# -*- coding: utf-8 -*-
"""
==============================================================================
碧蓝航线装备性能排行 —— 图形界面
==============================================================================

界面结构
--------
┌──────────────────────────────────────────────────────────────┐
│ 顶栏：标题 / 主题切换 / 背景设置 / 数据时间                    │
├──────────────────────────────────────────────────────────────┤
│ 筛选栏：搜索 分类 类型 稀有度 阵营 鱼雷弹药 仅显示可评分        │
├──────────────────────────────────────────────────────────────┤
│ 参数栏：炮击 雷击 防空 航空 装填值 属性效率 增伤 暴击 强化      │
├───────────────────────────┬──────────────────────────────────┤
│ 排行表（Treeview）         │ 装备详情（卡片式，可滚动）        │
└───────────────────────────┴──────────────────────────────────┘

关键设计
--------
* 主题：白天（白 + 天蓝）/ 夜间（灰黑 + 深蓝），所有颜色集中在 THEMES，
  切换时统一刷新 ttk 样式与已注册控件的背景/前景色。
* 背景：支持自定义图片（1920×1080 为基准），按窗口尺寸「覆盖裁切」，
  并按当前主题叠加一层色调，保证前景可读；同时裁一块铺到详情画布上。
* 详情：卡片式布局，随选中装备重建，因此天然跟随主题。
==============================================================================
"""
from __future__ import annotations

import csv
import json
import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import core

try:  # 背景图需要 Pillow（打包时已内置）
    from PIL import Image, ImageFilter, ImageTk
    HAS_PIL = True
except Exception:  # noqa: BLE001
    HAS_PIL = False

FONT = "Microsoft YaHei UI"

# ---------------------------------------------------------------------------
# 主题配色
# 每个 token 都会被界面引用，新增 token 时记得两套主题都补齐
# ---------------------------------------------------------------------------
THEMES = {
    "day": {
        "label": "白天",
        "window": "#e9f4fe",        # 窗口底色（浅天蓝）
        "panel": "#ffffff",         # 面板底色
        "card": "#ffffff",          # 卡片底色
        "line": "#cfe3f7",          # 描边
        "header1": "#2f7fc4",       # 顶栏
        "header2": "#1b4f86",
        "header_fg": "#ffffff",
        "header_sub": "#bcdcfa",
        "text": "#22364f",
        "muted": "#7b8ea8",
        "accent": "#2f8fd8",
        "accent_bg": "#e7f3fd",
        "good": "#1e8449",
        "good_bg": "#eaf7ef",
        "warn": "#c0392b",
        "gold": "#b9770e",
        "tile": "#f4faff",
        "tile_line": "#d5e8fa",
        "tree_bg": "#ffffff",
        "tree_head": "#e9f4fd",
        "tree_stripe": "#f6fbff",
        "select": "#cfe7fb",
        "chip1_bg": "#e7f3fd", "chip1_fg": "#2f8fd8",
        "chip2_bg": "#eaf7ef", "chip2_fg": "#1e8449",
        "chip3_bg": "#fdf5e6", "chip3_fg": "#b9770e",
        "chip4_bg": "#f3eefb", "chip4_fg": "#7c4dbb",
        "status": "#dfeefb",
        "status_fg": "#41586f",
        "wall_alpha": 0.22,         # 背景叠加主题色的比例
    },
    "night": {
        "label": "夜间",
        "window": "#12161d",        # 灰黑
        "panel": "#1b212b",
        "card": "#222936",
        "line": "#2f3a4d",
        "header1": "#1d2f4d",       # 深蓝
        "header2": "#0f1a2b",
        "header_fg": "#dbe7f7",
        "header_sub": "#8fb0d4",
        "text": "#d9e3f0",
        "muted": "#8b9bb2",
        "accent": "#5a9bd8",
        "accent_bg": "#1f2b3d",
        "good": "#5fbf8a",
        "good_bg": "#1d2f26",
        "warn": "#e2705f",
        "gold": "#e0b050",
        "tile": "#1d2531",
        "tile_line": "#2e3b4f",
        "tree_bg": "#1b212b",
        "tree_head": "#242e3d",
        "tree_stripe": "#1e2531",
        "select": "#2c4a6e",
        "chip1_bg": "#1f2b3d", "chip1_fg": "#7fb6e8",
        "chip2_bg": "#1d2f26", "chip2_fg": "#6fcb98",
        "chip3_bg": "#2e2a1c", "chip3_fg": "#e0b050",
        "chip4_bg": "#2a2233", "chip4_fg": "#b08bdd",
        "status": "#1a2331",
        "status_fg": "#9fb3cc",
        "wall_alpha": 0.42,
    },
}

# 稀有度文字颜色（两套主题共用，夜间也够亮）
RARITY_COLOR = {
    "白色": "#9aa4b2", "蓝色": "#4c9be8", "紫色": "#b07cd8",
    "金色": "#d4a017", "彩色": "#e8664a",
}

# 详情的「完整属性」展示顺序
DETAIL_ORDER = [
    "名称", "类型", "特性", "稀有度", "所属阵营", "伤害", "强化+3伤害", "强化+6伤害",
    "强化+10伤害", "强化+13伤害", "标准射速", "强化+3射速", "强化+6射速",
    "强化+10射速", "强化+13射速", "迎击标准射速", "炮击", "雷击", "防空", "航空",
    "命中", "装填", "机动", "耐久", "弹药", "飞行速度", "鱼雷航速",
    "对甲比例", "伤害范围", "散布范围", "索敌范围", "索敌角度", "弹药射程",
    "散布角度", "伤害补正", "强化+7伤害补正", "强化+11伤害补正",
    "强化+13伤害补正", "瞄准提前量", "技能名", "技能描述", "适用舰种",
    "主武器适用", "副武器适用", "禁用舰种", "所属科技箱", "整装获取",
    "设计图掉落", "其他设计图获取方式", "属性", "兵装效果", "专属角色",
    "舰载机耐久", "舰载机航速", "舰载机回避上限", "机枪", "炸弹", "鱼雷", "备注",
]

SCORE_KEYS = ("对空", "轻甲", "中甲", "重甲")

# 排行表列定义： (列名, 宽度, 对齐)
COLUMNS = [
    ("排名", 44, "center"),
    ("类型", 66, "center"),
    ("稀有度", 52, "center"),
    ("单轮基础", 72, "center"),
    ("评分·对空", 74, "center"),
    ("评分·轻甲", 74, "center"),
    ("评分·中甲", 74, "center"),
    ("评分·重甲", 74, "center"),
]

LEVEL_CHOICES = ["无强化", "+3", "+6", "+7", "+10", "+11", "+13"]

BG_SETTING = "background.json"


class App(tk.Tk):
    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.title("碧蓝航线 装备性能排行工具")
        self._center(1440, 900)
        self.minsize(1120, 680)

        # 运行状态
        self.items: list[dict] = []
        self.rows: list[dict] = []
        self.selected: dict | None = None
        self.sort_col = "评分·轻甲"
        self.sort_desc = True
        self.queue: queue.Queue = queue.Queue()
        self._busy = False

        # 图标缓存（48px 原图 + 24px 缩略）
        self.icon_map = core.load_icon_map()
        self._icon_small_cache: dict[str, object] = {}
        self._icon_big_cache: dict[str, object] = {}

        # 主题与背景
        self.theme_key = "day"
        self.theme = THEMES[self.theme_key]
        self._themed: list[tuple[tk.Widget, dict]] = []
        self._bg_source = None          # PIL Image
        self._bg_fit = None             # 按窗口尺寸裁切后的 PIL Image
        self._bg_photo = None           # 根窗口底图
        self._canvas_wall = None        # 详情画布底图
        self._bg_path = self._read_bg_setting()

        self.params = core.default_params()
        self._load_settings()

        self.style = ttk.Style(self)
        self._apply_ttk_style()
        self._build_ui()
        self._load_data()
        self.after(60, self._init_sash)
        self.after(120, self._poll_queue)
        self.after(200, self._load_background)

    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 60)
        self.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 2 - 10, 0)}")

    def _init_sash(self):
        """左侧表格约占 2/3，右侧详情留 1/3。"""
        try:
            w = self._body.winfo_width()
            if w > 200:
                self._body.sashpos(0, max(int(w * 0.66), 780))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------
    def _apply_ttk_style(self):
        """刷新 ttk 控件（表格、下拉框、输入框、滚动条）的颜色。"""
        t = self.theme
        s = self.style
        # 下拉列表（popdown）属于 Tk 原生 Listbox，只能用 option 数据库着色
        self.option_add("*TCombobox*Listbox.background", t["panel"])
        self.option_add("*TCombobox*Listbox.foreground", t["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", font=(FONT, 9), background=t["window"], foreground=t["text"])
        s.configure("TFrame", background=t["window"])
        s.configure("TLabel", background=t["window"], foreground=t["text"])
        s.configure("TButton", font=(FONT, 9), padding=(10, 4),
                    background=t["panel"], foreground=t["text"],
                    bordercolor=t["line"], lightcolor=t["panel"], darkcolor=t["line"])
        s.map("TButton", background=[("active", t["accent_bg"]),
                                     ("pressed", t["select"])],
              foreground=[("disabled", t["muted"])])
        s.configure("Accent.TButton", font=(FONT, 9, "bold"), padding=(12, 5),
                    background=t["accent"], foreground="#ffffff",
                    bordercolor=t["accent"])
        s.map("Accent.TButton", background=[("active", t["header1"])])
        s.configure("TCombobox", padding=3, fieldbackground=t["panel"],
                    background=t["panel"], foreground=t["text"],
                    arrowcolor=t["muted"], bordercolor=t["line"])
        # clam 自带 readonly 状态映射（浅灰），必须覆盖，否则只读下拉框会是白底
        s.map("TCombobox",
              fieldbackground=[("readonly", t["panel"]), ("disabled", t["window"])],
              foreground=[("readonly", t["text"]), ("disabled", t["muted"])],
              background=[("readonly", t["panel"]), ("active", t["panel"]),
                          ("pressed", t["panel"])],
              arrowcolor=[("readonly", t["muted"]), ("active", t["accent"])],
              selectbackground=[("readonly", t["select"])],
              selectforeground=[("readonly", t["text"])])
        s.map("TEntry",
              fieldbackground=[("disabled", t["window"])],
              foreground=[("disabled", t["muted"])])
        s.configure("TEntry", padding=3, fieldbackground=t["panel"],
                    foreground=t["text"], insertcolor=t["text"], bordercolor=t["line"])
        s.configure("Treeview", font=(FONT, 9), rowheight=30,
                    background=t["tree_bg"], fieldbackground=t["tree_bg"],
                    foreground=t["text"], borderwidth=0)
        s.configure("Treeview.Heading", font=(FONT, 9, "bold"),
                    background=t["tree_head"], foreground=t["text"], padding=6,
                    relief="flat")
        s.map("Treeview",
              background=[("selected", t["select"])],
              foreground=[("selected", t["text"])])
        s.configure("TScrollbar", background=t["tree_head"], troughcolor=t["window"],
                    bordercolor=t["window"], arrowcolor=t["muted"])
        s.configure("TProgressbar", background=t["accent"])

        # 行条纹 + 稀有度前景：按「稀有度|奇偶」组合注册
        if hasattr(self, "tree"):
            for rar, color in RARITY_COLOR.items():
                for parity, bg in (("e", t["tree_bg"]), ("o", t["tree_stripe"])):
                    self.tree.tag_configure(f"{rar}|{parity}", foreground=color,
                                            background=bg)

    def _label(self, parent, text="", *, bg="card", fg="text", font=None, **kw):
        """创建并登记一个会跟随主题的 Label。"""
        lbl = tk.Label(parent, text=text, bg=self.theme[bg], fg=self.theme[fg],
                       font=font or (FONT, 9), **kw)
        self._themed.append((lbl, {"bg": bg, "fg": fg}))
        return lbl

    def _frame(self, parent, token="card", **kw):
        f = tk.Frame(parent, bg=self.theme[token], **kw)
        self._themed.append((f, {"bg": token}))
        return f

    def _button(self, parent, text, command, *, bg="accent_bg", fg="accent",
                hover=None, font=None, padx=10, pady=3):
        btn = tk.Button(parent, text=text, command=command,
                        bg=self.theme[bg], fg=self.theme[fg],
                        activebackground=self.theme[hover or bg],
                        activeforeground=self.theme[fg],
                        font=font or (FONT, 8), bd=0, relief="flat",
                        cursor="hand2", padx=padx, pady=pady,
                        highlightthickness=0)
        self._themed.append((btn, {"bg": bg, "fg": fg,
                                   "activebackground": hover or bg,
                                   "activeforeground": fg}))
        return btn

    def _apply_theme(self):
        """把所有已登记控件的颜色换成当前主题。"""
        self.theme = THEMES[self.theme_key]
        t = self.theme
        self.configure(bg=t["window"])
        for widget, spec in self._themed:
            try:
                widget.configure(**{k: t[v] for k, v in spec.items()})
            except tk.TclError:
                continue
        self._apply_ttk_style()
        # 顶栏、详情等自绘部分重新上色
        if hasattr(self, "header"):
            self.header.configure(bg=t["header1"])
            self.header_line.configure(bg=t["accent"])
        if hasattr(self, "lbl_data"):
            self.lbl_data.configure(fg=t["header_sub"])
        if hasattr(self, "status"):
            self.status.configure(bg=t["status"], fg=t["status_fg"])
        # 底图与详情画布背景
        self._render_background()
        if self.selected:
            self.show_detail(self.selected)
        if hasattr(self, "btn_theme"):
            self.btn_theme.configure(
                text="☀ 白天" if self.theme_key == "night" else "☾ 夜间")

    def toggle_theme(self):
        self.theme_key = "night" if self.theme_key == "day" else "day"
        self._apply_theme()
        self.refresh()
        self.save_settings()

    # ------------------------------------------------------------------
    # 背景图
    # ------------------------------------------------------------------
    def _bg_setting_path(self):
        return os.path.join(core.data_dir(), BG_SETTING)

    def _read_bg_setting(self):
        try:
            with open(self._bg_setting_path(), "r", encoding="utf-8") as f:
                path = json.load(f).get("path", "")
            return path if path and os.path.exists(path) else ""
        except Exception:  # noqa: BLE001
            return ""

    def choose_background(self):
        if not HAS_PIL:
            messagebox.showerror("背景", "缺少 Pillow，无法加载图片")
            return
        path = filedialog.askopenfilename(
            title="选择背景图片（建议 1920×1080）",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("全部", "*.*")])
        if not path:
            return
        try:  # 复制到数据目录，避免原图被移动后失效
            dst = os.path.join(core.data_dir(), "background" + os.path.splitext(path)[1].lower())
            with open(path, "rb") as src, open(dst, "wb") as out:
                out.write(src.read())
            with open(self._bg_setting_path(), "w", encoding="utf-8") as f:
                json.dump({"path": dst}, f, ensure_ascii=False)
            self._bg_path = dst
            self._load_background()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("背景", f"加载失败：{exc}")

    def clear_background(self):
        self._bg_path = ""
        self._bg_source = None
        self._bg_fit = None
        self._bg_photo = None
        try:
            os.remove(self._bg_setting_path())
        except Exception:  # noqa: BLE001
            pass
        self._render_background()
        self._update_canvas_wallpaper()

    def _load_background(self):
        if not self._bg_path or not HAS_PIL:
            self._render_background()
            return
        try:
            self._bg_source = Image.open(self._bg_path).convert("RGB")
        except Exception:  # noqa: BLE001
            self._bg_source = None
        self._render_background()
        self._update_canvas_wallpaper()

    def _render_background(self):
        """把背景图按窗口尺寸裁切 + 主题染色，铺到窗口最底层。"""
        t = self.theme
        if not getattr(self, "bg_label", None):
            return
        if not self._bg_source or not HAS_PIL:
            self.bg_label.place_forget()
            self.configure(bg=t["window"])
            return
        w = max(self.winfo_width(), 320)
        h = max(self.winfo_height(), 240)
        img = self._bg_source
        # 等比缩放到覆盖整个窗口（cover），再居中裁切
        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale + 0.5), int(img.height * scale + 0.5)
        img = img.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        img = img.filter(ImageFilter.GaussianBlur(1.4))
        # 叠一层主题色，保证前景可读
        overlay = Image.new("RGB", img.size, t["window"])
        img = Image.blend(img, overlay, t["wall_alpha"])
        self._bg_fit = img
        self._bg_photo = ImageTk.PhotoImage(img)
        self.bg_label.configure(image=self._bg_photo)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_label.lower()

    def _update_canvas_wallpaper(self):
        """详情画布也用同一张底图的对应区域，形成「卡片浮在壁纸上」的效果。"""
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("wall")
        if not self._bg_fit or not HAS_PIL:
            self.canvas.configure(bg=self.theme["window"])
            return
        try:
            x = self.canvas.winfo_rootx() - self.winfo_rootx()
            y = self.canvas.winfo_rooty() - self.winfo_rooty()
            w = max(self.canvas.winfo_width(), 10)
            h = max(self.canvas.winfo_height(), 10)
            box = (max(x, 0), max(y, 0), max(x, 0) + w, max(y, 0) + h)
            crop = self._bg_fit.crop(box)
            self._canvas_wall = ImageTk.PhotoImage(crop)
            self.canvas.create_image(0, 0, anchor="nw", image=self._canvas_wall,
                                     tags="wall")
            self.canvas.tag_lower("wall")
        except Exception:  # noqa: BLE001
            self.canvas.configure(bg=self.theme["window"])

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def _build_ui(self):
        try:
            ico = os.path.join(core._bundle_dir(), "assets", "app.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:  # noqa: BLE001
            pass

        # 最底层背景图容器（未设置背景时隐藏）
        self.bg_label = tk.Label(self, bd=0)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_label.lower()

        # ---- 顶栏 ----
        self.header = tk.Frame(self, bg=self.theme["header1"], height=56)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)
        self._label(self.header, " 碧蓝航线 · 装备性能排行", bg="header1",
                    fg="header_fg", font=(FONT, 14, "bold")).pack(side="left")
        self._label(self.header, "评分 = 77 秒累计伤害（舰载机按架次）",
                    bg="header1", fg="header_sub", font=(FONT, 8)).pack(
            side="left", padx=(10, 0))

        self.lbl_data = self._label(self.header, "", bg="header1", fg="header_sub",
                                    font=(FONT, 8))
        self.lbl_data.pack(side="right", padx=(6, 14))
        self.btn_theme = self._button(self.header, "☾ 夜间", self.toggle_theme,
                                      bg="header1", fg="header_fg", hover="header2",
                                      padx=10, pady=4)
        self.btn_theme.pack(side="right", padx=4, pady=10)
        self._button(self.header, "背景", self.choose_background,
                     bg="header1", fg="header_fg", hover="header2",
                     padx=10, pady=4).pack(side="right", padx=4, pady=10)
        self._button(self.header, "清除背景", self.clear_background,
                     bg="header1", fg="header_fg", hover="header2",
                     padx=10, pady=4).pack(side="right", padx=4, pady=10)
        self.header_line = tk.Frame(self, bg=self.theme["accent"], height=2)
        self.header_line.pack(fill="x", side="top")

        # ---- 筛选 + 参数（收进一张卡片，四周留白让壁纸透出）----
        shell = tk.Frame(self, bg=self.theme["window"],
                         highlightbackground=self.theme["line"], highlightthickness=1)
        self._themed.append((shell, {"bg": "window", "highlightbackground": "line"}))
        shell.pack(fill="x", padx=18, pady=(8, 6))

        bar = ttk.Frame(shell, padding=(12, 9, 12, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text="搜索").pack(side="left")
        self.var_kw = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_kw, width=18).pack(side="left", padx=(5, 12))
        self.var_kw.trace_add("write", lambda *_: self.refresh())

        ttk.Label(bar, text="分类").pack(side="left")
        self.var_cat = tk.StringVar(value="舰炮")
        self.cb_cat = ttk.Combobox(bar, textvariable=self.var_cat, width=8,
                                   state="readonly", values=["全部"])
        self.cb_cat.pack(side="left", padx=(5, 12))
        self.cb_cat.bind("<<ComboboxSelected>>", lambda *_: self._sync_types())

        ttk.Label(bar, text="类型").pack(side="left")
        self.var_type = tk.StringVar(value="全部")
        self.cb_type = ttk.Combobox(bar, textvariable=self.var_type, width=11,
                                    state="readonly", values=["全部"])
        self.cb_type.pack(side="left", padx=(5, 12))
        self.cb_type.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        ttk.Label(bar, text="稀有度").pack(side="left")
        self.var_rarity = tk.StringVar(value="全部")
        cb_r = ttk.Combobox(bar, textvariable=self.var_rarity, width=6,
                            state="readonly", values=["全部"] + core.RARITIES)
        cb_r.pack(side="left", padx=(5, 12))
        cb_r.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        ttk.Label(bar, text="阵营").pack(side="left")
        self.var_faction = tk.StringVar(value="全部")
        self.cb_faction = ttk.Combobox(bar, textvariable=self.var_faction, width=9,
                                       state="readonly", values=["全部"])
        self.cb_faction.pack(side="left", padx=(5, 12))
        self.cb_faction.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        ttk.Label(bar, text="鱼雷弹药").pack(side="left")
        self.var_torp = tk.StringVar(value="全部")
        cb_t = ttk.Combobox(bar, textvariable=self.var_torp, width=6,
                            state="readonly", values=["全部", "通常", "声导"])
        cb_t.pack(side="left", padx=(5, 10))
        cb_t.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        self.var_only_weapon = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="仅显示可评分", variable=self.var_only_weapon,
                       bg=self.theme["window"], fg=self.theme["text"],
                       activebackground=self.theme["window"],
                       selectcolor=self.theme["panel"],
                       font=(FONT, 9), bd=0, highlightthickness=0,
                       command=self.refresh).pack(side="left")

        ttk.Button(bar, text="导出 CSV", command=self.export_csv).pack(side="right")
        ttk.Button(bar, text="更新数据", style="Accent.TButton",
                   command=self.update_data).pack(side="right", padx=8)

        # ---- 参数栏 ----
        pbar = ttk.Frame(shell, padding=(12, 7, 12, 8))
        pbar.pack(fill="x")
        self.pvars = {}
        for label, width in (("炮击", 5), ("雷击", 5), ("防空", 5), ("航空", 5),
                             ("装填值", 5), ("属性效率", 5), ("增伤", 4),
                             ("暴击倍率", 5)):
            ttk.Label(pbar, text=label).pack(side="left")
            var = tk.StringVar(value=self._fmt_num(self.params.get(label, 100)))
            self.pvars[label] = var
            e = ttk.Entry(pbar, textvariable=var, width=width)
            e.pack(side="left", padx=(4, 9))
            e.bind("<Return>", lambda *_: self.recompute())
            e.bind("<FocusOut>", lambda *_: self.recompute())

        ttk.Label(pbar, text="强化").pack(side="left", padx=(4, 0))
        self.var_level = tk.StringVar(
            value=self._level_label(self.params.get("强化等级", 13)))
        cb_lv = ttk.Combobox(pbar, textvariable=self.var_level, width=6,
                             state="readonly", values=LEVEL_CHOICES)
        cb_lv.pack(side="left", padx=(4, 10))
        cb_lv.bind("<<ComboboxSelected>>", lambda *_: self.recompute())

        self.var_anim = tk.BooleanVar(value=self.params.get("计入动画", True))
        self.var_equip_stat = tk.BooleanVar(value=self.params.get("计入装备属性", True))
        for text, var in (("计入开火动画", self.var_anim),
                          ("计入装备属性", self.var_equip_stat)):
            tk.Checkbutton(pbar, text=text, variable=var, bg=self.theme["window"],
                           fg=self.theme["text"],
                           activebackground=self.theme["window"],
                           selectcolor=self.theme["panel"],
                           font=(FONT, 9), bd=0, highlightthickness=0,
                           command=self.recompute).pack(side="left", padx=(0, 6))

        # ---- 主体：表格 + 详情 ----
        self._body = ttk.Panedwindow(self, orient="horizontal")
        self._body.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        left = ttk.Frame(self._body)
        self._body.add(left, weight=3)
        right = ttk.Frame(self._body)
        self._body.add(right, weight=2)
        self._build_table(left)
        self._build_detail(right)

        # ---- 状态栏 ----
        self.status = tk.Label(self, text="就绪", anchor="w",
                               bg=self.theme["status"], fg=self.theme["status_fg"],
                               font=(FONT, 8), padx=12, pady=4)
        self.status.pack(fill="x", side="bottom")

    def _build_table(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLUMNS],
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="装备", command=lambda: self.sort_by("名称"))
        self.tree.column("#0", width=280, anchor="w", minwidth=150, stretch=True)
        for name, width, anchor in COLUMNS:
            self.tree.heading(name, text=name, command=lambda c=name: self.sort_by(c))
            self.tree.column(name, width=width, anchor=anchor, minwidth=40)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda *_: self.open_wiki())

    def _build_detail(self, parent):
        # 标题条
        head = tk.Frame(parent, bg=self.theme["card"], highlightbackground=self.theme["line"],
                        highlightthickness=1)
        head.pack(fill="x", pady=(0, 6))
        self._themed.append((head, {"bg": "card", "highlightbackground": "line"}))
        self._label(head, "装备详情", bg="card", fg="header1",
                    font=(FONT, 10, "bold")).pack(side="left", padx=12, pady=7)
        self._button(head, "打开 Wiki", self.open_wiki,
                     bg="chip1_bg", fg="chip1_fg", hover="select").pack(
            side="right", padx=(4, 10), pady=7)
        self._button(head, "输出测试", self.open_sim,
                     bg="chip2_bg", fg="chip2_fg", hover="select").pack(
            side="right", pady=7)

        holder = tk.Frame(parent, bg=self.theme["window"],
                          highlightbackground=self.theme["line"], highlightthickness=1)
        holder.pack(fill="both", expand=True)
        self._themed.append((holder, {"bg": "window", "highlightbackground": "line"}))
        self.canvas = tk.Canvas(holder, bg=self.theme["window"],
                                highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        # 详情卡片不用内嵌 Frame，而是逐个挂到画布上，
        # 这样卡片之间与四周的缝隙能透出壁纸（画布底图）。
        self._cards: list[tuple[tk.Frame, int]] = []
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Enter>",
                         lambda e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _new_card_frame(self) -> tuple[tk.Frame, tk.Frame]:
        """新建一张卡片并挂到画布上，返回 (卡片外层, 内容区)。"""
        t = self.theme
        frame = tk.Frame(self.canvas, bg=t["card"], highlightbackground=t["line"],
                         highlightthickness=1)
        item = self.canvas.create_window((12, 0), anchor="nw", window=frame,
                                         tags="card")
        self._cards.append((frame, item))
        body = tk.Frame(frame, bg=t["card"])
        body.pack(fill="x", padx=14, pady=12)
        return frame, body

    def _layout_cards(self):
        """按当前画布宽度重新排列卡片（宽度变化会改变换行高度）。"""
        if not hasattr(self, "canvas"):
            return
        width = max(self.canvas.winfo_width() - 24, 220)
        y = 10
        for frame, item in self._cards:
            try:
                self.canvas.itemconfigure(item, width=width)
                frame.update_idletasks()
                self.canvas.coords(item, 12, y)
                y += frame.winfo_reqheight() + 8
            except tk.TclError:
                continue
        self.canvas.configure(scrollregion=(0, 0, width + 24, y + 10))

    def _on_canvas_resize(self, event):
        if not hasattr(self, "_wall_job"):
            self._wall_job = None
        if self._wall_job:
            self.after_cancel(self._wall_job)
        self._wall_job = self.after(120, self._after_canvas_resize)

    def _after_canvas_resize(self):
        self._layout_cards()
        self._update_canvas_wallpaper()

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    # ------------------------------------------------------------------
    # 数据与筛选
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_num(v) -> str:
        try:
            return f"{float(v):g}"
        except (TypeError, ValueError):
            return "0"

    @staticmethod
    def _level_label(level) -> str:
        try:
            lv = int(level)
        except (TypeError, ValueError):
            lv = 13
        return "无强化" if lv <= 0 else f"+{lv}"

    @staticmethod
    def _level_value(label: str) -> int:
        return 0 if label == "无强化" else int(label.replace("+", ""))

    def _load_data(self):
        items, tag = core.load_data()
        self.items = items
        self.lbl_data.config(
            text=f"数据 {len(items)} 件 · {tag}" if items else "无数据，请点击「更新数据」")
        self.cb_cat.config(values=["全部"] + sorted({it["category"] for it in items}))
        self.cb_faction.config(
            values=["全部"] + sorted({it["faction"] for it in items if it["faction"]}))
        self._sync_types()
        self.recompute()

    def _sync_types(self):
        cat = self.var_cat.get()
        types = sorted({it["type"] for it in self.items
                        if cat == "全部" or it["category"] == cat})
        values = ["全部"] + types
        self.cb_type.config(values=values)
        if self.var_type.get() not in values:
            self.var_type.set("全部")
        self.refresh()

    def _collect_params(self) -> dict:
        p = dict(self.params)
        for key, var in self.pvars.items():
            try:
                p[key] = float(var.get())
            except ValueError:
                p[key] = 0.0
        p["强化等级"] = self._level_value(self.var_level.get())
        p["计入动画"] = bool(self.var_anim.get())
        p["计入装备属性"] = bool(self.var_equip_stat.get())
        return p

    def recompute(self):
        self.params = self._collect_params()
        core.score_all(self.items, self.params)
        self.refresh()

    def refresh(self):
        kw = self.var_kw.get().strip().lower()
        t, r, f = self.var_type.get(), self.var_rarity.get(), self.var_faction.get()
        cat, torp_mode = self.var_cat.get(), self.var_torp.get()
        only = self.var_only_weapon.get()

        rows = []
        for it in self.items:
            if kw and kw not in it["name"].lower() \
                    and kw not in it.get("base_name", "").lower():
                continue
            if cat != "全部" and it["category"] != cat:
                continue
            if t != "全部" and it["type"] != t:
                continue
            if r != "全部" and it["rarity"] != r:
                continue
            if f != "全部" and it["faction"] != f:
                continue
            if torp_mode != "全部" and it["category"] == "鱼雷":
                homing = "声导" in (it.get("ammo") or "")
                if torp_mode == "声导" and not homing:
                    continue
                if torp_mode == "通常" and homing:
                    continue
            if only and not (it.get("score") or {}):
                continue
            rows.append(it)

        def sval(it, key):
            s = (it.get("score") or {}).get(key)
            return s["value"] if s else -1.0

        key_map = {
            "评分·对空": lambda x: sval(x, "对空"),
            "评分·轻甲": lambda x: sval(x, "轻甲"),
            "评分·中甲": lambda x: sval(x, "中甲"),
            "评分·重甲": lambda x: sval(x, "重甲"),
            "单轮基础": lambda x: self._volley_of(x),
            "名称": lambda x: x["name"],
            "类型": lambda x: x["type"],
            "稀有度": lambda x: (core.RARITIES.index(x["rarity"])
                                 if x["rarity"] in core.RARITIES else 9),
            "排名": lambda x: 0,
        }
        rows.sort(key=key_map.get(self.sort_col, key_map["评分·轻甲"]),
                  reverse=self.sort_desc)

        self.tree.delete(*self.tree.get_children())
        self.rows = rows
        for i, it in enumerate(rows, 1):
            sc = it.get("score") or {}

            def fmt(key):
                s = sc.get(key)
                return f"{s['value']:,.0f}" if s else "—"

            tag = f"{it['rarity']}|{'o' if i % 2 else 'e'}"
            self.tree.insert("", "end", iid=it["name"], tags=(tag,),
                             text="  " + it["name"],
                             image=self._icon_small(it["name"]),
                             values=(i, it["type"], it["rarity"],
                                     f"{self._volley_of(it):,.1f}",
                                     fmt("对空"), fmt("轻甲"), fmt("中甲"), fmt("重甲")))

        for name, _, _ in COLUMNS:
            base = name + (" ▼" if self.sort_desc else " ▲") if name == self.sort_col else name
            self.tree.heading(name, text=base)
        head0 = "装备" + (" ▼" if self.sort_desc else " ▲") \
            if self.sort_col == "名称" else "装备"
        self.tree.heading("#0", text=head0)

        self.status.config(
            text=f"共 {len(rows)} 件 · 按「{self.sort_col}」"
                 f"{'降序' if self.sort_desc else '升序'}"
                 f" · 单击表头排序，双击行打开 Wiki")
        kids = self.tree.get_children()
        if kids:
            sel = self.tree.selection()
            if not sel or sel[0] not in kids:
                self.tree.selection_set(kids[0])
            self.tree.yview_moveto(0)

    def _volley_of(self, it: dict) -> float:
        """列表「单轮基础」列：舰载机取单架次挂载总伤害，其余取单轮原始伤害。"""
        if it.get("category") == "舰载机" and "payload" in it:
            return float(it["payload"])
        sc = it.get("score") or {}
        for key in ("轻甲", "中甲", "重甲", "对空"):
            s = sc.get(key)
            if s:
                return float(s.get("volley_raw") or s.get("volley")
                             or s.get("per_sortie") or s.get("value") or 0.0)
        return 0.0

    def sort_by(self, col):
        if col == "排名":
            return
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = col
            self.sort_desc = True
        self.refresh()

    # ------------------------------------------------------------------
    # 图标
    # ------------------------------------------------------------------
    def _load_icon_big(self, name: str):
        if name in self._icon_big_cache:
            return self._icon_big_cache[name]
        path = self.icon_map.get(name)
        img = None
        if path and os.path.exists(path):
            try:
                img = tk.PhotoImage(file=path)
            except tk.TclError:
                img = None
        self._icon_big_cache[name] = img
        return img

    def _icon_small(self, name: str):
        if name in self._icon_small_cache:
            return self._icon_small_cache[name]
        big = self._load_icon_big(name)
        small = ""
        if big is not None:
            try:
                small = big.subsample(2, 2)
            except tk.TclError:
                small = ""
        self._icon_small_cache[name] = small
        return small

    # ------------------------------------------------------------------
    # 详情面板（卡片式）
    # ------------------------------------------------------------------
    def on_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        item = next((x for x in self.items if x["name"] == sel[0]), None)
        if item:
            self.selected = item
            self.show_detail(item)
            self._update_canvas_wallpaper()

    def _card(self, title: str | None = None):
        """创建一张卡片：主题色背景 + 描边 + 可选的左侧色条标题。"""
        t = self.theme
        _frame, body = self._new_card_frame()
        if title:
            row = tk.Frame(body, bg=t["card"])
            row.pack(fill="x", pady=(0, 9))
            tk.Frame(row, bg=t["accent"], width=3, height=14).pack(side="left",
                                                                  padx=(0, 7))
            tk.Label(row, text=title, bg=t["card"], fg=t["accent"],
                     font=(FONT, 9, "bold")).pack(side="left")
        return body

    def _kv_grid(self, body, pairs, cols=2, wrap=170):
        """两列「标签 : 数值」网格。"""
        t = self.theme
        grid = tk.Frame(body, bg=t["card"])
        grid.pack(fill="x")
        for i, (k, v) in enumerate(pairs):
            r, c = divmod(i, cols)
            tk.Label(grid, text=k, bg=t["card"], fg=t["muted"],
                     font=(FONT, 8), anchor="w").grid(row=r, column=c * 2,
                                                      sticky="w", pady=3)
            tk.Label(grid, text=v, bg=t["card"], fg=t["text"], font=(FONT, 9),
                     anchor="w", wraplength=wrap, justify="left").grid(
                row=r, column=c * 2 + 1, sticky="w", padx=(8, 18), pady=3)

    def show_detail(self, it: dict):
        t = self.theme
        self.canvas.delete("card")
        self._cards.clear()

        # ---------- 头部：图标 + 名称 + 标签 ----------
        _head, body = self._new_card_frame()
        row = tk.Frame(body, bg=t["card"])
        row.pack(fill="x")
        big = self._load_icon_big(it["name"])
        if big is not None:
            tk.Label(row, image=big, bg=t["card"]).pack(side="left", padx=(0, 14))
        col = tk.Frame(row, bg=t["card"])
        col.pack(side="left", anchor="w", fill="x", expand=True)
        tk.Label(col, text=it["name"], bg=t["card"],
                 fg=RARITY_COLOR.get(it["rarity"], t["header1"]),
                 font=(FONT, 13, "bold"), wraplength=300, justify="left",
                 anchor="w").pack(anchor="w")
        chips = tk.Frame(col, bg=t["card"])
        chips.pack(anchor="w", pady=(8, 0))
        for text, bgk, fgk in ((it["category"], "chip1_bg", "chip1_fg"),
                               (it["type"], "chip2_bg", "chip2_fg"),
                               (it["rarity"], "chip3_bg", "chip3_fg"),
                               (it["faction"], "chip4_bg", "chip4_fg")):
            if text:
                tk.Label(chips, text=text, bg=t[bgk], fg=t[fgk], font=(FONT, 8),
                         padx=8, pady=2).pack(side="left", padx=(0, 6))

        # 当前强化档位（用于展示与「已达上限」提示）
        raw = it.get("raw", {})
        want = int(self.params.get("强化等级", 13))
        lv = it.get("levels") or {}
        dmg = core.pick_level(lv.get("damage", {}), want)
        rld = core.pick_level(lv.get("reload", {}), want)
        corr = core.pick_level(lv.get("correction", {}), want)
        lv_used = max(core.used_level(lv.get("damage", {}), want),
                      core.used_level(lv.get("reload", {}), want),
                      core.used_level(lv.get("correction", {}), want))

        # ---------- 评分 ----------
        body = self._card("伤害评分")
        sc = it.get("score") or {}
        keys = [k for k in SCORE_KEYS if k in sc]
        if not keys:
            tk.Label(body, text="该装备不参与伤害评分", bg=t["card"], fg=t["warn"],
                     font=(FONT, 9)).pack(anchor="w")
        else:
            grid = tk.Frame(body, bg=t["card"])
            grid.pack(fill="x")
            cols = max(len(keys), 3)
            for j in range(cols):
                grid.columnconfigure(j, weight=1)
            for i, k in enumerate(keys):
                r = sc[k]
                tile = tk.Frame(grid, bg=t["tile"], highlightbackground=t["tile_line"],
                                highlightthickness=1)
                tile.grid(row=0, column=i, sticky="nsew", padx=(0, 7))
                tk.Label(tile, text=k, bg=t["tile"], fg=t["muted"],
                         font=(FONT, 8)).pack(pady=(9, 0))
                tk.Label(tile, text=f"{r['value']:,.0f}", bg=t["tile"], fg=t["gold"],
                         font=(FONT, 16, "bold")).pack(pady=(2, 0))
                if r.get("kind") in ("plane", "plane_aa"):
                    note = f"{r['sorties']} 架次"
                else:
                    note = f"{r.get('shots', 0)} 轮"
                tk.Label(tile, text=note, bg=t["tile"], fg=t["muted"],
                         font=(FONT, 7)).pack(pady=(1, 9))

            is_plane = any(r.get("kind") in ("plane", "plane_aa") for r in sc.values())
            caption = ("单架次挂载 × 77 秒内架次（机枪计对空，炸弹/鱼雷计对甲）"
                       if is_plane else "77 秒内累计伤害（首轮 t=0，超时部分丢弃）")
            tk.Label(body, text="评分口径：" + caption, bg=t["card"], fg=t["muted"],
                     font=(FONT, 8)).pack(anchor="w", pady=(9, 0))
            if lv_used and lv_used < want:
                tk.Label(body, text=f"注：该装备最高 +{lv_used}，已按 +{lv_used} 计算",
                         bg=t["card"], fg=t["warn"],
                         font=(FONT, 8)).pack(anchor="w", pady=(3, 0))

            det = tk.Frame(body, bg=t["card"])
            det.pack(fill="x", pady=(7, 0))
            for k in keys:
                r = sc[k]
                if r.get("kind") in ("plane", "plane_aa"):
                    line = (f"{k}：单架次 {r['per_sortie']:,.1f} × {r['sorties']} 架次"
                            f"（出击间隔 {r['cycle']:.2f}s）")
                else:
                    line = (f"{k}：单轮 {r['volley']:,.1f} × {r['shots']} 轮"
                            f"（间隔 {r['cycle']:.2f}s）")
                tk.Label(det, text=line, bg=t["card"], fg=t["muted"],
                         font=(FONT, 8), anchor="w").pack(anchor="w")

        # ---------- 基础数据 ----------
        body = self._card(f"基础数据（强化 +{lv_used}）" if lv_used else "基础数据")
        pairs = []
        if dmg and dmg[0]:
            pairs.append(("伤害", f"{dmg[0]:g}×{dmg[1]:g}" if dmg[1] > 1 else f"{dmg[0]:g}"))
        if rld:
            pairs.append(("标准射速", f"{rld:.2f}s/轮"))
        if corr:
            pairs.append(("伤害补正", f"{corr:g}%"))
        for k in ("炮击", "雷击", "防空", "航空", "弹药", "特性", "对甲比例",
                  "舰载机耐久", "舰载机航速", "舰载机回避上限"):
            v = raw.get(k, "").strip()
            if v:
                pairs.append((k, v))
        if pairs:
            self._kv_grid(body, pairs)
        else:
            tk.Label(body, text="—", bg=t["card"], fg=t["muted"]).pack(anchor="w")

        # ---------- 舰载挂载 ----------
        mounts = it.get("mounts") or {}
        if any(mounts.values()):
            body = self._card("舰载挂载")
            for kind, label in (("mg", "机枪"), ("bomb", "炸弹"), ("torp", "鱼雷")):
                for m in mounts.get(kind) or []:
                    d = core.pick_level(m.get("damage") or {}, want, 0) or 0
                    line = f"{m['count']} × {m['name']}"
                    tk.Label(body, text=line, bg=t["card"], fg=t["text"],
                             font=(FONT, 9), anchor="w").pack(anchor="w", pady=(2, 0))
                    extra = ""
                    if m.get("armor"):
                        extra = "   对甲 " + "/".join(f"{x:g}" for x in m["armor"])
                    tk.Label(body, text=f"    {label}单发 {d:g}{extra}", bg=t["card"],
                             fg=t["muted"], font=(FONT, 8)).pack(anchor="w")

        # ---------- 技能 ----------
        if it.get("skill_desc"):
            body = self._card("技能")
            tk.Label(body, text=it.get("skill_name") or "—", bg=t["card"],
                     fg=t["text"], font=(FONT, 9, "bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(body, text=it["skill_desc"], bg=t["card"], fg=t["good"],
                     font=(FONT, 9), wraplength=400, justify="left",
                     anchor="w").pack(anchor="w", pady=(4, 0))

        # ---------- 完整属性 ----------
        body = self._card("完整属性")
        shown = set(p[0] for p in pairs) if pairs else set()
        shown |= {"名称", "类型", "稀有度", "所属阵营"}
        order = {k: i for i, k in enumerate(DETAIL_ORDER)}
        rest = [(k, v) for k, v in raw.items()
                if k and v and v.strip() and k not in shown]
        rest.sort(key=lambda kv: (order.get(kv[0], 999), kv[0]))
        if rest:
            short = [(k, v) for k, v in rest if len(v) <= 24]
            long_ = [(k, v) for k, v in rest if len(v) > 24]
            if short:
                self._kv_grid(body, short)
            for k, v in long_:
                tk.Label(body, text=k, bg=t["card"], fg=t["muted"],
                         font=(FONT, 8), anchor="w").pack(anchor="w", pady=(7, 0))
                tk.Label(body, text=v, bg=t["card"], fg=t["text"], font=(FONT, 8),
                         wraplength=400, justify="left",
                         anchor="w").pack(anchor="w")
        else:
            tk.Label(body, text="—", bg=t["card"], fg=t["muted"]).pack(anchor="w")

        self._layout_cards()
        self.canvas.yview_moveto(0.0)
        self._update_canvas_wallpaper()
    def open_wiki(self):
        if self.selected:
            webbrowser.open(self.selected.get("url", ""))

    # ------------------------------------------------------------------
    # 输出测试
    # ------------------------------------------------------------------
    def open_sim(self):
        it = self.selected
        if not it:
            messagebox.showinfo("输出测试", "请先在左侧列表中选择一件装备")
            return
        t = self.theme
        win = tk.Toplevel(self)
        win.title("输出测试")
        win.geometry("580x540")
        win.transient(self)
        win.configure(bg=t["card"])

        top = tk.Frame(win, bg=t["card"])
        top.pack(fill="x", padx=18, pady=(16, 2))
        big = self._load_icon_big(it["name"])
        if big is not None:
            tk.Label(top, image=big, bg=t["card"]).pack(side="left", padx=(0, 12))
        info = tk.Frame(top, bg=t["card"])
        info.pack(side="left", anchor="w")
        tk.Label(info, text=it["name"], bg=t["card"], fg=t["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        tk.Label(info, text=f"{it['category']} / {it['type']} · {it['rarity']}",
                 bg=t["card"], fg=t["muted"], font=(FONT, 8)).pack(anchor="w")

        ctl = tk.Frame(win, bg=t["card"])
        ctl.pack(fill="x", padx=18, pady=(10, 6))
        tk.Label(ctl, text="时长（秒）", bg=t["card"], fg=t["text"],
                 font=(FONT, 9)).pack(side="left")
        var = tk.StringVar(value=f"{core.SCORE_WINDOW:g}")
        ent = ttk.Entry(ctl, textvariable=var, width=8)
        ent.pack(side="left", padx=(8, 10))

        body = tk.Text(win, wrap="word", bg=t["card"], relief="flat", font=(FONT, 9),
                       padx=18, pady=4, highlightthickness=0, bd=0,
                       fg=t["text"], insertbackground=t["text"])
        body.pack(fill="both", expand=True, pady=(0, 16))
        body.tag_configure("h", font=(FONT, 9, "bold"), foreground=t["accent"],
                           spacing1=12, spacing3=4)
        body.tag_configure("k", foreground=t["muted"])
        body.tag_configure("num", font=(FONT, 15, "bold"), foreground=t["gold"])
        body.tag_configure("armor", font=(FONT, 9, "bold"), foreground=t["text"],
                           spacing1=9)

        def render(*_):
            try:
                secs = float(var.get())
                if secs <= 0:
                    raise ValueError
            except ValueError:
                secs = core.SCORE_WINDOW
                var.set(f"{secs:g}")
            res = core.simulate(it, self.params, secs)
            body.configure(state="normal")
            body.delete("1.0", "end")
            rows = res["rows"]
            if not rows:
                body.insert("end", "该装备不参与伤害计算。\n", "k")
            elif res["kind"] == "gun":
                r = rows[0][1]
                body.insert("end", "射击节奏\n", "h")
                body.insert("end",
                            f"  开火间隔 {r['cycle']:.2f}s（装填 {r['reload']:.2f}s ×"
                            f" 装填系数 + 开火动画）\n", "k")
                body.insert("end",
                            f"  {secs:g} 秒内开火 {r['shots']} 次（首轮按 t=0 计）\n", "k")
                for k, r in rows:
                    body.insert("end", f"对{k}\n", "armor")
                    body.insert("end", f"  单轮 {r['volley']:.1f} × {r['shots']} 轮 = ", "k")
                    body.insert("end", f"{r['value']:,.0f}", "num")
                    body.insert("end", f"\n  等效秒伤 {r['dps']:.1f}\n", "k")
            else:
                r0 = rows[0][1]
                body.insert("end", "架次节奏\n", "h")
                body.insert("end",
                            f"  出击间隔 {r0['cycle']:.2f}s，{secs:g} 秒内出击"
                            f" {r0['sorties']} 架次（首架按 t=0 计）\n", "k")
                for k, r in rows:
                    body.insert("end", f"对{k}\n", "armor")
                    body.insert("end",
                                f"  单架次 {r['per_sortie']:,.1f} × {r['sorties']} 架次 = ", "k")
                    body.insert("end", f"{r['value']:,.0f}", "num")
                    body.insert("end", f"\n  等效秒伤 {r['value'] / secs:.1f}\n", "k")
            body.configure(state="disabled")

        ttk.Button(ctl, text="计算", command=render).pack(side="left")
        ttk.Button(ctl, text="关闭", command=win.destroy).pack(side="right")
        ent.bind("<Return>", render)
        render()

    # ------------------------------------------------------------------
    # 更新数据
    # ------------------------------------------------------------------
    def update_data(self):
        if self._busy:
            return
        if not messagebox.askyesno("更新数据",
                                   "将从 Wiki 重新抓取全部装备数据（约 1 分钟），是否继续？"):
            return
        self._busy = True
        t = self.theme
        dlg = tk.Toplevel(self)
        dlg.title("更新数据")
        dlg.geometry("460x140")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=t["card"])
        lbl = tk.Label(dlg, text="正在连接 Wiki…", bg=t["card"], fg=t["text"],
                       font=(FONT, 9), wraplength=420, justify="left")
        lbl.pack(padx=20, pady=(22, 10), anchor="w")
        pb = ttk.Progressbar(dlg, mode="determinate", maximum=100, length=420)
        pb.pack(padx=20)
        self._dlg = (dlg, lbl, pb)

        def worker():
            try:
                items = core.scrape(lambda stage, done, total:
                                    self.queue.put(("progress", stage, done, total)))
                path = core.save_cache(items)
                self.queue.put(("done", items, path))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, stage, done, total = msg
                    if getattr(self, "_dlg", None):
                        _, lbl, pb = self._dlg
                        lbl.config(text=f"{stage}  {done}/{total}" if total else stage)
                        pb.config(maximum=max(total, 1), value=done)
                elif kind == "done":
                    _, items, path = msg
                    self._busy = False
                    self._close_dlg()
                    self.items = items
                    self.lbl_data.config(text=f"数据 {len(items)} 件 · 刚刚更新")
                    self._load_data()
                    messagebox.showinfo("完成", f"已更新 {len(items)} 件装备数据。\n{path}")
                elif kind == "error":
                    self._busy = False
                    self._close_dlg()
                    messagebox.showerror("更新失败", msg[1])
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _close_dlg(self):
        if getattr(self, "_dlg", None):
            self._dlg[0].destroy()
            self._dlg = None

    # ------------------------------------------------------------------
    # 导出 CSV
    # ------------------------------------------------------------------
    def export_csv(self):
        if not self.rows:
            messagebox.showinfo("导出", "当前没有可导出的数据")
            return
        path = os.path.join(core.data_dir(), "装备排行.csv")

        def cell(it, key):
            s = (it.get("score") or {}).get(key)
            return f"{s['value']:.2f}" if s else ""

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["排名", "名称", "类型", "稀有度", "阵营", "弹药",
                            "单轮基础", "评分·对空", "评分·轻甲", "评分·中甲",
                            "评分·重甲", "Wiki"])
                for i, it in enumerate(self.rows, 1):
                    w.writerow([
                        i, it["name"], it["type"], it["rarity"], it["faction"],
                        it.get("ammo", ""), f"{self._volley_of(it):.2f}",
                        cell(it, "对空"), cell(it, "轻甲"), cell(it, "中甲"),
                        cell(it, "重甲"), it["url"],
                    ])
            messagebox.showinfo("导出成功", f"已保存到：\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", str(exc))

    # ------------------------------------------------------------------
    # 设置持久化
    # ------------------------------------------------------------------
    def _settings_path(self):
        return os.path.join(core.data_dir(), "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.params.update({k: v for k, v in saved.items() if k in self.params})
            if saved.get("theme") in THEMES:
                self.theme_key = saved["theme"]
                self.theme = THEMES[self.theme_key]
        except Exception:  # noqa: BLE001
            pass

    def save_settings(self):
        try:
            data = self._collect_params()
            data["theme"] = self.theme_key
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except Exception:  # noqa: BLE001
            pass


def run():
    try:  # 高 DPI 下保持字体清晰
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    app = App()
    app.protocol("WM_DELETE_WINDOW", lambda: (app.save_settings(), app.destroy()))
    app.mainloop()
