# -*- coding: utf-8 -*-
"""
==============================================================================
碧蓝航线装备数据核心模块
==============================================================================

职责划分
--------
1. 网络层      : 与 WIKI 的 MediaWiki API 交互（POST，避免超长 URL）
2. 解析层      : 把装备页面的 wikitext 模板展开成结构化 dict
3. 抓取流程    : 目录 → 页面 → 模板 → 结构化数据 → JSON 缓存
4. 评分引擎    : 按「公式合集」的伤害公式计算 77 秒窗口内的累计伤害
5. 舰载机武器库: 解析机枪/炸弹/鱼雷三张数据库表（含逐级强化数值）
6. 资源        : 图标索引、内置快照

数据来源
--------
https://wiki.biligame.com/blhx/装备图鉴
每个装备是一个使用 {{舰炮图鉴}} / {{鱼雷图鉴}} / {{防空炮图鉴}} /
{{舰载机图鉴}} / {{设备图鉴}} 模板的页面，字段与网页展示一一对应。

评分口径（与用户约定）
----------------------
* 舰炮 / 导弹 / 鱼雷 / 防空炮 : 77 秒内累计伤害，超过 77 秒的部分丢弃
* 舰载机（含水上机/反潜机）  : 77 秒内累计 = 单架次挂载伤害 × 架次
                              机枪计入「对空」，炸弹/鱼雷计入「对甲」
* 强化档位 : 可选无强化 ~ +13，装备没有该档时自动回退到它的最高档

==============================================================================
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
API = "https://wiki.biligame.com/blhx/api.php"
# WIKI 会拦截默认 UA，这里伪装成浏览器
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 AL-EquipRank/1.0")

# 模板名 → 装备大类
TEMPLATES = {
    "舰炮图鉴": "舰炮",
    "导弹图鉴": "导弹",
    "鱼雷图鉴": "鱼雷",
    "防空炮图鉴": "防空炮",
    "舰载机图鉴": "舰载机",
    "设备图鉴/反潜": "设备",   # 反潜类设备用的是子模板，必须排在前面
    "设备图鉴": "设备",
    "特殊兵装图鉴": "特殊兵装",
}

# 不进入装备列表的类别（按需求剔除）
EXCLUDED_CATEGORIES = {"设备", "特殊兵装"}

# 稀有度从低到高，用于排序权重
RARITIES = ["白色", "蓝色", "紫色", "金色", "彩色"]

# 开火前摇 + 后摇（秒），取自 WIKI「装填公式」条目
ANIM_BY_TYPE = {
    "驱逐炮": 0.26,
    "轻巡炮": 0.28,
    "重巡炮": 0.30,
    "大口径重巡炮": 0.30,
    "絮库夫炮": 0.30,
    "战列炮": 0.0,     # 跨射无抬手
    "导弹": 0.0,
    "水面鱼雷": 0.20,
    "潜艇鱼": 0.20,
    "防空炮": 0.0,
}

# 强化档位（游戏内实际存在的档位）
ENHANCE_LEVELS = [0, 3, 6, 7, 10, 11, 13]

# 稀有度 → 可强化的最高档。页面没写任何强化数值时用它兜底。
# 白色 +3 / 蓝色 +6 / 紫色 +10 / 金色与彩色 +13
RARITY_MAX_LEVEL = {"白色": 3, "蓝色": 6, "紫色": 10, "金色": 13, "彩色": 13}

# 评分窗口（秒）
SCORE_WINDOW = 77.0

# 舰载机机枪射速的换算基数：wiki 数据库里的射速按「发/分」记录，
# 除以它得到「发/秒」，再乘单发伤害即为该机枪的每秒输出当量。
# 若日后确认 wiki 用的是别的单位，改这一个常数即可（不影响排名以外的口径）。
MG_RATE_UNIT = 60.0

ARMOR_KEYS = ("轻甲", "中甲", "重甲")


# ---------------------------------------------------------------------------
# 路径处理：区分「源码运行」与「PyInstaller 打包后」
# ---------------------------------------------------------------------------
def _bundle_dir() -> str:
    """打包后是可执行文件解压/放置的资源目录，源码运行时是项目根目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_dir() -> str:
    """可执行文件所在目录（用于存放用户数据）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """用户数据目录：优先 exe 同级 data/，不可写时回退到 %LOCALAPPDATA%。"""
    d = os.path.join(app_dir(), "data")
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".wtest")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return d
    except Exception:  # noqa: BLE001
        d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                         "AzurLaneEquipRank")
        os.makedirs(d, exist_ok=True)
        return d


def cache_path() -> str:
    return os.path.join(data_dir(), "equipment.json")


def plane_db_path() -> str:
    return os.path.join(data_dir(), "plane_weapons.json")


def bundled_data_path() -> str:
    return os.path.join(_bundle_dir(), "data", "equipment.json")


# ---------------------------------------------------------------------------
# 网络层
# ---------------------------------------------------------------------------
def api_get(params: dict, timeout: int = 40) -> dict:
    """调用 MediaWiki API。

    统一使用 POST：一次请求多个长中文标题时，查询串会超过服务端 URL 长度
    限制并返回 HTTP 567，POST 把参数放进 body 可以规避。
    失败自动重试 4 次（1.5s / 3s / 4.5s 退避）。
    """
    q = dict(params)
    q.setdefault("format", "json")
    q.setdefault("formatversion", 2)
    body = urllib.parse.urlencode(q).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败: {last}")


def list_category(cat: str, progress=None) -> list[str]:
    """列出一个分类下的全部页面标题（自动翻页）。"""
    titles: list[str] = []
    cont = None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": cat,
             "cmlimit": "500", "cmnamespace": "0"}
        if cont:
            p["cmcontinue"] = cont
        data = api_get(p)
        cm = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in cm)
        cont = data.get("continue", {}).get("cmcontinue")
        if progress:
            progress(len(titles))
        if not cont:
            break
        time.sleep(0.2)
    return titles


def _fetch_batch(titles: list[str]) -> dict[str, str]:
    """取一批页面（≤50）的 wikitext。"""
    out: dict[str, str] = {}
    data = api_get({
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "titles": "|".join(titles),
    })
    for page in data.get("query", {}).get("pages", []):
        if page.get("missing"):
            continue
        revs = page.get("revisions") or []
        if revs:
            content = revs[0].get("slots", {}).get("main", {}).get("content")
            if content:
                out[page["title"]] = content
    return out


def fetch_texts(titles: list[str], progress=None, total_hint=None) -> dict[str, str]:
    """批量下载 wikitext。

    每批 50 页；失败时按 10 页、再按单页重试，尽量不丢数据。
    """
    out: dict[str, str] = {}
    step = 50
    for i in range(0, len(titles), step):
        batch = titles[i:i + step]
        try:
            out.update(_fetch_batch(batch))
        except Exception:  # noqa: BLE001
            for j in range(0, len(batch), 10):
                sub = batch[j:j + 10]
                try:
                    out.update(_fetch_batch(sub))
                except Exception:  # noqa: BLE001
                    for single in sub:
                        try:
                            out.update(_fetch_batch([single]))
                        except Exception:  # noqa: BLE001
                            continue
        if progress:
            progress(min(i + step, len(titles)), total_hint or len(titles))
        time.sleep(0.25)
    return out


# ---------------------------------------------------------------------------
# 解析层：wikitext → 结构化数据
# ---------------------------------------------------------------------------
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _split_top(text: str, sep: str = "|") -> list[str]:
    """按顶层分隔符切分，跳过 {{...}} 与 [[...]] 内部的分隔符。"""
    parts, buf, depth, i = [], [], 0, 0
    n = len(text)
    while i < n:
        two = text[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            buf.append(two)
            i += 2
            continue
        ch = text[i]
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _template_body(text: str, start: int) -> str:
    """从 {{ 开始，括号配平取出模板内部文本。"""
    depth, i, n = 0, start, len(text)
    while i < n - 1:
        two = text[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
            continue
        if two == "}}":
            depth -= 1
            if depth == 0:
                return text[start + 2:i]
            i += 2
            continue
        i += 1
    return text[start + 2:]


def _clean(value: str) -> str:
    """去掉注释、换行标签，并把 [[链接|文字]] 简化为文字。"""
    v = _COMMENT.sub("", value or "").strip()
    v = v.replace("<br>", "、").replace("<br/>", "、").replace("<br />", "、")
    v = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", v)
    v = re.sub(r"\[\[([^\]]+)\]\]", r"\1", v)
    return v.strip()


def _num(value: str, default: float = 0.0) -> float:
    """从字符串里抽出第一个数字（'1.64s/轮' → 1.64）。"""
    m = re.search(r"-?\d+(?:\.\d+)?", (value or "").replace(",", ""))
    return float(m.group()) if m else default


def parse_damage(value: str) -> tuple[float, float]:
    """解析伤害面板。

    '4×4'   → (4.0, 4.0)   单发 4，弹数 4
    '56/轮' → (56.0, 1.0)  防空炮/单发类
    """
    v = _clean(value)
    m = re.match(r"\s*([\d.]+)\s*[×xX*]\s*([\d.]+)", v)
    if m:
        return float(m.group(1)), float(m.group(2))
    return _num(v), 1.0


def parse_armor(value: str) -> list[float]:
    """解析对甲比例 '120-60-60' → [轻, 中, 重]（百分数）。缺失补 0。"""
    v = _clean(value)
    parts = [p for p in re.split(r"[-/／]", v) if p.strip()]
    out = [_num(p) for p in parts[:3]]
    while len(out) < 3:
        out.append(0.0)
    return out


def parse_page(title: str, text: str) -> dict | None:
    """把一个装备页面的 wikitext 解析成装备字典。

    返回字段说明见模块顶部；raw 保留模板全部原始参数，供详情面板展示。
    """
    text = _COMMENT.sub("", text)
    # 找到装备模板（同一页面可能还嵌了别的模板，取第一个匹配）
    m = re.search(r"\{\{\s*(" + "|".join(TEMPLATES) + r")\s*(\||\}\})", text)
    if not m:
        return None
    category = TEMPLATES[m.group(1)]
    body = _template_body(text, m.start())
    chunks = _split_top(body)

    params: dict[str, str] = {}
    for chunk in chunks[1:]:
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        params[k.strip()] = _clean(v)

    # 名称末尾的 T0/T1/T2/T3 是「型号等级」，拆出来方便按系列比较
    tier_m = re.search(r"(T[0-9])$", title)
    tier = tier_m.group(1) if tier_m else ""
    base_name = title[: -len(tier)] if tier else title

    # ---- 基础数值 ----
    dmg, cnt = parse_damage(params.get("伤害", ""))
    reload_s = _num(params.get("标准射速", ""))
    max_dmg, max_cnt = parse_damage(
        params.get("强化+13伤害") or params.get("强化+11伤害")
        or params.get("强化+10伤害") or params.get("伤害", ""))
    max_reload = _num(params.get("强化+13射速") or params.get("强化+11射速")
                      or params.get("强化+10射速") or params.get("标准射速", ""))

    correction = _num(params.get("伤害补正", "100"), 100.0)
    corr_max = _num(params.get("强化+13伤害补正") or params.get("强化+11伤害补正")
                    or params.get("强化+7伤害补正") or "", 0.0) or correction

    # ---- 逐级强化数值（0 = 无强化）----
    # 页面上不一定每档都写，缺档时评分阶段会回退到「不高于目标档的最高档」
    lv_damage = {0: (dmg, cnt)}
    lv_reload = {0: reload_s} if reload_s else {}
    lv_corr = {0: correction}
    for lv in (3, 6, 7, 10, 11, 13):
        raw_d = params.get(f"强化+{lv}伤害", "")
        if raw_d.strip():
            lv_damage[lv] = parse_damage(raw_d)
        raw_r = params.get(f"强化+{lv}射速", "")
        if raw_r.strip():
            lv_reload[lv] = _num(raw_r)
        raw_c = params.get(f"强化+{lv}伤害补正", "")
        if raw_c.strip():
            lv_corr[lv] = _num(raw_c)

    # 对甲比例：导弹页字段名不同，做一次兜底
    # 该装备自身的强化上限：扫描页面上所有「强化+Nxxx」字段取最大 N，
    # 一个都没有时按稀有度兜底。
    # 这一步很关键：舰载机武器库里存了 +0~+13 全部档位，
    # 但白色飞机只能强化到 +3，不截断就会取到 +13 的数值。
    enhance_seen = [int(mm.group(1)) for mm in
                    (re.match(r"强化\+(\d+)", k) for k in params) if mm]
    observed = max(enhance_seen) if enhance_seen else 0
    rarity_max = RARITY_MAX_LEVEL.get(params.get("稀有度", ""), 13)
    max_level = observed if observed > 0 else rarity_max

    armor = parse_armor(params.get("对甲比例") or params.get("导弹先锋对甲比例", ""))
    if not any(armor):
        armor = [100.0, 100.0, 100.0]

    item = {
        "name": title,
        "base_name": base_name,
        "tier": tier,
        "category": category,
        "type": params.get("类型", category),
        "rarity": params.get("稀有度", ""),
        "faction": params.get("所属阵营", ""),
        "damage": dmg,
        "count": cnt,
        "reload": reload_s,
        "max_damage": max_dmg,
        "max_count": max_cnt,
        "max_reload": max_reload or reload_s,
        "armor": armor,
        "correction": correction,
        "correction_max": corr_max,
        "levels": {"damage": lv_damage, "reload": lv_reload, "correction": lv_corr},
        "max_level": max_level,
        "ammo": params.get("弹药", ""),
        "traits": params.get("特性", ""),
        "skill_name": params.get("技能名", ""),
        "skill_desc": params.get("技能描述", ""),
        "ship_types": params.get("适用舰种", "") or params.get("主武器适用", ""),
        "ship_types_disabled": params.get("禁用舰种", ""),
        "url": "https://wiki.biligame.com/blhx/" + urllib.parse.quote(title),
        "raw": params,
    }

    # 装备绿字（炮击/雷击/防空/航空…），评分时可叠加进舰船面板
    bonus = {}
    for key in ("炮击", "雷击", "防空", "航空", "命中", "装填", "反潜",
                "机动", "耐久", "幸运"):
        if params.get(key, "").strip():
            val = _num(params[key])
            if val:
                bonus[key] = val
    item["stat_bonus"] = bonus
    return item


def parse_all(texts: dict[str, str], progress=None) -> list[dict]:
    """批量解析，单页异常不影响整体。"""
    items = []
    total = len(texts)
    for idx, (title, text) in enumerate(texts.items(), 1):
        try:
            it = parse_page(title, text)
            if it:
                items.append(it)
        except Exception:  # noqa: BLE001
            continue
        if progress and idx % 50 == 0:
            progress(idx, total)
    return items


# ---------------------------------------------------------------------------
# 舰载机武器库（机枪 / 炸弹 / 鱼雷 三张数据库表）
# ---------------------------------------------------------------------------
PLANE_DB_PAGES = {
    "mg": "模板:舰载机图鉴/数据库/机枪",
    "bomb": "模板:舰载机图鉴/数据库/炸弹",
    "torp": "模板:舰载机图鉴/数据库/鱼雷",
}


def parse_plane_db(texts: dict) -> dict:
    """解析 #switch 数据表。

    每一行的形式为：
        名称=伤害0,伤害1,...,伤害13;附加1;附加2;附加3

    * 机枪：附加 = 射速列表;射程;射角
    * 炸弹：附加 = 伤害范围;散布范围;对甲比例
    * 鱼雷：附加 = 航速;对甲比例
    伤害列表的 14 个位置对应强化 +0 ~ +13，空位表示该档没有数据。
    """
    out = {"mg": {}, "bomb": {}, "torp": {}}
    for kind, page in PLANE_DB_PAGES.items():
        raw = texts.get(page) or texts.get(page.replace("模板:", "Template:")) or ""
        if not raw:
            continue
        raw = _COMMENT.sub("", raw)
        for line in raw.split("\n"):
            line = line.strip()
            if not line.startswith("|") or "=" not in line:
                continue
            key, val = line[1:].split("=", 1)
            key = key.strip()
            if not key or key.endswith("TX"):   # 跳过表头行
                continue
            parts = val.split(";")
            dmg = {}
            for i, s in enumerate(parts[0].split(",")):
                s = s.strip()
                if not s or s in ("？", "?", "-"):
                    continue
                try:
                    dmg[i] = float(s)
                except ValueError:
                    continue
            if kind == "mg":
                rates = [x.strip() for x in (parts[1].split(",") if len(parts) > 1 else [])]
                out["mg"][key] = {"damage": dmg, "rate": rates,
                                  "range": parts[2].strip() if len(parts) > 2 else "",
                                  "angle": parts[3].strip() if len(parts) > 3 else ""}
            elif kind == "bomb":
                out["bomb"][key] = {"damage": dmg,
                                    "armor": parse_armor(parts[3] if len(parts) > 3 else "")}
            else:
                out["torp"][key] = {"damage": dmg,
                                    "armor": parse_armor(parts[2] if len(parts) > 2 else "")}
    return out


def fetch_plane_db(progress=None) -> dict:
    """联网拉取并保存武器库（只有 3 个页面，很快）。"""
    texts = fetch_texts(list(PLANE_DB_PAGES.values()), progress if progress else None)
    db = parse_plane_db(texts)
    if db["bomb"] or db["mg"] or db["torp"]:
        tmp = plane_db_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, plane_db_path())
    return db


def load_plane_db() -> dict:
    """读取武器库：先用户目录，再内置快照。"""
    for path in (plane_db_path(), os.path.join(_bundle_dir(), "data", "plane_weapons.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                db = json.load(f)
            if db.get("bomb") or db.get("mg"):
                return db
        except Exception:  # noqa: BLE001
            continue
    return {"mg": {}, "bomb": {}, "torp": {}}


_MOUNT_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*(.+)$")
MOUNT_FIELDS = (("机枪", "mg"), ("炸弹", "bomb"), ("鱼雷", "torp"))


def _rate_levels(raw: list) -> dict:
    """把「75,,,70,,,66,64,,,60」这类射速列表转成 {档位: 发/分}。

    与伤害列表同构：14 个槽位对应 +0 ~ +13，空位表示该档没有数据；
    数值保持 wiki 的「发/分」原样，换算成发/秒在评分时再做（见 MG_RATE_UNIT）。
    """
    out = {}
    for i, s in enumerate(raw or []):
        s = str(s).strip()
        if not s or s in ("？", "?", "-"):
            continue
        try:
            out[i] = float(s)
        except ValueError:
            continue
    return out


def attach_plane_mounts(items: list[dict], db: dict) -> None:
    """把舰载机的『4 x 1000lb 炸弹T0』这类挂载串解析成真实武器数值。

    数据库的键本身带「数量 x」前缀（2x 与 4x 的单发伤害可能不同），
    所以先用整串匹配，匹配不到再去掉数量前缀重试。
    """
    for it in items:
        if it["category"] != "舰载机":
            continue
        mounts: dict[str, list] = {"mg": [], "bomb": [], "torp": []}
        for field, kind in MOUNT_FIELDS:
            raw = (it["raw"].get(field) or "").strip()
            if not raw:
                continue
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                m = _MOUNT_RE.match(part)
                count, name = (int(m.group(1)), m.group(2).strip()) if m else (1, part)
                table = db.get(kind) or {}
                entry = table.get(part) or table.get(name)
                if not entry:
                    continue
                row = {"name": name, "count": count, "damage": entry.get("damage", {})}
                if kind == "mg":
                    row["rate"] = _rate_levels(entry.get("rate") or [])
                    row["range"] = entry.get("range", "")
                    row["angle"] = entry.get("angle", "")
                else:
                    row["armor"] = entry.get("armor", [0, 0, 0])
                mounts[kind].append(row)
        it["mounts"] = mounts


# ---------------------------------------------------------------------------
# 抓取流程与缓存
# ---------------------------------------------------------------------------
def scrape(progress=None) -> list[dict]:
    """完整抓取流程：目录 → 页面 → 解析 → 挂载 → 排序。

    progress(stage:str, done:int, total:int) 用于界面进度条。
    """
    def stage(name, done, total):
        if progress:
            progress(name, done, total)

    stage("获取装备目录", 0, 0)
    titles: list[str] = []
    seen = set()
    for t in list_category("Category:装备"):
        if t not in seen:
            seen.add(t)
            titles.append(t)
    stage(f"获取装备目录（{len(titles)} 项）", len(titles), len(titles))
    if not titles:
        raise RuntimeError("未能获取到装备页面列表")

    stage("下载页面数据", 0, len(titles))
    texts = fetch_texts(titles, lambda d, t: stage("下载页面数据", d, t), len(titles))

    stage("解析数据", 0, len(texts))
    items = parse_all(texts, lambda d, t: stage("解析数据", d, t))
    items = [it for it in items if it["category"] not in EXCLUDED_CATEGORIES]

    stage("获取舰载机武器库", 0, 0)
    try:
        db = fetch_plane_db()
    except Exception:  # noqa: BLE001
        db = load_plane_db()
    attach_plane_mounts(items, db)

    items.sort(key=lambda x: (x["category"], x["type"], x["name"]))
    return items


def save_cache(items: list[dict]) -> str:
    """写入装备缓存 JSON。"""
    path = cache_path()
    payload = {
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "source": "https://wiki.biligame.com/blhx/装备图鉴",
        "items": items,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path


def load_data() -> tuple[list[dict], str]:
    """读取装备数据：用户缓存优先，其次内置快照。返回 (列表, 数据时间)。"""
    seen = set()
    for path in (cache_path(), bundled_data_path()):
        real = os.path.abspath(path)
        if real in seen:
            continue
        seen.add(real)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            items = payload.get("items", [])
            if items:
                tag = payload.get("updated", "")
                if getattr(sys, "frozen", False) and path == bundled_data_path():
                    tag = (tag + "（内置快照）").strip()
                return items, tag
        except Exception:  # noqa: BLE001
            continue
    return [], ""


# ---------------------------------------------------------------------------
# 评分引擎
# ---------------------------------------------------------------------------
def default_params() -> dict:
    """评分参数的默认值（界面可改）。"""
    return {
        "炮击": 100.0,
        "雷击": 100.0,
        "防空": 100.0,
        "航空": 100.0,
        "属性效率": 100.0,   # %
        "装填值": 100.0,     # 影响装填系数 √(200/(装填值+100))
        "增伤": 0.0,         # %
        "debuff": 0.0,       # %
        "等级差": 0.0,       # 己方等级 - 对方等级，每级 ±2%
        "暴击倍率": 1.0,
        "武器效率": 100.0,   # %
        "强化等级": 13,      # 0/3/6/7/10/11/13
        "计入装备属性": True,
        "计入动画": True,
    }


# 不同类别参与计算的属性
STAT_FOR_CATEGORY = {"舰炮": "炮击", "导弹": "雷击", "鱼雷": "雷击",
                     "防空炮": "防空", "舰载机": "航空"}


def _int_keys(d: dict) -> dict:
    """JSON 反序列化后键会变成字符串，这里统一转回 int。"""
    out = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def pick_level(levels: dict, want: int, default=None):
    """取「不高于 want 的最高档」的数值；一档都没有时取最低档。

    这是「选 +13 但装备只到 +10 就按 +10 算」的实现。
    """
    lv = _int_keys(levels)
    if not lv:
        return default
    ks = [k for k in lv if k <= want]
    return lv[max(ks) if ks else min(lv)]


def used_level(levels: dict, want: int) -> int:
    """实际生效的档位编号（用于界面提示）。"""
    lv = _int_keys(levels)
    if not lv:
        return 0
    ks = [k for k in lv if k <= want]
    return max(ks) if ks else min(lv)


def stat_value(item: dict, params: dict) -> tuple[float, float]:
    """返回 (参与计算的属性值, 装备自身加成)。

    勾选「计入装备属性」时，装备绿字（如 +45 炮击）会叠加到舰船面板上。
    """
    key = STAT_FOR_CATEGORY.get(item["category"], "炮击")
    base = float(params.get(key, 100.0))
    bonus = 0.0
    if params.get("计入装备属性", True):
        b = item.get("stat_bonus", {})
        if item["category"] == "舰炮":
            bonus = max(b.get("炮击", 0.0), 0.0)
        elif item["category"] in ("鱼雷", "导弹"):
            bonus = max(b.get("雷击", 0.0), 0.0)
        elif item["category"] == "防空炮":
            bonus = max(b.get("防空", 0.0), 0.0)
        elif item["category"] == "舰载机":
            bonus = max(b.get("航空", 0.0), 0.0)
    return base + bonus, bonus


def _mods(params: dict) -> float:
    """通用乘区：增伤 × 敌方 debuff × 等级压制 × 暴击倍率。"""
    return ((1 + float(params.get("增伤", 0.0)) / 100.0)
            * (1 + float(params.get("debuff", 0.0)) / 100.0)
            * (1 + float(params.get("等级差", 0.0)) * 0.02)
            * float(params.get("暴击倍率", 1.0)))


def _cycle(item: dict, reload_s: float, params: dict) -> float:
    """开火/出击间隔。

    舰炮类 = 装填时间 × √(200/(装填值+100)) + 前摇后摇
    舰载机 = 只算出击冷却（没有开火动画）
    """
    k = math.sqrt(200.0 / (float(params.get("装填值", 100.0)) + 100.0))
    if item.get("category") == "舰载机":
        anim = 0.0
    elif params.get("计入动画", True):
        anim = ANIM_BY_TYPE.get(item["type"], 0.26)
    else:
        anim = 0.0
    return max(k * reload_s + anim, 0.05)


def score_gun(item: dict, params: dict, key: str = "轻甲",
              window: float | None = None) -> dict | None:
    """舰炮 / 导弹 / 鱼雷 / 防空炮评分。

    计算链：
        属性系数 = 1 + 属性值/100 × 属性效率
        单发伤害 = 属性系数 × 单发 × 修正比例 × 武器效率
        单轮伤害 = 单发伤害 × 弹数 × 对甲效率（防空炮无对甲）
        单轮伤害 ×= 增伤 × debuff × 等级压制 × 暴击
        开火次数 = floor(窗口 / 开火间隔) + 1     ← t=0 打第一轮
        评分     = 单轮伤害 × 开火次数

    key: "轻甲"/"中甲"/"重甲"/"对空"
    """
    cat = item["category"]
    if cat not in ("舰炮", "鱼雷", "防空炮", "导弹"):
        return None

    want_param = int(params.get("强化等级", 13))
    want = min(want_param, int(item.get("max_level") or want_param))
    lv = item.get("levels") or {}
    dmg = pick_level(lv.get("damage", {}), want)          # (单发, 弹数)
    reload_s = pick_level(lv.get("reload", {}), want)     # 装填秒
    corr = pick_level(lv.get("correction", {}), want)     # 伤害补正 %
    if not dmg or not dmg[0] or not reload_s:
        return None

    stat, bonus = stat_value(item, params)
    eff = float(params.get("属性效率", 100.0)) / 100.0
    w_eff = float(params.get("武器效率", 100.0)) / 100.0
    attr = 1 + (stat / 100.0) * eff

    if cat == "防空炮":
        # 防空公式：无武器修正比例、无对甲效率
        corr_f = 1.0
        armor_pct = None
        per_hit = attr * dmg[0] * w_eff
    else:
        corr_f = (corr or 100.0) / 100.0
        armor_pct = item["armor"][ARMOR_KEYS.index(key)] / 100.0
        per_hit = attr * dmg[0] * corr_f * w_eff

    # 单轮总伤害：先算「未计护甲」的原始值（列表里展示用），再乘对甲效率
    volley_raw = per_hit * dmg[1] * _mods(params)
    armor_mult = armor_pct if armor_pct is not None else 1.0
    volley = volley_raw * armor_mult

    cycle = _cycle(item, reload_s, params)
    win = SCORE_WINDOW if window is None else float(window)
    shots = int(win // cycle) + 1
    total = volley * shots

    return {
        "value": total,          # 窗口内总伤害（排序用）
        "dps": total / win,
        "volley": volley,        # 单轮（含对甲）
        "volley_raw": volley_raw,
        "cycle": cycle,
        "shots": shots,
        "window": win,
        "correction": corr_f,
        "armor_pct": armor_pct,
        "reload": reload_s,
        "count": dmg[1],
        "damage": dmg[0],
        "stat": stat,
        "bonus": bonus,
        "attr": attr,
        "level_used": used_level(lv.get("damage", {}), want),
        "kind": "aa" if cat == "防空炮" else "gun",
    }


def _weapon_eff(name: str, kind: str) -> float:
    """航空武器属性效率：航弹 80%，火箭弹 / 鱼雷 / 机枪 100%。"""
    if kind in ("torp", "mg"):
        return 1.0
    for kw in ("火箭弹", "HVAR", "RP-3", "RS-82", "S-21", "Wfr.Gr", "TinyTim"):
        if kw in (name or ""):
            return 1.0
    return 0.8


def score_plane(item: dict, params: dict, window: float | None = None) -> dict:
    """舰载机评分。

    单架次挂载：
        对空 = Σ(机枪单发 × 数量) × (1 + 航空/100 × 属性效率 × 100%)
        对甲 = Σ(炸弹/鱼雷单发 × 数量 × 对甲效率)
               × (1 + 航空/100 × 属性效率 × 武器属性效率)
    77 秒累计：
        出击间隔 = √(200/(装填值+100)) × 标准射速 + 动画
        架次     = floor(77 / 出击间隔) + 1
        评分     = 单架次 × 架次
    """
    if item["category"] != "舰载机":
        return {}
    want_param = int(params.get("强化等级", 13))
    want = min(want_param, int(item.get("max_level") or want_param))
    mounts = item.get("mounts") or {}
    stat, bonus = stat_value(item, params)
    eff = float(params.get("属性效率", 100.0)) / 100.0
    mods = _mods(params)

    # 架次：用舰载机自己的标准射速（强化后）折算
    reload_s = pick_level((item.get("levels") or {}).get("reload", {}), want) or 0
    cycle = _cycle(item, reload_s, params) if reload_s else 0.0
    win = SCORE_WINDOW if window is None else float(window)
    sorties = int(win // cycle) + 1 if cycle else 1

    res: dict[str, dict] = {}

    # ---- 机枪 → 对空 ----
    mg_rows = mounts.get("mg") or []
    mg_acc = 0.0
    for m in mg_rows:
        d = pick_level(m.get("damage", {}), want, 0.0) or 0.0
        mg_acc += d * m.get("count", 1) * (1 + stat / 100.0 * eff * _weapon_eff(m["name"], "mg"))
    if mg_acc:
        per = mg_acc * mods
        res["对空"] = {
            "value": per * sorties,
            "per_sortie": per,
            "sorties": sorties,
            "cycle": cycle,
            "window": win,
            "mounts": [(m["name"], m.get("count", 1),
                        pick_level(m.get("damage", {}), want, 0.0) or 0.0) for m in mg_rows],
            "kind": "plane_aa",
            "stat": stat,
            "bonus": bonus,
            "attr": 1 + stat / 100.0 * eff,
        }

    # ---- 炸弹 / 鱼雷 → 对甲 ----
    for idx, armor in enumerate(ARMOR_KEYS):
        rows = []
        total = 0.0
        for kind in ("bomb", "torp"):
            for m in mounts.get(kind) or []:
                d = pick_level(m.get("damage", {}), want, 0.0) or 0.0
                pct = (m.get("armor") or [0, 0, 0])[idx] / 100.0
                e = _weapon_eff(m["name"], kind)
                part = d * m.get("count", 1) * pct * (1 + stat / 100.0 * eff * e)
                if part:
                    total += part
                    rows.append((m["name"], m.get("count", 1), d, pct, kind))
        if total:
            per = total * mods
            res[armor] = {
                "value": per * sorties,
                "per_sortie": per,
                "sorties": sorties,
                "cycle": cycle,
                "window": win,
                "mounts": rows,
                "kind": "plane",
                "stat": stat,
                "bonus": bonus,
                "attr": 1 + stat / 100.0 * eff,
            }
    return res


def plane_payload(item: dict, params: dict) -> float:
    """单架次挂载总伤害（不含对甲效率），列表的「单轮基础」列用。"""
    want_param = int(params.get("强化等级", 13))
    want = min(want_param, int(item.get("max_level") or want_param))
    mounts = item.get("mounts") or {}
    stat, _ = stat_value(item, params)
    eff = float(params.get("属性效率", 100.0)) / 100.0
    total = 0.0
    for kind in ("mg", "bomb", "torp"):
        for m in mounts.get(kind) or []:
            d = pick_level(m.get("damage", {}), want, 0.0) or 0.0
            e = _weapon_eff(m["name"], kind)
            total += d * m.get("count", 1) * (1 + stat / 100.0 * eff * e)
    return total * _mods(params)


def score_all(items: list[dict], params: dict) -> None:
    """给每件装备写回 score 字典。"""
    for it in items:
        cat = it["category"]
        if cat == "舰载机":
            it["score"] = score_plane(it, params)
            it["payload"] = plane_payload(it, params)
        elif cat in ("舰炮", "导弹", "鱼雷", "防空炮"):
            keys = ("对空",) if cat == "防空炮" else ARMOR_KEYS
            res = {}
            for k in keys:
                r = score_gun(it, params, k)
                if r:
                    res[k] = r
            it["score"] = res
        else:
            it["score"] = {}


def simulate(item: dict, params: dict, seconds: float = SCORE_WINDOW) -> dict:
    """任意时长的输出测试（默认 77 秒，与评分口径一致）。"""
    out = {"seconds": seconds, "kind": "", "rows": []}
    cat = item["category"]
    if cat in ("舰炮", "导弹", "鱼雷", "防空炮"):
        out["kind"] = "gun"
        keys = ("对空",) if cat == "防空炮" else ARMOR_KEYS
        for k in keys:
            r = score_gun(item, params, k, window=seconds)
            if r:
                out["rows"].append((k, r))
    elif cat == "舰载机":
        out["kind"] = "plane"
        sc = score_plane(item, params, window=seconds)
        for k, r in sc.items():
            out["rows"].append((k, r))
    return out


# ---------------------------------------------------------------------------
# 资源：图标
# ---------------------------------------------------------------------------
def icons_dir() -> str:
    return os.path.join(_bundle_dir(), "assets", "icons")


def load_icon_map() -> dict[str, str]:
    """返回 {装备名: 图标 PNG 绝对路径}。"""
    base = icons_dir()
    try:
        with open(os.path.join(base, "icons.json"), "r", encoding="utf-8") as f:
            mapping = json.load(f)
        return {k: os.path.join(base, v) for k, v in mapping.items()}
    except Exception:  # noqa: BLE001
        return {}
