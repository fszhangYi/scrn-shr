"""控制端窗口。连接后锁定本机光标，把键盘和鼠标发给被控端。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import threading

from scrnshr.capture import KeyHook, clip_cursor, release_cursor_clip, set_cursor_pos
from scrnshr.client_session import ClientSession
from scrnshr.inputlogic import ForwardPolicy, PointerLockMath
from scrnshr.netutil import DEFAULT_PORT, get_lan_ipv4s, parse_port, prepare_target
from scrnshr.winutil import configure_root, enable_dpi_awareness, make_icon_image, place_window

NOTES = (
    "连接后会转发键盘和鼠标。Esc 释放光标，Ctrl+Alt+Q 断开连接。",
    "请填写另一台电脑的地址，不要填写本机。",
    "这一版不传画面、文件和剪贴板。",
    "需要两边都手动打开，不会加入开机启动。",
)

_BUTTONS = {1: "left", 2: "middle", 3: "right"}


class ClientApp:
    def __init__(self) -> None:
        enable_dpi_awareness()
        self._closed = False
        self._locked = False
        self._engage_tries = 0
        self._disarmed_recenters = 0
        self.session: ClientSession | None = None
        self.peer: tuple[str, int] | None = None
        self._hook: KeyHook | None = None
        self.policy = ForwardPolicy()
        self.pointer = PointerLockMath()

        self.root = tk.Tk()
        configure_root(self.root)
        self.root.title("局域网键鼠控制端")
        self.root.minsize(460, 420)
        place_window(self.root, 480, 460)
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        try:
            from PIL import ImageTk

            self._icon_photo = ImageTk.PhotoImage(make_icon_image())
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            self._icon_photo = None

        self.ip_var = tk.StringVar()
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.password_var = tk.StringVar()
        self.status = tk.StringVar(value="未连接")
        self._build()

    def _build(self) -> None:
        self.form = ttk.Frame(self.root, padding=16)
        ttk.Label(self.form, text="局域网键鼠 · 控制端", font=("Microsoft YaHei UI", 16)).pack(anchor="w")
        ttk.Label(self.form, text="填写被控端窗口上的地址和密码。", wraplength=420).pack(anchor="w", pady=(8, 14))

        self.ip_entry = self._field("对方 IP", self.ip_var)
        self.port_entry = self._field("端口", self.port_var)
        self.password_entry = self._field("控制密码", self.password_var)
        self.entries = (self.ip_entry, self.port_entry, self.password_entry)
        self.ip_entry.focus_set()

        buttons = ttk.Frame(self.form)
        buttons.pack(fill="x", pady=(8, 8))
        self.primary = ttk.Button(buttons, text="连接", command=self._connect)
        self.primary.pack(side="right")
        self.secondary = ttk.Button(buttons, text="断开", command=self._disconnect)

        ttk.Label(self.form, text="状态").pack(anchor="w", pady=(8, 0))
        ttk.Label(self.form, textvariable=self.status, wraplength=420, justify="left").pack(anchor="w", pady=(4, 12))
        ttk.Label(self.form, text="\n".join(NOTES), wraplength=420, justify="left").pack(anchor="w")

        self.capture = tk.Frame(self.root, bg="#1e2933")
        self.canvas = tk.Canvas(self.capture, bg="#1e2933", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonPress>", self._on_press)
        self.canvas.bind("<ButtonRelease>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.form.pack(fill="both", expand=True)

    def _field(self, label: str, variable: tk.StringVar) -> ttk.Entry:
        ttk.Label(self.form, text=label).pack(anchor="w")
        entry = ttk.Entry(self.form, textvariable=variable)
        entry.pack(fill="x", pady=(4, 10))
        return entry

    def run(self) -> None:
        self.root.mainloop()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._locked = False
        self._release_local_capture()
        session = self.session
        self.session = None
        if session is not None:
            session.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _connect(self) -> None:
        if self.session is not None or self._closed:
            return
        try:
            port = parse_port(self.port_var.get())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        password = self.password_var.get().strip()
        if not password:
            self.status.set("请填写被控端窗口上的控制密码。")
            return
        ip_text = self.ip_var.get()
        self._set_busy(True)
        self.status.set("正在连接…")

        def work() -> None:
            try:
                ip = prepare_target(ip_text, get_lan_ipv4s())
                session = ClientSession()
                session.connect(ip, port, password)
            except Exception as exc:
                self.root.after(0, lambda error=exc: self._connect_failed(error))
                return
            self.root.after(0, lambda found=session, host=ip: self._connect_ok(found, host, port))

        threading.Thread(target=work, name="scrnshr-connect", daemon=True).start()

    def _connect_failed(self, exc: Exception) -> None:
        if self._closed:
            return
        self._set_busy(False)
        self.status.set(str(exc) or "连接失败")

    def _connect_ok(self, session: ClientSession, ip: str, port: int) -> None:
        if self._closed:
            session.close()
            return
        self.session = session
        self.peer = (ip, port)
        self._set_busy(False)

        def notify() -> None:
            try:
                self.root.after(0, self._on_remote_closed)
            except tk.TclError:
                pass

        session.start_watch(notify)
        self._lock()

    def _lock(self) -> None:
        if self.session is None or self._closed:
            return
        self.policy = ForwardPolicy()
        self.pointer = PointerLockMath()
        try:
            self._hook = KeyHook(self._on_key)
            self._hook.start()
        except Exception as exc:
            self._hook = None
            self.status.set(f"无法捕获键盘：{exc}")
            self._show_unlocked()
            return
        self._locked = True
        self._engage_tries = 0
        self._disarmed_recenters = 0
        self._show_capture()
        self.root.after(40, self._engage_pointer)

    def _show_capture(self) -> None:
        self.form.pack_forget()
        self.capture.pack(fill="both", expand=True)
        self.root.minsize(640, 420)
        place_window(self.root, 720, 480)
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        self._draw_hint()
        self.root.bind("<Escape>", self._escape_backup)
        self.root.bind("<Control-Alt-q>", self._disconnect_backup)
        self.root.bind("<Control-Alt-Q>", self._disconnect_backup)

    def _engage_pointer(self) -> None:
        if not self._locked:
            return
        self.canvas.update_idletasks()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 40 or height < 40:
            self._engage_tries += 1
            if self._engage_tries < 20:
                self.root.after(50, self._engage_pointer)
                return
            self._end_forwarding(notify_remote=True, disconnect=False)
            self.status.set("控制窗口没有显示出来，已停止转发。")
            return
        try:
            self._warp_and_clip()
        except OSError as exc:
            self._end_forwarding(notify_remote=True, disconnect=False)
            self.status.set(str(exc))
            return
        self.canvas.focus_set()
        self.root.after(150, self._arm_pointer)

    def _arm_pointer(self) -> None:
        if self._locked:
            self.pointer.arm()

    def _warp_and_clip(self) -> None:
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        clip_cursor(left, top, left + width, top + height)
        set_cursor_pos(left + width // 2, top + height // 2)

    def _draw_hint(self) -> None:
        self.canvas.delete("all")
        peer = self.peer or ("", 0)
        text = (
            f"正在把键盘和鼠标转发到 {peer[0]}:{peer[1]}\n\n"
            "光标已锁定在这个窗口里。\n"
            "Esc            释放光标，回到本机操作\n"
            "Ctrl+Alt+Q     断开连接\n\n"
            "这一版只转发键盘和鼠标，不传画面、文件和剪贴板。"
        )
        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 200)
        self.canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill="white",
            font=("Microsoft YaHei UI", 14),
            justify="center",
            width=width - 48,
        )

    def _on_canvas_configure(self, event) -> None:
        if not self._locked or event.widget is not self.canvas or event.width < 40 or event.height < 40:
            return
        self._draw_hint()
        try:
            self._warp_and_clip()
        except OSError:
            return

    def _on_motion(self, event) -> None:
        if not self._locked or event.widget is not self.canvas:
            return
        if self.canvas.winfo_width() < 40:
            return
        delta = self.pointer.on_move(event.x, event.y, event.widget.winfo_width(), event.widget.winfo_height())
        if delta is not None:
            self._send({"t": "move", "dx": delta[0], "dy": delta[1]})
            self._try_recenter()
            return
        if self.pointer.armed:
            return
        self._disarmed_recenters += 1
        if self._disarmed_recenters > 8:
            self.pointer.arm()
            return
        self._try_recenter()

    def _try_recenter(self) -> None:
        try:
            self._recenter()
        except OSError as exc:
            self._end_forwarding(notify_remote=True, disconnect=False)
            self.status.set(str(exc))

    def _recenter(self) -> None:
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        set_cursor_pos(left + self.canvas.winfo_width() // 2, top + self.canvas.winfo_height() // 2)

    def _on_press(self, event):
        self._button(event, True)
        return "break"

    def _on_release(self, event):
        self._button(event, False)
        return "break"

    def _button(self, event, down: bool) -> None:
        if not self._locked:
            return
        name = _BUTTONS.get(event.num)
        if name is None:
            return
        self._send({"t": "button", "b": name, "down": down})

    def _on_wheel(self, event):
        if not self._locked:
            return "break"
        steps = int(event.delta / 120) if event.delta else 0
        if steps == 0 and event.delta:
            steps = 1 if event.delta > 0 else -1
        if steps:
            self._send({"t": "scroll", "dx": 0, "dy": steps})
        return "break"

    def _on_key(self, spec: dict, down: bool) -> None:
        action = self.policy.decide(spec, down)
        if action == "unlock":
            self.root.after(0, lambda: self._end_forwarding(notify_remote=True, disconnect=False))
            return
        if action == "disconnect":
            self.root.after(0, lambda: self._end_forwarding(notify_remote=False, disconnect=True))
            return
        self._send({"t": "key", "kind": spec["kind"], "v": spec["v"], "down": down})

    def _send(self, message: dict) -> None:
        session = self.session
        if session is None:
            return
        try:
            session.send(message)
        except Exception:
            try:
                self.root.after(0, self._on_remote_closed)
            except tk.TclError:
                pass

    def _escape_backup(self, _event=None):
        if self._locked:
            self._end_forwarding(notify_remote=True, disconnect=False)
        return "break"

    def _disconnect_backup(self, _event=None):
        self._end_forwarding(notify_remote=False, disconnect=True)
        return "break"

    def _end_forwarding(self, notify_remote: bool, disconnect: bool) -> None:
        was_locked = self._locked
        self._locked = False
        if was_locked:
            self._release_local_capture()
            if notify_remote and self.session is not None and not disconnect:
                try:
                    self.session.send({"t": "release_all"})
                except Exception:
                    disconnect = True
        if disconnect:
            self._disconnect()
        elif was_locked and not self._closed:
            self._show_unlocked()

    def _disconnect(self) -> None:
        self._locked = False
        self._release_local_capture()
        session = self.session
        self.session = None
        self.peer = None
        if session is not None:
            session.close()
        self._show_idle()
        if not self._closed:
            self.status.set("已断开。")

    def _on_remote_closed(self) -> None:
        if self._closed or (self.session is None and not self._locked):
            return
        self._locked = False
        self._release_local_capture()
        session = self.session
        self.session = None
        self.peer = None
        if session is not None:
            session.close()
        self._show_idle()
        self.status.set("对方已断开。")

    def _release_local_capture(self) -> None:
        hook = self._hook
        self._hook = None
        if hook is not None:
            try:
                hook.stop()
            except Exception:
                pass
        try:
            release_cursor_clip()
        except Exception:
            pass
        if self._closed:
            return
        try:
            self.root.attributes("-topmost", False)
            self.root.unbind("<Escape>")
            self.root.unbind("<Control-Alt-q>")
            self.root.unbind("<Control-Alt-Q>")
        except tk.TclError:
            pass

    def _show_idle(self) -> None:
        if self._closed:
            return
        try:
            self.capture.pack_forget()
            self.form.pack(fill="both", expand=True)
            self.root.minsize(460, 420)
            for entry in self.entries:
                entry.state(["!disabled"])
            self.primary.configure(text="连接", command=self._connect, state="normal")
            self.secondary.pack_forget()
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _show_unlocked(self) -> None:
        if self._closed:
            return
        self._show_idle()
        if self.peer is None:
            return
        try:
            for entry in self.entries:
                entry.state(["disabled"])
            self.primary.configure(text="继续转发", command=self._lock, state="normal")
            self.secondary.pack(side="right", padx=(0, 6))
            self.status.set(f"已连接 {self.peer[0]}:{self.peer[1]}。光标已释放，本机可以正常操作。")
        except tk.TclError:
            pass

    def _set_busy(self, busy: bool) -> None:
        if self._closed:
            return
        if busy:
            self.primary.configure(state="disabled")
            for entry in self.entries:
                entry.state(["disabled"])
            return
        if self.session is None:
            self.primary.configure(state="normal")
            for entry in self.entries:
                entry.state(["!disabled"])


def run() -> None:
    app = ClientApp()
    try:
        app.run()
    finally:
        app.shutdown()
