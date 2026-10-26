# -*- coding: utf-8 -*-
"""碧蓝航线装备性能排行工具 —— 程序入口。"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from app.ui import run  # noqa: E402


def selftest() -> int:
    """打包后自检：验证联网抓取链路是否可用。"""
    from app import core
    try:
        texts = core.fetch_texts(["100mm88式火炮T0"])
        if texts:
            return 0
        return 3
    except Exception:  # noqa: BLE001
        return 4


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    run()
