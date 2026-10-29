"""控制密码。

被控端生成一次性随机数，控制端发送 HMAC。密码本身不在网络上传输，
也不写入磁盘。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PIN_LENGTH = 6


def new_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))


def new_nonce() -> str:
    return secrets.token_hex(16)


def proof(password: str, nonce: str) -> str:
    return hmac.new(password.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(password: str, nonce: str, given: str) -> bool:
    expected = proof(password, nonce)
    candidate = str(given)
    if len(candidate) != len(expected):
        return False
    return hmac.compare_digest(expected, candidate)
