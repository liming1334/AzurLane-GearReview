# -*- coding: utf-8 -*-
"""从原始图片生成应用图标 assets/app.ico 与 assets/app.png。

用法:
    python tools/make_icon.py [源图路径]

默认源图是项目根目录下的 `azur lane.jpg`。
生成的 ico 含 16/24/32/48/64/128/256 七个尺寸：
  * 256 是资源管理器大图标 / 任务栏高 DPI 用
  * 32/16 是标题栏与任务栏常规尺寸用
缺小尺寸时 Windows 只能靠缩放，会糊。
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def default_source() -> str:
    """默认源图：优先项目根目录的 `azur lane.jpg`，其次是 assets 里的那份。"""
    for cand in (os.path.join(ROOT, "azur lane.jpg"),
                 os.path.join(ASSETS, "app_source.jpg")):
        if os.path.exists(cand):
            return cand
    return os.path.join(ROOT, "azur lane.jpg")


SRC = sys.argv[1] if len(sys.argv) > 1 else default_source()


def load_square(path: str) -> Image.Image:
    """读图并居中裁成正方形（ico 只能是方的，非方图会被拉伸变形）。"""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((256, 256), Image.LANCZOS)


def main() -> int:
    if not os.path.exists(SRC):
        print("找不到源图:", SRC)
        return 1
    os.makedirs(ASSETS, exist_ok=True)
    base = load_square(SRC)
    ico = os.path.join(ASSETS, "app.ico")
    base.save(ico, sizes=SIZES)
    base.save(os.path.join(ASSETS, "app.png"))
    print("源图:", SRC)
    print("图标:", ico, os.path.getsize(ico), "bytes | 尺寸:", SIZES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
