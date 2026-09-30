import os
import sys


def data_path(relative: str = "") -> str:
    """返回数据文件的绝对路径，兼容开发环境和 PyInstaller 打包环境。"""
    if getattr(sys, "_MEIPASS", False):
        base = sys._MEIPASS
    else:
        current_file = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(os.path.dirname(current_file))
    return os.path.join(base, relative) if relative else base
