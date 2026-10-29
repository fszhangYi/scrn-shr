"""这一版做到哪为止。

画面、文件和剪贴板留在后面，不在当前程序里实现。
两台电脑都要手动打开，不注册开机启动。
"""

from __future__ import annotations

DEFERRED_SENTENCE = "这一版只转发键盘和鼠标，不传画面、文件和剪贴板。"
MANUAL_SENTENCE = "需要两边都手动打开，不会加入开机启动。"

HOST_NOTES = (
    "关闭窗口后程序会留在托盘里，托盘菜单可以再次打开或退出。",
    MANUAL_SENTENCE,
    DEFERRED_SENTENCE,
    "以当前登录用户运行即可，不需要管理员。UAC 提示和锁屏无法控制。",
    "如果系统询问防火墙，请允许它在专用网络上接收连接。",
)

CLIENT_NOTES = (
    "连接后会转发键盘和鼠标。Esc 释放光标，Ctrl+Alt+Q 断开连接。",
    "请填写另一台电脑的地址，不要填写本机。",
    DEFERRED_SENTENCE,
    MANUAL_SENTENCE,
)
