# -*- coding: utf-8 -*-
"""打印几类装备的原始字段，确认数据结构。"""
import json
import sys

sys.path.insert(0, r"G:\azur lane")

data = json.load(open(r"G:\azur lane\data\equipment.json", encoding="utf-8"))
items = data["items"]

want = {"战斗机": None, "轰炸机": None, "鱼雷机": None, "水上机": None, "反潜机": None}
for it in items:
    t = it["type"]
    if t in want and want[t] is None:
        want[t] = it

for t, it in want.items():
    if not it:
        print(f"--- {t}: 无样本 ---")
        continue
    print(f"\n===== {t}: {it['name']} =====")
    for k, v in it["raw"].items():
        if v and str(v).strip():
            print(f"  {k} = {v}")

print("\n===== 舰炮弹药样例（强化档位） =====")
for it in items:
    if it["category"] == "舰炮" and it["rarity"] == "金色":
        print(f"\n[{it['name']}]")
        for k, v in it["raw"].items():
            if any(s in k for s in ("伤害", "射速", "补正")):
                print(f"  {k} = {v}")
        break
