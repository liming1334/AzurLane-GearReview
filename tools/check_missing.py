# -*- coding: utf-8 -*-
"""列出未能解析的页面，看看它们用了什么模板。"""
import sys

sys.path.insert(0, r"G:\azur lane")
from app import core  # noqa: E402


def main():
    items, _ = core.load_data()
    have = {it["name"] for it in items}
    titles = []
    for cat in ("Category:装备", "Category:特殊兵装"):
        titles += core.list_category(cat)
    missing = [t for t in titles if t not in have]
    print(f"目录 {len(titles)} 页，已解析 {len(have)}，缺失 {len(missing)}")
    texts = core.fetch_texts(missing) if missing else {}
    for t in missing:
        txt = texts.get(t, "")
        head = " ".join(txt.split())[:160]
        print(f"\n[{t}]\n  {head}")


if __name__ == "__main__":
    main()
