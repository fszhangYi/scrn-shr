@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\pythonw.exe" (
  echo 正在准备运行环境...
  python -m venv .venv
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
start "" /D "%~dp0" ".venv\Scripts\pythonw.exe" -m scrnshr host
exit /b 0
:fail
echo 启动失败。请确认已经安装 Python 3，并且当前目录可以创建虚拟环境。
pause
exit /b 1