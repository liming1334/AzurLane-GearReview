# -*- coding: utf-8 -*-
"""下载装备图标：文件:装备名.jpg → 48×48 PNG，并生成 icons.json。"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

sys.path.insert(0, r"G:\azur lane")
from app import core  # noqa: E402

OUT_DIR = r"G:\azur lane\assets\icons"
SIZE = 48


def fetch_imageinfo(titles: list[str]) -> dict:
    out = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        data = core.api_get({
            "action": "query", "prop": "imageinfo", "titles": "|".join(batch),
            "iiprop": "url", "iiurlwidth": "64",
        })
        for page in data.get("query", {}).get("pages", []):
            if page.get("missing"):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url:
                out[page["title"]] = url
        time.sleep(0.2)
    return out


def download(url: str) -> bytes | None:
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": core.UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return None


def to_png(blob: bytes) -> bytes:
    img = Image.open(io.BytesIO(blob)).convert("RGBA")
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main():
    items, _ = core.load_data()
    names = [it["name"] for it in items]
    print(f"装备 {len(names)} 件")

    jpg_titles = [f"文件:{n}.jpg" for n in names]
    info = fetch_imageinfo(jpg_titles)
    print(f"jpg 命中 {len(info)}")

    missing = [n for n in names if f"文件:{n}.jpg" not in info]
    if missing:
        png_titles = [f"文件:{n}.png" for n in missing]
        info_png = fetch_imageinfo(png_titles)
        print(f"png 补齐 {len(info_png)}")
        info.update(info_png)

    os.makedirs(OUT_DIR, exist_ok=True)
    mapping: dict[str, str] = {}
    fails: list[str] = []

    def work(name: str):
        title = f"文件:{name}.jpg"
        url = info.get(title) or info.get(f"文件:{name}.png")
        if not url:
            fails.append(name)
            return
        blob = download(url)
        if not blob:
            fails.append(name)
            return
        try:
            png = to_png(blob)
        except Exception:  # noqa: BLE001
            fails.append(name)
            return
        fname = hashlib.md5(name.encode("utf-8")).hexdigest()[:16] + ".png"
        with open(os.path.join(OUT_DIR, fname), "wb") as f:
            f.write(png)
        mapping[name] = fname

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, names))

    with open(os.path.join(OUT_DIR, "icons.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)

    total = sum(os.path.getsize(os.path.join(OUT_DIR, v)) for v in mapping.values())
    print(f"成功 {len(mapping)} / {len(names)}，失败 {len(fails)}，合计 {total / 1024 / 1024:.2f} MB")
    if fails[:10]:
        print("失败示例:", fails[:10])


if __name__ == "__main__":
    main()
