# -*- coding: utf-8 -*-
"""全量抓取并写入 data/equipment.json。"""
import sys
import time

sys.path.insert(0, r"G:\azur lane")
from app import core  # noqa: E402


def main():
    t0 = time.time()
    last = [0.0]

    def progress(stage, done, total):
        now = time.time()
        if now - last[0] > 2 or done >= total:
            last[0] = now
            print(f"{stage}: {done}/{total}", flush=True)

    items = core.scrape(progress)
    path = core.save_cache(items)
    cats = {}
    for it in items:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
    print(f"\n总条目: {len(items)}")
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"输出: {path}")
    print(f"耗时: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
