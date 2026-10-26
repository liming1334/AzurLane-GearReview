# -*- coding: utf-8 -*-
"""自检：打开 60 秒输出弹窗并截图。"""
import sys
import traceback

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

sys.path.insert(0, r"G:\azur lane")

from app import ui  # noqa: E402


def raise_window():
    app.lift()
    app.attributes("-topmost", True)
    app.focus_force()
    app.open_sim()


def shoot():
    try:
        from PIL import ImageGrab
        top = app.winfo_children()
        win = None
        for w in top:
            if w.winfo_class() == "Toplevel" and w.winfo_ismapped():
                win = w
        if win:
            win.lift()
            win.attributes("-topmost", True)
            win.update_idletasks()
            win.update()
            x, y = win.winfo_rootx(), win.winfo_rooty()
            w_, h_ = win.winfo_width(), win.winfo_height()
            img = ImageGrab.grab(bbox=(x, y, x + w_, y + h_))
            out = r"G:\azur lane\.tmp\sim_shot.png"
            img.save(out)
            print("sim screenshot:", out, img.size)
        else:
            print("no toplevel window found")
    except Exception:
        traceback.print_exc()


app = ui.App()
app.after(600, raise_window)
app.after(1800, shoot)
app.after(2800, lambda: (app.destroy(), print("closed")))
app.mainloop()
