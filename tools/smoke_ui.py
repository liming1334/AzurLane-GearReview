# -*- coding: utf-8 -*-
"""界面自检：支持分类 / 主题，截图后退出。

用法:
    python smoke_ui.py [分类] [输出] [--night] [--kw=词]
"""
import sys
import traceback

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

sys.path.insert(0, r"G:\azur lane")

from app import ui  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = [a for a in sys.argv[1:] if a.startswith("--")]
CAT = args[0] if args else ""
OUT = args[1] if len(args) > 1 else r"G:\azur lane\.tmp\shot.png"
NIGHT = "--night" in flags
KW = ""
for f in flags:
    if f.startswith("--kw="):
        KW = f.split("=", 1)[1]


def setup():
    want = "night" if NIGHT else "day"
    if app.theme_key != want:
        app.theme_key = want
        app._apply_theme()
        app.refresh()
    if CAT:
        app.var_cat.set(CAT)
        app._sync_types()
        app.recompute()
    if KW:
        app.var_kw.set(KW)
        app.refresh()
    app.lift()
    app.attributes("-topmost", True)
    app.focus_force()


def shoot():
    try:
        from PIL import ImageGrab
        app.update_idletasks()
        app.update()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        img.save(OUT)
        print("screenshot:", OUT, img.size)
    except Exception:
        traceback.print_exc()


app = ui.App()
app.after(600, setup)
app.after(2200, shoot)
app.after(3200, lambda: (app.destroy(), print("closed")))
app.mainloop()
