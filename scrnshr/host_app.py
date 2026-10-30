"""被控端窗口和托盘。"""

from __future__ import annotations

import ctypes
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from scrnshr.auth import new_pin
from scrnshr.desktop_link import DesktopLink
from scrnshr.errors import BindError
from scrnshr.host_server import HostServer
from scrnshr.inject import PynputInjector
from scrnshr.netutil import DEFAULT_PORT, get_lan_ipv4s
from scrnshr.scope import HOST_NOTES
from scrnshr.screengrab import capture_message
from scrnshr.winutil import configure_root, enable_dpi_awareness, make_icon_image, place_window

DENY_TEXT = {
    "auth": "有连接使用了错误的密码。",
    "lan": "已拒绝局域网以外的地址。",
    "busy": "已经有一个控制端连着，新的连接被拒绝。",
    "version": "对方版本和本程序不一致。",
}


class HostApp:
    def __init__(self, bind_host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
        enable_dpi_awareness()
        self._closed = False
        self._controlled = False
        self._addresses_ready = False
        self.addresses: list[str] = []
        self._events: queue.Queue = queue.Queue()
        self.icon = None
        self._share_stop = threading.Event()
        self._share_stop.set()
        self._poll_after = None

        self.root = tk.Tk()
        configure_root(self.root)
        self.root.title("局域网键鼠被控端")
        self.root.minsize(440, 520)
        place_window(self.root, 460, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._hide)

        self._icon_image = make_icon_image()
        try:
            from PIL import ImageTk

            self._icon_photo = ImageTk.PhotoImage(self._icon_image)
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            self._icon_photo = None

        self.state_var = tk.StringVar(value="正在启动")
        self.detail_var = tk.StringVar(value="")
        self.password_var = tk.StringVar(value=new_pin())
        self._build()

        self.server = HostServer(
            PynputInjector(),
            self.password_var.get(),
            port=port,
            bind_host=bind_host,
        )
        self.server.set_status_callback(lambda *payload: self._events.put(payload))
        self.server.set_channel_callback(lambda message: self._events.put(("channel", message)))
        self.link = DesktopLink(self.root, self._send_remote, self._link_status)
        try:
            self.server.start()
        except BindError as exc:
            self.detail_var.set(str(exc))
        self._start_tray()
        self._load_addresses()
        self._poll_after = self.root.after(150, self._poll)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="局域网键鼠 · 被控端", font=("Microsoft YaHei UI", 16)).pack(anchor="w")
        ttk.Label(
            frame,
            text="把下面的地址和控制密码告诉同一局域网里的另一台电脑。",
            wraplength=410,
        ).pack(anchor="w", pady=(8, 14))

        ttk.Label(frame, text="本机地址").pack(anchor="w")
        self.address_frame = ttk.Frame(frame)
        self.address_frame.pack(fill="x", pady=(4, 12))
        ttk.Label(self.address_frame, text="正在读取本机地址…").pack(anchor="w")

        ttk.Label(frame, text="控制密码").pack(anchor="w")
        password_row = ttk.Frame(frame)
        password_row.pack(fill="x", pady=(4, 12))
        ttk.Label(password_row, textvariable=self.password_var, font=("Consolas", 20)).pack(side="left")
        ttk.Button(password_row, text="复制", command=self._copy_password).pack(side="right")
        self.regen = ttk.Button(password_row, text="更换", command=self._new_password)
        self.regen.pack(side="right", padx=(0, 6))

        ttk.Label(frame, text="状态").pack(anchor="w")
        ttk.Label(frame, textvariable=self.state_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(frame, textvariable=self.detail_var, wraplength=410, justify="left").pack(anchor="w", pady=(4, 12))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="刷新地址", command=self._load_addresses).pack(side="left")
        ttk.Button(buttons, text="发送文件", command=self._send_file).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="停止并退出", command=self.shutdown).pack(side="right")

        ttk.Label(frame, text="\n".join(HOST_NOTES), wraplength=410, justify="left").pack(anchor="w", pady=(18, 0))

    def run(self) -> None:
        self.root.mainloop()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_poll()
        self._stop_share()
        try:
            self.link.stop()
        except Exception:
            pass
        try:
            self.server.stop()
        except Exception:
            pass
        icon = self.icon
        self.icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _hide(self) -> None:
        self.detail_var.set("窗口已放到托盘。右下角图标可以重新打开，或选择“停止并退出”。")
        self.root.withdraw()

    def _show(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        if self._closed:
            return
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _load_addresses(self) -> None:
        def work() -> None:
            ips = get_lan_ipv4s()

            def deliver() -> None:
                if self._closed:
                    return
                self._set_addresses(ips)

            try:
                self.root.after(0, deliver)
            except tk.TclError:
                pass

        threading.Thread(target=work, name="scrnshr-ips", daemon=True).start()

    def _set_addresses(self, ips: list[str]) -> None:
        self._addresses_ready = True
        self.addresses = list(ips)
        for child in self.address_frame.winfo_children():
            child.destroy()
        if not self.server.listening:
            ttk.Label(self.address_frame, text="没有在监听，地址暂时不可用。", wraplength=410).pack(anchor="w")
        elif not ips:
            ttk.Label(
                self.address_frame,
                text="没有发现局域网地址。请确认这台电脑已经连上 Wi-Fi 或网线。",
                wraplength=410,
            ).pack(anchor="w")
        else:
            for ip in ips:
                row = ttk.Frame(self.address_frame)
                row.pack(fill="x", pady=2)
                label = f"{ip}:{self.server.port}"
                ttk.Label(row, text=label).pack(side="left")
                ttk.Button(row, text="复制", command=lambda text=label: self._copy(text)).pack(side="right")
        self._apply_menu()
        self._update_tooltip()

    def _copy_password(self) -> None:
        self._copy(self.password_var.get())

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.detail_var.set("已复制。")

    def _new_password(self) -> None:
        if self._controlled:
            return
        pin = new_pin()
        self.password_var.set(pin)
        self.server.set_password(pin)
        self.detail_var.set("已更换密码。请把新密码告诉控制端。")

    def _cancel_poll(self) -> None:
        after_id = self._poll_after
        self._poll_after = None
        if after_id is None:
            return
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass

    def _poll(self) -> None:
        self._poll_after = None
        if self._closed:
            return
        while True:
            try:
                payload = self._events.get_nowait()
            except queue.Empty:
                break
            self._apply_status(payload)
        try:
            self._poll_after = self.root.after(150, self._poll)
        except tk.TclError:
            pass

    def _apply_status(self, payload) -> None:
        kind = payload[0]
        if kind == "waiting":
            self._controlled = False
            self._stop_share()
            self.link.stop()
            self.state_var.set("等待连接")
            self.regen.state(["!disabled"])
        elif kind == "connected":
            self._controlled = True
            self.state_var.set(f"正在被 {payload[1]} 控制")
            self.detail_var.set("对方可以看到这台电脑的画面，并操作键盘和鼠标。")
            self.regen.state(["disabled"])
            self.link.start()
            self._start_share()
        elif kind == "denied":
            self.detail_var.set(DENY_TEXT.get(payload[1], "已拒绝一次连接。"))
        elif kind == "channel":
            self.link.handle(payload[1])
        elif kind == "detail":
            self.detail_var.set(payload[1])
        self._update_tooltip()

    def _start_tray(self) -> None:
        try:
            import pystray
        except Exception as exc:
            self.detail_var.set(f"托盘不可用：{exc}")
            return
        self._pystray = pystray
        self.icon = pystray.Icon(
            "scrnshr-host",
            self._icon_image,
            "局域网键鼠被控端",
            menu=self._build_menu(),
        )
        try:
            self.icon.run_detached()
        except Exception as exc:
            self.icon = None
            self.detail_var.set(f"托盘不可用：{exc}")

    def _build_menu(self):
        pystray = self._pystray
        items = [pystray.MenuItem("显示窗口", self._show, default=True), pystray.Menu.SEPARATOR]
        if not self.server.listening:
            items.append(pystray.MenuItem("没有在监听", None, enabled=False))
        elif not self._addresses_ready:
            items.append(pystray.MenuItem("正在读取地址", None, enabled=False))
        elif not self.addresses:
            items.append(pystray.MenuItem("没有局域网地址", None, enabled=False))
        else:
            for ip in self.addresses:
                items.append(pystray.MenuItem(f"{ip}:{self.server.port}", None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("停止并退出", self._quit_from_tray))
        return pystray.Menu(*items)

    def _apply_menu(self) -> None:
        if self.icon is None:
            return
        try:
            self.icon.menu = self._build_menu()
        except Exception:
            pass

    def _update_tooltip(self) -> None:
        if self.icon is None:
            return
        if self._controlled:
            title = self.state_var.get()
        elif self.addresses and self.server.listening:
            title = "  ".join(f"{ip}:{self.server.port}" for ip in self.addresses)
        else:
            title = "局域网键鼠被控端"
        try:
            self.icon.title = title
        except Exception:
            pass

    def _send_remote(self, message: dict) -> None:
        if not self.server.send(message):
            raise ConnectionError("连接已断开")

    def _link_status(self, text: str) -> None:
        if not self._closed:
            self.detail_var.set(text)

    def _send_file(self) -> None:
        if not self._controlled:
            self.detail_var.set("还没有控制端连接。")
            return
        selected = filedialog.askopenfilename(parent=self.root, title="发送文件给控制端")
        if selected:
            self.link.send_path(Path(selected))

    def _start_share(self) -> None:
        self._stop_share()
        stop = threading.Event()
        self._share_stop = stop
        threading.Thread(target=self._share_loop, args=(stop,), name="scrnshr-screen", daemon=True).start()

    def _stop_share(self) -> None:
        self._share_stop.set()

    def _share_loop(self, stop: threading.Event) -> None:
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        seq = 0
        reported = False
        while not stop.is_set() and self._controlled:
            seq += 1
            started = time.perf_counter()
            try:
                self.server.send(capture_message(seq))
            except Exception as exc:
                if not reported:
                    reported = True
                    self._events.put(("detail", f"画面发送失败：{exc}"))
            remaining = 0.12 - (time.perf_counter() - started)
            if stop.wait(max(0.02, remaining)):
                break

    def _quit_from_tray(self, _icon=None, _item=None) -> None:
        try:
            self.root.after(0, self.shutdown)
        except tk.TclError:
            self.shutdown()


def run() -> None:
    app = HostApp()
    try:
        app.run()
    finally:
        app.shutdown()
