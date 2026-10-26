# -*- coding: utf-8 -*-
"""小样本验证：抓若干页并打印解析结果。"""
import json
import sys

sys.path.insert(0, r"G:\azur lane")
from app import core  # noqa: E402

SAMPLE = [
    "100mm88式火炮T0",
    "533mm鱼雷Mk35(4连发射)T0",
    "100mm双联装防空炮SM-5-1sT1",
]

texts = core.fetch_texts(SAMPLE)
print("fetched:", list(texts))
for title, text in texts.items():
    item = core.parse_page(title, text)
    if not item:
        print("!! parse failed:", title)
        continue
    brief = {k: v for k, v in item.items() if k != "raw"}
    print(json.dumps(brief, ensure_ascii=False, indent=1)[:1200])
    print("raw keys:", len(item["raw"]))
