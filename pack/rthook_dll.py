"""在主脚本导入 tkinter 之前，把随程序带上的 Tcl 运行库加载进来。"""

from pack.support import prepare_dlls

prepare_dlls()
