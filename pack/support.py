"""打包后的程序在没有控制台时，用窗口报告启动失败。"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

# 先加载被依赖的库，再加载 Tcl/Tk。官方 Python 用 tcl86t/tk86t，Miniconda 用 tcl90。
RUNTIME_DLLS = (
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
    "zlib.dll",
    "zlib1.dll",
    "libtommath.dll",
    "tcl86t.dll",
    "tk86t.dll",
    "tcl90.dll",
    "tcl9tk90.dll",
)

_prepared = False


def prepare_source_tree() -> None:
    if getattr(sys, "frozen", False):
        return
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)


def imported_dll_names(path: Path) -> list[str]:
    """读出 PE 文件直接依赖的 DLL 名字，用来在加载失败时指出缺的是哪一个。"""
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if len(data) < 0x40 or data[:2] != b"MZ":
        return []
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return []
    coff = e_lfanew + 4
    number_of_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_optional = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    if optional + size_optional > len(data):
        return []
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        directory = optional + 112
    elif magic == 0x10B:
        directory = optional + 96
    else:
        return []
    if directory + 16 > len(data):
        return []
    import_rva = struct.unpack_from("<I", data, directory + 8)[0]
    if import_rva == 0:
        return []
    sections = []
    section_off = optional + size_optional
    for index in range(number_of_sections):
        off = section_off + index * 40
        if off + 24 > len(data):
            return []
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, off + 8)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def rva_to_offset(rva: int) -> int | None:
        for virtual_address, span, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + span:
                return raw_pointer + (rva - virtual_address)
        return None

    cursor = rva_to_offset(import_rva)
    if cursor is None:
        return []
    names: list[str] = []
    while cursor + 20 <= len(data):
        name_rva = struct.unpack_from("<I", data, cursor + 12)[0]
        first_thunk = struct.unpack_from("<I", data, cursor + 16)[0]
        if name_rva == 0 and first_thunk == 0:
            break
        name_off = rva_to_offset(name_rva)
        if name_off is None or name_off >= len(data):
            break
        end = data.find(b"\0", name_off)
        if end == -1:
            break
        names.append(data[name_off:end].decode("ascii", "replace"))
        cursor += 20
    return names


def prepare_dlls() -> None:
    """在导入 tkinter 之前，按完整路径加载 Tcl。新电脑的搜索路径找不到它们时，就会报找不到模块。"""
    global _prepared
    if _prepared or not getattr(sys, "frozen", False):
        return
    _prepared = True
    folder = Path(getattr(sys, "_MEIPASS"))
    folder_text = str(folder)
    os.environ["PATH"] = folder_text + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(folder_text)
    kernel = ctypes_kernel()
    kernel.SetDllDirectoryW(folder_text)
    if not any((folder / name).is_file() for name in ("tcl86t.dll", "tcl90.dll")):
        _fail("程序里没有 Tcl 运行库。请用仓库里的打包脚本重新生成，不要用 Miniconda 直接打包。")
    for name in RUNTIME_DLLS:
        path = folder / name
        if not path.is_file():
            continue
        if kernel.LoadLibraryW(str(path)):
            continue
        _fail(_why_unloaded(path, kernel, set()))


def ctypes_kernel():
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LoadLibraryW.argtypes = (ctypes.c_wchar_p,)
    kernel.LoadLibraryW.restype = ctypes.c_void_p
    kernel.SetDllDirectoryW.argtypes = (ctypes.c_wchar_p,)
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    return kernel


def _why_unloaded(path: Path, kernel, seen: set[str]) -> str:
    import ctypes

    key = str(path.resolve()).lower()
    if key in seen:
        return path.name
    seen.add(key)
    for name in imported_dll_names(path):
        sibling = path.parent / name
        if sibling.is_file():
            if kernel.LoadLibraryW(str(sibling)):
                continue
            return f"{path.name} 依赖的 {_why_unloaded(sibling, kernel, seen)} 没有加载成功"
        if kernel.LoadLibraryW(name):
            continue
        return f"{path.name} 找不到 {name}"
    return f"{path.name} 加载失败（Windows 错误 {ctypes.get_last_error()}）"


def _fail(detail: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, "窗口组件没有加载成功。\n" + detail, "局域网键鼠", 0x00000010)
    os._exit(1)


def launch(run) -> int:
    prepare_source_tree()
    if sys.platform != "win32":
        return 2
    try:
        run()
    except Exception as exc:
        from scrnshr.__main__ import _report

        _report(exc)
        return 1
    return 0
