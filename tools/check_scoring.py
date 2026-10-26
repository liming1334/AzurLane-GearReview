# -*- coding: utf-8 -*-
"""校验新评分：舰炮 77 秒伤害、舰载机单轮挂载、鱼雷弹药。"""
import sys

sys.path.insert(0, r"G:\azur lane")
from app import core  # noqa: E402

items, tag = core.load_data()
print("条目:", len(items), tag)
p = core.default_params()
core.score_all(items, p)

guns = [i for i in items if i["category"] == "舰炮" and i["score"]]
guns.sort(key=lambda i: -i["score"]["轻甲"]["value"])
print("\n--- 舰炮 前 5（77 秒轻甲伤害）---")
for g in guns[:5]:
    s = g["score"]["轻甲"]
    print(f"{g['name']:<34} {s['value']:>10,.0f}  单轮 {s['volley']:.1f} × {s['shots']}发 "
          f"（间隔 {s['cycle']:.2f}s, 等级+{s['level_used']}）")

planes = [i for i in items if i["category"] == "舰载机"]
with_score = [i for i in planes if i["score"]]
print(f"\n--- 舰载机 {len(with_score)}/{len(planes)} 有评分 ---")
for pl in with_score[:6]:
    sc = pl["score"]
    aa = sc.get("对空", {}).get("value", 0)
    light = sc.get("轻甲", {}).get("value", 0)
    print(f"{pl['name']:<30} 对空 {aa:>8.1f}  轻 {light:>8.1f}  "
          f"中 {sc.get('中甲', {}).get('value', 0):>8.1f}  重 {sc.get('重甲', {}).get('value', 0):>8.1f}")
    for m in (pl.get("mounts") or {}).get("bomb", [])[:2]:
        print(f"    炸弹 {m['count']}×{m['name']}  伤害表档位 {sorted(m['damage'])[-3:]}  对甲 {m['armor']}")

torps = [i for i in items if i["category"] == "鱼雷"]
print(f"\n--- 鱼雷 {len(torps)} 件，弹药分布 ---")
from collections import Counter
print(Counter(t["ammo"] for t in torps))
