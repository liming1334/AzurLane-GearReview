# -*- coding: utf-8 -*-
"""诊断：检查数据加载与筛选结果。"""
import sys

sys.path.insert(0, r"G:\azur lane")

from app import core, ui  # noqa: E402

print("data_dir:", core.data_dir())
print("cache:", core.cache_path())
items, tag = core.load_data()
print("load_data ->", len(items), repr(tag))
if items:
    print("sample:", items[0]["name"], items[0]["category"])

app = ui.App()
print("app.items:", len(app.items))
print("app.rows:", len(app.rows))
print("tree children:", len(app.tree.get_children()))
print("type filter:", app.var_type.get())
print("label:", app.lbl_data.cget("text"))
print("geometry:", app.winfo_geometry())
app.update()
print("after update geometry:", app.winfo_geometry())
app.destroy()
