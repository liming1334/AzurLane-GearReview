# -*- coding: utf-8 -*-
"""端到端验证：启动指定 exe，聚焦窗口并截图。

用法:
    python test_exe.py [exe路径] [TEMP覆盖值]
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

EXE_DEFAULT = r"G:\azur lane\dist\碧蓝装备排行\碧蓝装备排行.exe"
TITLE_KEY = "装备性能排行"

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
SW_RESTORE = 9


def find_window(key):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if key in buf.value and user32.IsWindowVisible(hwnd):
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else EXE_DEFAULT
    temp = sys.argv[2] if len(sys.argv) > 2 else r"G:\azur lane\.tmp"
    out = sys.argv[3] if len(sys.argv) > 3 else r"G:\azur lane\.tmp\exe_shot.png"

    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = temp

    proc = subprocess.Popen([exe], env=env)
    hwnd, title = None, ""
    for _ in range(80):
        time.sleep(0.5)
        if proc.poll() is not None:
            print("FAIL: 进程已退出，退出码", proc.returncode)
            return 1
        wins = find_window(TITLE_KEY)
        if wins:
            hwnd, title = wins[0]
            break
    if not hwnd:
        print("FAIL: 未找到窗口")
        proc.kill()
        return 1

    print("窗口标题:", title)
    time.sleep(3.0)

    sys.path.insert(0, r"G:\azur lane\tools")
    import capture
    img = capture.grab(hwnd)
    img.save(out)
    print("size:", img.size, "->", out)

    time.sleep(0.5)
    alive = proc.poll() is None
    print("进程存活:", alive, "| 使用 TEMP:", temp)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return 0 if alive else 2


if __name__ == "__main__":
    sys.exit(main())
