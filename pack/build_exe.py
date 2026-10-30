"""把一边打成单个 exe。由仓库根目录的两个打包脚本调用。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SHARED_HIDDEN = (
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pynput._util.win32",
    "PIL._tkinter_finder",
    "PIL.ImageGrab",
    "PIL.ImageTk",
)

TARGETS = {
    "host": {
        "name": "局域网键鼠被控端",
        "entry": "host_entry.py",
        "hidden": _SHARED_HIDDEN + ("pystray._win32", "pystray._util.win32"),
    },
    "client": {
        "name": "局域网键鼠控制端",
        "entry": "client_entry.py",
        "hidden": _SHARED_HIDDEN,
    },
}


def _is_windows_dll(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("api-ms-win-") or name == "ucrtbase.dll":
        return True
    windir = os.environ.get("WINDIR", r"C:\Windows").lower()
    return str(path).lower().startswith(windir + "\\")


def is_blocked_binary(name: str) -> bool:
    """Miniconda 里的 api-ms-win 和 ucrtbase 会盖住新电脑上的系统运行库，导致 _tkinter 报找不到模块。"""
    base = Path(name).name.lower()
    return base.startswith("api-ms-win-") or base == "ucrtbase.dll"


def is_conda_prefix(prefix: str) -> bool:
    """Miniconda 的 Tcl 依赖私有运行库。用它打包的程序在没装 Miniconda 的电脑上会报找不到模块。"""
    text = prefix.lower().replace("/", "\\")
    return "\\miniconda" in text or "\\anaconda" in text or "\\conda\\" in text


def _prefer_prefix_dll(path: Path) -> Path | None:
    """搜索路径上可能先碰到 Miniconda 的运行库。打包时改用当前 Python 自己目录里的同名文件。"""
    prefix = Path(getattr(sys, "base_prefix", sys.prefix))
    for candidate in (prefix / path.name, prefix / "DLLs" / path.name, prefix / "Library" / "bin" / path.name):
        if candidate.is_file():
            return candidate
    if is_conda_prefix(str(path)) and not is_conda_prefix(str(prefix)):
        return None
    return path


def tk_binaries() -> list[str]:
    """把 _tkinter 直接依赖的 DLL 收进来。缺了它们，没装 Python 的电脑会报找不到模块。"""
    import _tkinter

    from PyInstaller.depend.bindepend import get_imports

    pending = [Path(_tkinter.__file__)]
    seen: set[Path] = set()
    collected: list[str] = []
    while pending:
        current = pending.pop()
        try:
            imports = get_imports(str(current))
        except Exception:
            continue
        for _name, resolved in imports:
            if not resolved:
                continue
            dependency = _prefer_prefix_dll(Path(resolved))
            if dependency is None or _is_windows_dll(dependency) or is_blocked_binary(dependency.name):
                continue
            key = dependency.resolve()
            if key in seen or not dependency.is_file():
                continue
            seen.add(key)
            collected.append(str(dependency))
            pending.append(dependency)
    runtime = Path(getattr(sys, "base_prefix", sys.prefix)) / "VCRUNTIME140_1.dll"
    if runtime.is_file() and runtime.resolve() not in seen:
        collected.append(str(runtime))
    return collected


def spec_source(kind: str, root: Path | None = None) -> str:
    target = TARGETS[kind]
    root = ROOT if root is None else root
    entry = root / "pack" / target["entry"]
    icon = root / "build" / "icon.ico"
    binaries = [(path, ".") for path in tk_binaries()]
    hidden = list(target["hidden"])
    hook = root / "pack" / "rthook_dll.py"
    return "\n".join([
        "# -*- mode: python ; coding: utf-8 -*-",
        "from PyInstaller.building.datastruct import TOC",
        "",
        "a = Analysis(",
        f"    [{str(entry)!r}],",
        f"    pathex=[{str(root)!r}],",
        f"    binaries={binaries!r},",
        "    datas=[],",
        f"    hiddenimports={hidden!r},",
        "    hookspath=[],",
        "    hooksconfig={},",
        f"    runtime_hooks=[{str(hook)!r}],",
        "    excludes=[],",
        "    noarchive=False,",
        "    optimize=0,",
        ")",
        "",
        "def _ship(item):",
        "    name = item[0].replace('\\\\', '/').rsplit('/', 1)[-1].lower()",
        "    if name.startswith('api-ms-win-') or name == 'ucrtbase.dll':",
        "        return False",
        "    return True",
        "",
        "a.binaries = TOC([item for item in a.binaries if _ship(item)])",
        "pyz = PYZ(a.pure)",
        "exe = EXE(",
        "    pyz,",
        "    a.scripts,",
        "    a.binaries,",
        "    a.datas,",
        "    [],",
        f"    name={target['name']!r},",
        "    debug=False,",
        "    bootloader_ignore_signals=False,",
        "    strip=False,",
        "    upx=False,",
        "    upx_exclude=[],",
        "    runtime_tmpdir=None,",
        "    console=False,",
        "    disable_windowed_traceback=False,",
        "    argv_emulation=False,",
        "    target_arch=None,",
        "    codesign_identity=None,",
        "    entitlements_file=None,",
        f"    icon=[{str(icon)!r}],",
        ")",
        "",
    ])


def pyinstaller_args(kind: str, root: Path | None = None) -> list[str]:
    target = TARGETS[kind]
    root = ROOT if root is None else root
    icon = root / "build" / "icon.ico"
    entry = root / "pack" / target["entry"]
    args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        target["name"],
        "--icon",
        str(icon),
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build" / kind),
        "--specpath",
        str(root / "build"),
        "--paths",
        str(root),
    ]
    for name in target["hidden"]:
        args.extend(("--hidden-import", name))
    args.append(str(entry))
    return args


def _install_build_tools() -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "pyinstaller"])


def _write_icon(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from scrnshr.winutil import make_icon_image

    make_icon_image().save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])


def build(kind: str) -> Path:
    if sys.platform != "win32":
        raise SystemExit("打包只在 Windows 上进行。")
    if kind not in TARGETS:
        raise SystemExit("用法: python pack/build_exe.py host|client")
    if is_conda_prefix(getattr(sys, "base_prefix", sys.prefix)):
        raise SystemExit("不能用 Miniconda 打包。请运行仓库里的打包脚本，它会安装标准 Python 再打包。")
    names = {Path(item).name.lower() for item in tk_binaries()}
    if "tcl86t.dll" not in names and "tcl90.dll" not in names:
        raise SystemExit("没有找到 Tcl 运行库，停止打包。")
    if "tcl86t.dll" in names and "zlib1.dll" not in names:
        raise SystemExit("没有找到 zlib1.dll。没有它，另一台电脑仍会报找不到模块。")
    _install_build_tools()
    icon = ROOT / "build" / "icon.ico"
    _write_icon(icon)
    spec_dir = ROOT / "build"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec = spec_dir / f"{TARGETS[kind]['name']}.spec"
    spec.write_text(spec_source(kind), encoding="utf-8")
    from PyInstaller.__main__ import run

    run([
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / kind),
        str(spec),
    ])
    output = ROOT / "dist" / f"{TARGETS[kind]['name']}.exe"
    if not output.is_file():
        raise SystemExit(f"没有生成 {output}")
    print(f"已生成 {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in TARGETS:
        print("用法: python pack/build_exe.py host|client")
        return 2
    build(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
