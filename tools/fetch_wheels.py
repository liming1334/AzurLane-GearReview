"""Download PyInstaller wheels from PyPI and unzip them into ./vendor (no pip)."""
import json, sys, urllib.request, zipfile, io, os, re

PKGS = ["pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
        "pywin32-ctypes", "packaging", "setuptools"]

DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wheel-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick(urls):
    cands = [u for u in urls if u["filename"].endswith(".whl")]
    # prefer universal or win_amd64 wheels for cp312
    def score(u):
        fn = u["filename"]
        s = 0
        if "py3-none-any" in fn:
            s += 3
        if "none-win_amd64" in fn:
            s += 5
        if "cp312" in fn:
            s += 4
        if "cp3" in fn and "cp312" not in fn:
            s -= 2
        return s
    cands.sort(key=score, reverse=True)
    return cands[0] if cands else None


def main():
    os.makedirs(DEST, exist_ok=True)
    for pkg in PKGS:
        try:
            data = get_json(f"https://pypi.org/pypi/{pkg}/json")
            ver = data["info"]["version"]
            rel = data["releases"].get(ver) or []
            whl = pick(rel)
            if not whl:
                print(f"[skip] {pkg}: no wheel")
                continue
            print(f"[get ] {pkg} {ver} -> {whl['filename']}")
            req = urllib.request.Request(whl["url"], headers={"User-Agent": "wheel-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                blob = r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                z.extractall(DEST)
            print(f"[ok  ] {pkg} ({len(blob)//1024} KB)")
        except Exception as e:
            print(f"[FAIL] {pkg}: {e}")


if __name__ == "__main__":
    main()
