# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico。"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT = r"G:\azur lane\assets"
os.makedirs(OUT, exist_ok=True)
SIZE = 256

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 深蓝圆底 + 渐变描边
for i in range(SIZE // 2, 0, -1):
    t = i / (SIZE / 2)
    r = int(31 + (58 - 31) * (1 - t))
    g = int(58 + (111 - 58) * (1 - t))
    b = int(95 + (181 - 95) * (1 - t))
    d.ellipse([SIZE / 2 - i, SIZE / 2 - i, SIZE / 2 + i, SIZE / 2 + i], fill=(r, g, b, 255))

d.ellipse([16, 16, SIZE - 16, SIZE - 16], outline=(255, 255, 255, 90), width=4)

# 主炮剪影
barrel = [(128, 60), (150, 60), (150, 150), (128, 150)]
d.polygon([(120, 52), (156, 52), (150, 96), (126, 96)], fill=(255, 255, 255, 235))
d.rectangle([116, 104, 160, 132], fill=(255, 255, 255, 235))
d.ellipse([100, 128, 176, 200], fill=(255, 255, 255, 235))
d.ellipse([124, 152, 152, 180], fill=(31, 58, 95, 255))

# 底部刻度（排行意象）
for i, h in enumerate([12, 22, 34]):
    x = 66 + i * 46
    d.rectangle([x, 224 - h, x + 30, 224], fill=(255, 255, 255, 220))

img.save(os.path.join(OUT, "app.ico"),
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(OUT, "app.png"))
print("icon ->", os.path.join(OUT, "app.ico"))
