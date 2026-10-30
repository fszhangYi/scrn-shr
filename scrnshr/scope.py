"""产品说明。两边都要手动打开，不注册开机启动。"""

from __future__ import annotations

SHARE_SENTENCE = "连接后会传输画面，并可以互传文件和剪贴板。"
MANUAL_SENTENCE = "需要两边都手动打开，不会加入开机启动。"
SAVE_SENTENCE = "收到的文件保存在“下载”文件夹的“局域网键鼠”目录里。"

HOST_NOTES = (
    "关闭窗口后程序会留在托盘里，托盘菜单可以再次打开或退出。",
    MANUAL_SENTENCE,
    SHARE_SENTENCE,
    SAVE_SENTENCE,
    "以当前登录用户运行即可，不需要管理员。UAC 提示和锁屏无法控制，也不会出现在画面里。",
    "如果系统询问防火墙，请允许它在专用网络上接收连接。",
)

CLIENT_NOTES = (
    "连接后显示对方画面，并尽量铺满窗口。在画面上移动和点击即可操作对方。",
    "点「使用本机键盘」，或把窗口最小化，键盘就交还这台电脑。Esc 同样可以释放。Ctrl+Alt+Q 断开连接。",
    SHARE_SENTENCE,
    SAVE_SENTENCE,
    "请填写另一台电脑的地址，不要填写本机。",
    MANUAL_SENTENCE,
)
