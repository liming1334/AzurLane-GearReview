# -*- coding: utf-8 -*-
"""生成一张 1920×1080 的示例壁纸，用于测试背景功能。"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
OUT = r"G:\azur lane\.tmp\wallpaper.jpg"

img = Image.new("RGB", (W, H), (10, 26, 48))
d = ImageDraw.Draw(img)

# 渐变底色
for y in range(H):
    t = y / H
    r = int(12 + 40 * t)
    g = int(30 + 70 * t)
    b = int(60 + 120 * t)
    d.line([(0, y), (W, y)], fill=(r, g, b))

# 光斑
for cx, cy, rad, col in ((380, 260, 320, (60, 140, 220)),
                         (1500, 780, 420, (30, 90, 160)),
                         (1100, 200, 240, (90, 170, 230))):
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)
    layer = layer.filter(ImageFilter.GaussianBlur(160))
    img = Image.blend(img, Image.blend(img, layer, 0.55), 0.6)

# 波纹
d = ImageDraw.Draw(img)
for i in range(14):
    y = 700 + i * 26
    d.arc([-200 + i * 30, y, W + 200 - i * 30, y + 300], 200, 340,
          fill=(70, 120, 180), width=2)

img = img.filter(ImageFilter.GaussianBlur(0.6))
img.save(OUT, quality=88)
print("wallpaper ->", OUT, img.size, os.path.getsize(OUT) // 1024, "KB")
