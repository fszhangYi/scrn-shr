@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "build\cpython\python.exe" (
  echo 正在安装标准 Python，只用它打包，避免带上 Miniconda 的运行库。
  mkdir build 2>nul
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile 'build\python-setup.exe'"
  if errorlevel 1 goto fail
  "build\python-setup.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_pip=1 Include_tcltk=1 TargetDir="%CD%\build\cpython"
  if not exist "build\cpython\python.exe" goto fail
)
if not exist "build\packvenv\Scripts\python.exe" (
  echo 正在准备打包环境...
  "build\cpython\python.exe" -m venv "build\packvenv"
  if errorlevel 1 goto fail
)
echo 正在打包被控端。这台电脑需要 Python，生成的程序不需要。
"build\packvenv\Scripts\python.exe" pack\build_exe.py host
if errorlevel 1 goto fail
echo.
echo 程序在 dist 目录，文件名带有打包时间。请复制上面打印的那个 exe。
if not defined SCRNSHR_NO_PAUSE pause
exit /b 0
:fail
echo 打包失败。
pause
exit /b 1
