"""连接过程中会交给界面显示的错误。"""


class ScrnError(Exception):
    """程序自己抛出的错误。"""


class ProtocolError(ScrnError):
    """对方发来的数据不符合约定。"""


class AuthError(ScrnError):
    """密码不正确。"""


class LanError(ScrnError):
    """地址不在允许的局域网范围内。"""


class BusyError(ScrnError):
    """被控端已经有一个控制端连着。"""


class BindError(ScrnError):
    """本机端口无法开始监听。"""


class ConnectionClosed(ScrnError):
    """对端已经断开。"""
