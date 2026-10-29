"""局域网地址判断，以及列出本机可以告诉对方的 IPv4。"""

from __future__ import annotations

import ipaddress
import socket
import subprocess
import sys
from collections.abc import Iterable

DEFAULT_PORT = 47621
_NO_WINDOW = 0x08000000


def is_lan_ip(value: str) -> bool:
    """是否允许作为控制目标或来源。

    允许私有地址、链路本地地址和本机回环。回环只给同一台电脑上的自动化测试使用，
    界面会另外拦住“连自己”。公网地址一律拒绝。
    """
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    if not isinstance(address, ipaddress.IPv4Address):
        return False
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        return False
    if address.is_loopback or address.is_link_local:
        return True
    return bool(address.is_private)


def peer_block_reason(ip: str, busy: bool) -> str | None:
    """被控端是否应拒绝这个来源。返回原因代码，允许时返回 None。"""
    if not is_lan_ip(ip):
        return "lan"
    if busy:
        return "busy"
    return None


def display_addresses(candidates: Iterable[str]) -> list[str]:
    """留给对方填写的地址。去掉回环和公网。"""
    chosen: list[str] = []
    for raw in candidates:
        ip = raw.strip()
        if not is_lan_ip(ip):
            continue
        if ipaddress.ip_address(ip).is_loopback:
            continue
        if ip not in chosen:
            chosen.append(ip)
    return chosen


def is_same_machine(ip: str, local_ips: Iterable[str]) -> bool:
    text = ip.strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    return text in set(local_ips)


def parse_port(value: str) -> int:
    text = value.strip()
    if not text.isdigit():
        raise ValueError("端口必须是数字")
    port = int(text)
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    return port


def prepare_target(ip: str, local_ips: Iterable[str]) -> str:
    """控制端真正发起连接前的检查。"""
    text = ip.strip()
    if not is_lan_ip(text):
        raise ValueError("只能连接局域网 IP 地址，例如 192.168.1.20")
    if is_same_machine(text, local_ips):
        raise ValueError("不能连接本机，否则键盘和鼠标会自己带动自己。请填写另一台电脑的地址。")
    return text


def _route_ipv4() -> list[str]:
    found: list[str] = []
    for target in ("192.168.1.1", "10.255.255.255", "172.16.0.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 9))
            ip = sock.getsockname()[0]
        except OSError:
            continue
        finally:
            sock.close()
        if ip not in found:
            found.append(ip)
    return found


def _powershell_ipv4() -> list[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress",
    ]
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 8,
        "check": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _NO_WINDOW
    try:
        completed = subprocess.run(command, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def get_lan_ipv4s() -> list[str]:
    candidates = _route_ipv4()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            candidates.append(info[4][0])
    except OSError:
        pass
    candidates.extend(_powershell_ipv4())
    return display_addresses(candidates)


def enable_tcp_keepalive(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if sys.platform != "win32":
        return
    try:
        sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10_000, 2_000))
    except OSError:
        pass
