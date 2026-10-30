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
    crop: tuple[int, int, int, int] | None = None


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


def _encode_jpeg(image, quality: int, subsampling: int = 0) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, subsampling=subsampling)
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


def plan_frame(previous, image, origin_x: int, origin_y: int, screen_w: int, screen_h: int, seq: int, *, force_full: bool = False):
    """相对上一帧只编码变化区域。没有变化时返回 None，调用方就不要占着发送。"""
    frame = _fitted(image)
    if previous is None or previous.size != frame.size:
        return _binary_frame(frame, origin_x, origin_y, screen_w, screen_h, seq, 85, 0), frame
    from PIL import ImageChops

    box = ImageChops.difference(previous, frame).getbbox()
    if box is None:
        return None, previous
    area = (box[2] - box[0]) * (box[3] - box[1])
    if force_full or area > frame.width * frame.height * 0.7:
        quality, subsampling = (85, 0) if force_full else (70, 2)
        return _binary_frame(frame, origin_x, origin_y, screen_w, screen_h, seq, quality, subsampling), frame
    x0, y0, x1, y1 = _align_box(box, frame.width, frame.height)
    crop = frame.crop((x0, y0, x1, y1))
    message = _binary_frame(crop, origin_x, origin_y, screen_w, screen_h, seq, 75, 0 if area < frame.width * frame.height * 0.2 else 2)
    message["w"] = frame.width
    message["h"] = frame.height
    message.update(cx=x0, cy=y0, cw=x1 - x0, ch=y1 - y0)
    return message, frame


def _fitted(image):
    frame = image.convert("RGB")
    if max(frame.width, frame.height) > _MAX_EDGE:
        frame = fit_frame(frame, _MAX_EDGE)
    return frame


def _binary_frame(frame, origin_x: int, origin_y: int, screen_w: int, screen_h: int, seq: int, quality: int, subsampling: int) -> dict:
    return {
        "t": "screen",
        "bin": True,
        "seq": int(seq),
        "ox": int(origin_x),
        "oy": int(origin_y),
        "sw": int(screen_w),
        "sh": int(screen_h),
        "w": frame.width,
        "h": frame.height,
        "jpg": _encode_jpeg(frame, quality, subsampling),
    }


def _align_box(box, width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = max(0, x0 & ~15)
    y0 = max(0, y0 & ~15)
    x1 = min(width, (x1 + 15) & ~15)
    y1 = min(height, (y1 + 15) & ~15)
    if x1 <= x0 or y1 <= y0:
        return 0, 0, width, height
    return x0, y0, x1, y1


def decode_screen(message: dict):
    if message.get("t") != "screen":
        raise ProtocolError("不是画面消息")
    try:
        payload = message.get("jpg", b"")
        if isinstance(payload, str):
            raw = base64.b64decode(payload, validate=True)
        elif isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
        else:
            raise ProtocolError("画面无法解析")
        image = _open_jpeg(raw)
        crop = None
        image_w, image_h = image.width, image.height
        if message.get("cx") is not None:
            crop = (_int_field(message, "cx"), _int_field(message, "cy"), _positive(message, "cw"), _positive(message, "ch"))
            image_w = _positive(message, "w")
            image_h = _positive(message, "h")
        geometry = ViewGeometry(
            origin_x=_int_field(message, "ox"),
            origin_y=_int_field(message, "oy"),
            screen_w=_positive(message, "sw"),
            screen_h=_positive(message, "sh"),
            image_w=image_w,
            image_h=image_h,
            crop=crop,
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
