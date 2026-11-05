# -*- coding: utf-8 -*-
"""用受控超时运行 exe 的自检模式，打印退出码。

用法: python selftest_exe.py [exe路径] [TEMP覆盖值]
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE_DEFAULT = os.path.join(ROOT, "打包", "碧蓝装备排行_单文件版.exe")

exe = sys.argv[1] if len(sys.argv) > 1 else EXE_DEFAULT
temp = sys.argv[2] if len(sys.argv) > 2 else tempfile.gettempdir()

env = dict(os.environ)
env["TEMP"] = env["TMP"] = temp

try:
    p = subprocess.run([exe, "--selftest"], env=env, timeout=90, capture_output=True)
    print("exit:", p.returncode)
    print("stderr:", p.stderr.decode("utf-8", "ignore")[:300])
except subprocess.TimeoutExpired:
    print("TIMEOUT: 自检 90 秒未返回")
    sys.exit(9)
