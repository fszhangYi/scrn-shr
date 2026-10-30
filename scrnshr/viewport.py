"""把控制窗口里的点击位置换算成被控端屏幕坐标，并编解码一帧画面。"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from scrnshr.errors import ProtocolError
from scrnshr.protocol import MAX_MESSAGE

# 1080p、1440p 按原始大小发送。再大的屏幕先收到这条边长以内。
_MAX_EDGE = 2560
_JPEG_QUALITY = 85


@dataclass(frozen=True)
class ViewGeometry:
    origin_x: int
    origin_y: int
    screen_w: int
    screen_h: int
    image_w: int
    image_h: int


def fit_frame(image, max_edge: int = _MAX_EDGE):
    """只在屏幕比上限更大时缩小，缩小用较锐利的采样。"""
    if image.width <= max_edge and image.height <= max_edge:
        return image
    from PIL import Image

    scale = min(max_edge / image.width, max_edge / image.height)
    width = max(1, int(image.width * scale))
    height = max(1, int(image.height * scale))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _jpeg_limit() -> int:
    # Base64 会胀大约 4/3，再给 JSON 字段留一点空位。
    return (MAX_MESSAGE - 512) * 3 // 4


def _encode_jpeg(image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, subsampling=0)
    return buffer.getvalue()


def _frame_that_fits(image):
    frame = image.convert("RGB")
    if max(frame.width, frame.height) > _MAX_EDGE:
        frame = fit_frame(frame, _MAX_EDGE)
    quality = _JPEG_QUALITY
    raw = _encode_jpeg(frame, quality)
    limit = _jpeg_limit()
    while len(raw) > limit and max(frame.width, frame.height) > 1280:
        edge = max(1280, int(max(frame.width, frame.height) * 0.8))
        if edge >= max(frame.width, frame.height):
            break
        frame = fit_frame(frame, edge)
        raw = _encode_jpeg(frame, quality)
    if len(raw) > limit:
        raw = _encode_jpeg(frame, 70)
    return frame, raw


def encode_screen(image, origin_x: int, origin_y: int, screen_w: int, screen_h: int, seq: int) -> dict:
    frame, raw = _frame_that_fits(image)
    payload = base64.b64encode(raw).decode("ascii")
    return {
        "t": "screen",
        "seq": int(seq),
        "ox": int(origin_x),
        "oy": int(origin_y),
        "sw": int(screen_w),
        "sh": int(screen_h),
        "w": frame.width,
        "h": frame.height,
        "jpg": payload,
    }


def decode_screen(message: dict):
    if message.get("t") != "screen":
        raise ProtocolError("不是画面消息")
    try:
        raw = base64.b64decode(message.get("jpg", ""), validate=True)
        image = _open_jpeg(raw)
        geometry = ViewGeometry(
            origin_x=_int_field(message, "ox"),
            origin_y=_int_field(message, "oy"),
            screen_w=_positive(message, "sw"),
            screen_h=_positive(message, "sh"),
            image_w=image.width,
            image_h=image.height,
        )
    except ProtocolError:
        raise
    except Exception as exc:
        raise ProtocolError("画面无法解析") from exc
    return image, geometry


def map_canvas_to_screen(
    canvas_x: float,
    canvas_y: float,
    canvas_w: int,
    canvas_h: int,
    geometry: ViewGeometry,
) -> tuple[int, int] | None:
    if canvas_w <= 0 or canvas_h <= 0 or geometry.image_w <= 0 or geometry.image_h <= 0:
        return None
    scale = min(canvas_w / geometry.image_w, canvas_h / geometry.image_h)
    draw_w = geometry.image_w * scale
    draw_h = geometry.image_h * scale
    offset_x = (canvas_w - draw_w) / 2
    offset_y = (canvas_h - draw_h) / 2
    if canvas_x < offset_x or canvas_y < offset_y or canvas_x > offset_x + draw_w or canvas_y > offset_y + draw_h:
        return None
    local_x = (canvas_x - offset_x) / scale
    local_y = (canvas_y - offset_y) / scale
    screen_x = round(geometry.origin_x + local_x * geometry.screen_w / geometry.image_w)
    screen_y = round(geometry.origin_y + local_y * geometry.screen_h / geometry.image_h)
    return int(screen_x), int(screen_y)


def map_canvas_filled(
    canvas_x: float,
    canvas_y: float,
    canvas_w: int,
    canvas_h: int,
    geometry: ViewGeometry,
) -> tuple[int, int] | None:
    """画面铺满窗口时，把窗口上的任意一点换算成对方屏幕坐标。"""
    if canvas_w <= 0 or canvas_h <= 0 or geometry.image_w <= 0 or geometry.image_h <= 0:
        return None
    local_x = min(max(canvas_x, 0), canvas_w - 1) / canvas_w * geometry.image_w
    local_y = min(max(canvas_y, 0), canvas_h - 1) / canvas_h * geometry.image_h
    screen_x = round(geometry.origin_x + local_x * geometry.screen_w / geometry.image_w)
    screen_y = round(geometry.origin_y + local_y * geometry.screen_h / geometry.image_h)
    return int(screen_x), int(screen_y)


def _open_jpeg(raw: bytes):
    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    image.load()
    if image.format != "JPEG":
        raise ProtocolError("画面不是 JPEG")
    return image


def _int_field(message: dict, name: str) -> int:
    value = message.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("画面坐标不正确")
    if not -32000 <= value <= 32000:
        raise ProtocolError("画面坐标超出范围")
    return value


def _positive(message: dict, name: str) -> int:
    value = _int_field(message, name)
    if value <= 0:
        raise ProtocolError("画面尺寸不正确")
    return value
