"""生成 README 用的截图（白天 / 夜间）。

PrintWindow 抓 Canvas 自绘区域会发黑，所以改用全屏 ImageGrab + 按窗口的
物理像素矩形裁剪，并去掉标题栏。

用法: python tools/shot_readme.py
输出: assets/preview.png、assets/preview_night.png
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须先声明 DPI 感知：否则 GetWindowRect 返回逻辑坐标，和 ImageGrab 的物理像素对不上，
# 截出来的图会整体错位
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # noqa: BLE001
    pass

from PIL import ImageGrab  # noqa: E402

from app.ui import App  # noqa: E402

user32 = ctypes.windll.user32


def shoot(category: str, theme: str, out: str):
    app = App()
    app.theme_key = theme
    app._apply_theme()
    app.var_cat.set(category)
    app._sync_types()
    app.refresh()
    app.update()
    app.update_idletasks()
    time.sleep(1.0)
    app.update()
    time.sleep(0.5)

    hwnd = int(app.wm_frame(), 16)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
    # 去掉标题栏（约 32px）和窗口边框的 3px 毛边
    top, inset = 32, 3
    if img.height > top + 100:
        img = img.crop((inset, top, img.width - inset, img.height - inset))
    img.save(out)
    print("saved", out, img.size)
    app.destroy()


shoot("舰炮", "day", os.path.join(ROOT, "assets", "preview.png"))
time.sleep(0.5)
shoot("舰载机", "night", os.path.join(ROOT, "assets", "preview_night.png"))
