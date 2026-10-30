"""控制端窗口。连接后显示对方画面，并转发键盘、鼠标、文件和剪贴板。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from scrnshr.capture import KeyHook, release_cursor_clip
from scrnshr.client_session import ClientSession
from scrnshr.desktop_link import DesktopLink
from scrnshr.inputlogic import ForwardPolicy
from scrnshr.netutil import DEFAULT_PORT, get_lan_ipv4s, parse_port, prepare_target
from scrnshr.scope import CLIENT_NOTES
from scrnshr.viewport import decode_screen, map_canvas_filled, map_canvas_to_screen
from scrnshr.winutil import configure_root, enable_dpi_awareness, make_icon_image, place_window

_BUTTONS = {1: "left", 2: "middle", 3: "right"}


class ClientApp:
    def __init__(self) -> None:
        enable_dpi_awareness()
        self._closed = False
        self._locked = False
        self._viewing = False
        self._view_gen = 0
        self.session: ClientSession | None = None
        self.peer: tuple[str, int] | None = None
        self._hook: KeyHook | None = None
        self.policy = ForwardPolicy()
        self._geo = None
        self._remote_image = None
        self._photo = None
        self._pending = None
        self._frame_after = None
        self._chrome_visible = True

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
        self.view_status = tk.StringVar(value="正在接收画面…")
        self._build()
        self.link = DesktopLink(self.root, self._send, self._link_status)

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
        ttk.Label(self.form, text="\n".join(CLIENT_NOTES), wraplength=420, justify="left").pack(anchor="w")

        self.capture = tk.Frame(self.root, bg="#1e2933")
        self.bar = ttk.Frame(self.capture, padding=(8, 6))
        self.bar.pack(fill="x")
        self.key_button = ttk.Button(self.bar, text="使用本机键盘", command=self._toggle_keys)
        self.key_button.pack(side="left")
        ttk.Button(self.bar, text="发送文件", command=self._send_file).pack(side="left", padx=(8, 0))
        ttk.Button(self.bar, text="隐藏边框", command=self._toggle_chrome).pack(side="left", padx=(8, 0))
        ttk.Button(self.bar, text="断开", command=self._disconnect).pack(side="right")
        ttk.Label(self.bar, textvariable=self.view_status).pack(side="left", padx=12)

        self.canvas = tk.Canvas(self.capture, bg="#1e2933", highlightthickness=0, cursor="arrow")
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
        self._view_gen += 1
        self._cancel_frame()
        self._locked = False
        self._viewing = False
        self._release_local_capture()
        try:
            self.link.stop()
        except Exception:
            pass
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
        self._view_gen += 1
        generation = self._view_gen
        self.session = session
        self.peer = (ip, port)
        self._geo = None
        self._remote_image = None
        self._pending = None
        self._set_busy(False)

        def closed() -> None:
            try:
                self.root.after(0, self._on_remote_closed)
            except tk.TclError:
                pass

        session.start_watch(self._on_network, closed)
        self.link.start()
        self._lock()
        self._schedule_frame(generation)

    def _on_network(self, message: dict) -> None:
        if message.get("t") == "screen":
            try:
                image, geometry = decode_screen(message)
            except Exception:
                return
            self._pending = (image, geometry)
            return
        try:
            self.root.after(0, lambda current=message: self._deliver_channel(current))
        except tk.TclError:
            pass

    def _deliver_channel(self, message: dict) -> None:
        if self._closed or self.session is None:
            return
        self.link.handle(message)

    def _pull_frame(self, generation: int) -> None:
        self._frame_after = None
        if generation != self._view_gen or self._closed or self.session is None:
            return
        pending = self._pending
        self._pending = None
        if pending is not None:
            image, geometry = pending
            merged = _paste_frame(self._remote_image, image, geometry)
            if merged is not None:
                self._remote_image = merged
                self._geo = geometry
                self._redraw()
        self._schedule_frame(generation)

    def _cancel_frame(self) -> None:
        after_id = self._frame_after
        self._frame_after = None
        if after_id is None:
            return
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass

    def _schedule_frame(self, generation: int) -> None:
        try:
            self._frame_after = self.root.after(30, lambda: self._pull_frame(generation))
        except tk.TclError:
            pass

    def _lock(self) -> None:
        if self.session is None or self._closed:
            return
        self._show_capture()
        if self._hook is not None:
            return
        self.policy = ForwardPolicy()
        try:
            self._hook = KeyHook(self._on_key)
            self._hook.start()
        except Exception as exc:
            self._hook = None
            self._locked = False
            self.view_status.set(f"画面可用，键盘捕获失败：{exc}")
            self.key_button.configure(text="控制对方键盘")
            return
        self._locked = True
        self.view_status.set("正在转发键盘和鼠标。Ctrl+Alt+H 隐藏边框，最小化或点「使用本机键盘」交还键盘。")
        self.key_button.configure(text="使用本机键盘")

    def _toggle_keys(self) -> None:
        if self._locked:
            self._end_forwarding(notify_remote=True, disconnect=False)
        else:
            self._lock()

    def _show_capture(self) -> None:
        first = not self._viewing
        self._viewing = True
        self.form.pack_forget()
        self.capture.pack(fill="both", expand=True)
        if first:
            self.root.minsize(720, 480)
            self._fill_screen()
            self._draw_waiting()
        self.root.bind("<Escape>", self._escape_backup)
        self.root.bind("<Control-Alt-q>", self._disconnect_backup)
        self.root.bind("<Control-Alt-Q>", self._disconnect_backup)
        self.root.bind("<Control-Alt-h>", self._toggle_chrome)
        self.root.bind("<Control-Alt-H>", self._toggle_chrome)
        self.root.bind("<Unmap>", self._on_unmap)
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass

    def _fill_screen(self) -> None:
        try:
            self.root.state("zoomed")
        except tk.TclError:
            place_window(self.root, self.root.winfo_screenwidth() - 20, self.root.winfo_screenheight() - 60)

    def _on_unmap(self, event) -> None:
        if event.widget is not self.root:
            return
        try:
            self.root.after(80, self._release_if_minimized)
        except tk.TclError:
            pass

    def _release_if_minimized(self) -> None:
        if self._closed or not self._locked:
            return
        try:
            minimized = self.root.state() == "iconic"
        except tk.TclError:
            return
        if minimized:
            self._end_forwarding(notify_remote=True, disconnect=False)

    def _draw_waiting(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 200)
        self.canvas.create_text(
            width / 2,
            height / 2,
            text="正在接收对方画面…\n\n在画面上移动和点击即可操作对方。\nCtrl+Alt+H 隐藏标题栏和工具条。\n最小化或点「使用本机键盘」交还键盘，Ctrl+Alt+Q 断开。",
            fill="white",
            font=("Microsoft YaHei UI", 14),
            justify="center",
        )

    def _redraw(self) -> None:
        if not self._viewing or self._remote_image is None:
            return
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        from PIL import Image, ImageTk

        if (width, height) == self._remote_image.size:
            shown = self._remote_image
        else:
            shown = self._remote_image.resize((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(width / 2, height / 2, image=self._photo)

    def _on_canvas_configure(self, event) -> None:
        if not self._viewing or event.widget is not self.canvas or event.width < 40 or event.height < 40:
            return
        if self._remote_image is None:
            self._draw_waiting()
        else:
            self._redraw()

    def _pointer_target(self, event):
        if self._geo is None:
            return None
        return map_canvas_filled(
            event.x,
            event.y,
            event.widget.winfo_width(),
            event.widget.winfo_height(),
            self._geo,
        )

    def _on_motion(self, event) -> None:
        if not self._viewing or self.session is None:
            return
        point = self._pointer_target(event)
        if point is not None:
            self._send_input({"t": "abs", "x": point[0], "y": point[1]})

    def _on_press(self, event):
        self._button(event, True)
        return "break"

    def _on_release(self, event):
        self._button(event, False)
        return "break"

    def _button(self, event, down: bool) -> None:
        if not self._viewing or self.session is None:
            return
        point = self._pointer_target(event)
        if point is None:
            return
        if down:
            self._send_input({"t": "abs", "x": point[0], "y": point[1]})
        name = _BUTTONS.get(event.num)
        if name is not None:
            self._send_input({"t": "button", "b": name, "down": down})

    def _on_wheel(self, event):
        if not self._viewing:
            return "break"
        steps = int(event.delta / 120) if event.delta else 0
        if steps == 0 and event.delta:
            steps = 1 if event.delta > 0 else -1
        if steps:
            self._send_input({"t": "scroll", "dx": 0, "dy": steps})
        return "break"

    def _on_key(self, spec: dict, down: bool) -> None:
        action = self.policy.decide(spec, down)
        if action == "unlock":
            self.root.after(0, lambda: self._end_forwarding(notify_remote=True, disconnect=False))
            return
        if action == "chrome":
            self.root.after(0, self._toggle_chrome)
            return
        if action == "disconnect":
            self.root.after(0, lambda: self._end_forwarding(notify_remote=False, disconnect=True))
            return
        self._send_input({"t": "key", "kind": spec["kind"], "v": spec["v"], "down": down})

    def _send(self, message: dict) -> None:
        self._transmit(message, queued=False)

    def _send_input(self, message: dict) -> None:
        self._transmit(message, queued=True)

    def _transmit(self, message: dict, queued: bool) -> None:
        session = self.session
        if session is None:
            return
        try:
            if queued:
                session.send_input(message)
            else:
                session.send(message)
        except Exception:
            try:
                self.root.after(0, self._on_remote_closed)
            except tk.TclError:
                pass

    def _toggle_chrome(self, _event=None):
        if not self._viewing or self._closed:
            return "break"
        try:
            if self._chrome_visible:
                self.bar.pack_forget()
                self.root.overrideredirect(True)
                width = self.root.winfo_screenwidth()
                height = self.root.winfo_screenheight()
                self.root.geometry(f"{width}x{height}+0+0")
                self._chrome_visible = False
            else:
                self.root.overrideredirect(False)
                if not self.bar.winfo_manager():
                    self.bar.pack(fill="x", before=self.canvas)
                self._fill_screen()
                self._chrome_visible = True
                self.view_status.set("已显示标题栏和工具条。Ctrl+Alt+H 再次隐藏。")
            self.canvas.focus_set()
        except tk.TclError:
            pass
        return "break"

    def _send_file(self) -> None:
        if self.session is None:
            return
        if self._locked:
            self._end_forwarding(notify_remote=True, disconnect=False)
        selected = filedialog.askopenfilename(parent=self.root, title="发送文件给被控端")
        if selected:
            self.link.send_path(Path(selected))

    def _link_status(self, text: str) -> None:
        if self._closed:
            return
        if self._viewing:
            self.view_status.set(text)
        else:
            self.status.set(text)

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
            self.view_status.set("键盘已交还这台电脑。鼠标仍可在画面上操作。")
            self.key_button.configure(text="控制对方键盘")

    def _disconnect(self) -> None:
        self._view_gen += 1
        self._cancel_frame()
        self._locked = False
        self._viewing = False
        self._release_local_capture()
        try:
            self.link.stop()
        except Exception:
            pass
        session = self.session
        self.session = None
        self.peer = None
        self._geo = None
        self._remote_image = None
        self._pending = None
        if session is not None:
            session.close()
        self._show_idle()
        if not self._closed:
            self.status.set("已断开。")

    def _on_remote_closed(self) -> None:
        if self._closed or (self.session is None and not self._locked and not self._viewing):
            return
        self._disconnect()
        if not self._closed:
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

    def _show_idle(self) -> None:
        if self._closed:
            return
        try:
            self.root.unbind("<Escape>")
            self.root.unbind("<Control-Alt-q>")
            self.root.unbind("<Control-Alt-Q>")
            self.root.unbind("<Control-Alt-h>")
            self.root.unbind("<Control-Alt-H>")
            self.root.unbind("<Unmap>")
            self._chrome_visible = True
            try:
                self.root.overrideredirect(False)
                self.root.state("normal")
            except tk.TclError:
                pass
            self.capture.pack_forget()
            self.form.pack(fill="both", expand=True)
            self.root.minsize(460, 420)
            for entry in self.entries:
                entry.state(["!disabled"])
            self.primary.configure(text="连接", command=self._connect, state="normal")
            self.secondary.pack_forget()
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


def _paste_frame(base, image, geometry):
    crop = geometry.crop
    if crop is None:
        return image
    if base is None or base.size != (geometry.image_w, geometry.image_h):
        return None
    merged = base.copy()
    merged.paste(image, (crop[0], crop[1]))
    return merged


def run() -> None:
    app = ClientApp()
    try:
        app.run()
    finally:
        app.shutdown()
