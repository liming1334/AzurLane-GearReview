"""核心逻辑的回归测试（标准库 unittest，无需 pytest）。

跑法（在项目根目录）：
    python -m unittest discover -s tests -v

为什么用 unittest：项目的依赖靠 vendor/ 解压 wheel，pip 装不了 pytest，
所以只用标准库。测试分两类：
  * 纯逻辑：用合成的小数据，不依赖抓取结果，任何环境都能跑；
  * 数据体检：读 data/equipment.json 与 assets/icons/icons.json，
    缓存缺失时自动 skip，不影响纯逻辑部分。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import core  # noqa: E402


# ---------------------------------------------------------------------------
# 合成数据：只放评分用得到的字段
# ---------------------------------------------------------------------------
def make_plane(max_level=3, dmg=None, reload_levels=None, name="F4F野猫T1"):
    """造一架只有机枪的舰载机。"""
    return {
        "name": name,
        "category": "舰载机",
        "type": "战斗机",
        "rarity": "白色",
        "max_level": max_level,
        "levels": {"reload": reload_levels if reload_levels is not None else {0: 5.0, 3: 4.0}},
        "stat_bonus": {},
        "mounts": {
            "mg": [{"name": "12.7mm机枪T1", "count": 6,
                    "damage": dmg if dmg is not None else {0: 22.0, 3: 33.0, 13: 68.0}}],
            "bomb": [],
            "torp": [],
        },
    }


def make_gun(dmg=(100.0, 2.0), reload=4.0, correction=100.0, category="舰炮",
             type_="驱逐炮", armor=(100.0, 100.0, 100.0)):
    return {
        "name": "测试炮",
        "category": category,
        "type": type_,
        "rarity": "金色",
        "max_level": 13,
        "levels": {"damage": {0: dmg}, "reload": {0: reload}, "correction": {0: correction}},
        "armor": list(armor),
        "stat_bonus": {},
    }


# ---------------------------------------------------------------------------
# 一、强化档位选择：全程「不高于目标档的最高档」
# ---------------------------------------------------------------------------
class TestPickLevel(unittest.TestCase):
    def test_takes_highest_not_above_target(self):
        lv = {0: 1.0, 3: 2.0, 6: 3.0, 10: 4.0}
        self.assertEqual(core.pick_level(lv, 13), 4.0)   # 只到 +10 就给 +10 的值
        self.assertEqual(core.pick_level(lv, 6), 3.0)
        self.assertEqual(core.pick_level(lv, 5), 2.0)    # 5 落在空档 → 退到 ≤5 的最高档 +3
        self.assertEqual(core.pick_level(lv, 3), 2.0)

    def test_all_levels_above_want_falls_back_to_lowest(self):
        # 数据里一档都不 ≤ want 时取最低档，避免返回 None 把整件装备算成 0
        self.assertEqual(core.pick_level({10: 5.0, 13: 9.0}, 3), 5.0)

    def test_empty_returns_default(self):
        self.assertIsNone(core.pick_level({}, 13))
        self.assertEqual(core.pick_level({}, 13, 7.0), 7.0)
        self.assertEqual(core.pick_level(None, 13, 7.0), 7.0)

    def test_string_keys_from_json(self):
        # JSON 反序列化后键是字符串，必须照样能取
        self.assertEqual(core.pick_level({"0": 1.0, "13": 9.0}, 13), 9.0)
        self.assertEqual(core.pick_level({"3": 2.0}, 13), 2.0)

    def test_used_level_reports_effective_tier(self):
        self.assertEqual(core.used_level({0: 1.0, 10: 2.0}, 13), 10)
        self.assertEqual(core.used_level({0: 1.0, 10: 2.0}, 6), 0)
        self.assertEqual(core.used_level({}, 13), 0)


# ---------------------------------------------------------------------------
# 二、机枪射速列表的解析（第 10 轮补的实现）
# ---------------------------------------------------------------------------
class TestRateLevels(unittest.TestCase):
    def test_sparse_list(self):
        # wiki 的射速是稀疏列表，空位表示该档没有数据
        self.assertEqual(core._rate_levels(["75", "", "", "70", "", "", "66"]),
                         {0: 75.0, 3: 70.0, 6: 66.0})

    def test_placeholders_and_blanks_skipped(self):
        self.assertEqual(core._rate_levels(["？", "?", "-", "", "  "]), {})
        self.assertEqual(core._rate_levels([]), {})
        self.assertEqual(core._rate_levels(None), {})

    def test_whitespace_and_number_types(self):
        self.assertEqual(core._rate_levels([" 79 ", 75, ""]), {0: 79.0, 1: 75.0})

    def test_garbage_values_skipped_not_fatal(self):
        # 单档坏数据不该让整件装备解析失败
        self.assertEqual(core._rate_levels(["75", "abc", "70"]), {0: 75.0, 2: 70.0})

    def test_feeds_pick_level(self):
        rates = core._rate_levels(["75", "", "", "70", "", "", "66", "64", "", "", "60"])
        self.assertEqual(core.pick_level(rates, 13), 60.0)
        self.assertEqual(core.pick_level(rates, 3), 70.0)


# ---------------------------------------------------------------------------
# 三、强化上限：白/蓝按稀有度截断，紫及以上不动
# ---------------------------------------------------------------------------class TestEffectiveMaxLevel(unittest.TestCase):
    def test_white_is_capped_at_3(self):
        # 「强化+7伤害 = 待补充」占位文本不该把白色顶到 +7
        self.assertEqual(core.effective_max_level("白色", 7), 3)
        self.assertEqual(core.effective_max_level("白色", 13), 3)
        self.assertEqual(core.effective_max_level("白色", 3), 3)

    def test_blue_is_capped_at_6(self):
        # 补正多写一档（+7）、或留空的 +13 字段，都不代表装备能到那档
        self.assertEqual(core.effective_max_level("蓝色", 7), 6)
        self.assertEqual(core.effective_max_level("蓝色", 13), 6)
        self.assertEqual(core.effective_max_level("蓝色", 6), 6)

    def test_purple_and_above_untouched(self):
        # 口径未定，紫色及以上仍按页面原值
        self.assertEqual(core.effective_max_level("紫色", 11), 11)
        self.assertEqual(core.effective_max_level("紫色", 13), 13)
        self.assertEqual(core.effective_max_level("金色", 13), 13)
        self.assertEqual(core.effective_max_level("彩色", 13), 13)

    def test_no_enhancement_fields_falls_back_to_rarity(self):
        self.assertEqual(core.effective_max_level("白色", 0), 3)
        self.assertEqual(core.effective_max_level("蓝色", 0), 6)
        self.assertEqual(core.effective_max_level("紫色", 0), 10)


# ---------------------------------------------------------------------------
# 四、伤害补正：页面没写时按 wiki 模板的兜底公式补
# ---------------------------------------------------------------------------
class TestCorrectionFallback(unittest.TestCase):
    """wiki 的装备模板对空的「强化+N伤害补正」有 #expr 兜底。

    例：双联装203mmSKC主炮改T0 页面上 `强化+13伤害补正=` 是空的，
    但 wiki 渲染出来是 130%（110 × 1.18）。只读页面参数会停在 110%。
    """

    def test_fallback_values(self):
        self.assertEqual(core.correction_fallback(110, 13), 130.0)
        self.assertEqual(core.correction_fallback(105, 13), 124.0)
        self.assertEqual(core.correction_fallback(100, 13), 118.0)
        self.assertEqual(core.correction_fallback(100, 11), 104.0)
        self.assertEqual(core.correction_fallback(110, 7), 114.0)

    def test_rounding_is_half_up(self):
        # MediaWiki 的 round0 是四舍五入，不是 Python 的银行家舍入
        self.assertEqual(core.correction_fallback(125, 13), 148.0)   # 147.5
        self.assertEqual(core.correction_fallback(125, 11), 130.0)   # 130.0

    def test_explicit_value_wins(self):
        params = {"伤害补正": "110", "强化+13伤害补正": "120"}
        lv = core.build_correction_levels(params, "舰炮", 110.0, "金色")
        self.assertEqual(lv[13], 120.0)      # 页面写了就用页面的，不套 1.18

    def test_tier_depends_on_rarity(self):
        # 蓝 → +7、紫 → +11、金/彩 → +13，其余档位不补
        blue = core.build_correction_levels({"伤害补正": "110"}, "舰炮", 110.0, "蓝色")
        self.assertEqual(blue, {0: 110.0, 7: 114.0})
        purple = core.build_correction_levels({"伤害补正": "110"}, "舰炮", 110.0, "紫色")
        self.assertEqual(purple, {0: 110.0, 11: 114.0})
        gold = core.build_correction_levels({"伤害补正": "110"}, "舰炮", 110.0, "金色")
        self.assertEqual(gold, {0: 110.0, 13: 130.0})

    def test_white_gets_no_fallback(self):
        white = core.build_correction_levels({"伤害补正": "110"}, "舰炮", 110.0, "白色")
        self.assertEqual(white, {0: 110.0})

    def test_plane_gets_no_fallback(self):
        # 舰载机模板没有这套兜底
        plane = core.build_correction_levels({"伤害补正": "100"}, "舰载机", 100.0, "金色")
        self.assertEqual(plane, {0: 100.0})

    def test_known_skc_case(self):
        # 双联装203mmSKC主炮改T0：页面 +13 字段为空，实际应为 130%
        params = {"伤害补正": "110", "强化+13伤害补正": "", "对甲比例": "80-115-75"}
        lv = core.build_correction_levels(params, "舰炮", 110.0, "金色")
        self.assertEqual(lv[13], 130.0)


# ---------------------------------------------------------------------------
# 五、对甲比例：wiki 写 75-110-75，即 75% / 110% / 75%，计算时要除以 100
# ---------------------------------------------------------------------------
class TestArmorPercent(unittest.TestCase):
    def test_parse_returns_percent_numbers(self):
        self.assertEqual(core.parse_armor("75-110-75"), [75.0, 110.0, 75.0])
        self.assertEqual(core.parse_armor("140-110-90"), [140.0, 110.0, 90.0])

    def test_missing_parts_padded_with_zero(self):
        self.assertEqual(core.parse_armor("80-115"), [80.0, 115.0, 0.0])

    def test_score_uses_fraction_of_percent(self):
        # 对甲比例 110% 要按 1.10 参与计算，不是 110
        params = core.default_params()
        params["计入动画"] = False
        item = make_gun(armor=(75.0, 110.0, 75.0))
        res = core.score_gun(item, params, key="中甲")
        self.assertAlmostEqual(res["armor_pct"], 1.10, places=6)
        self.assertAlmostEqual(res["volley"], res["volley_raw"] * 1.10, places=6)
        light = core.score_gun(item, params, key="轻甲")
        self.assertAlmostEqual(light["armor_pct"], 0.75, places=6)

    def test_plane_mount_armor_is_percent(self):
        item = make_plane(max_level=13, dmg={0: 10.0})
        item["mounts"]["bomb"] = [{"name": "500lb炸弹T1", "count": 2,
                                   "damage": {0: 100.0}, "armor": [80.0, 85.0, 100.0]}]
        res = core.score_plane(item, core.default_params())
        # 单架次对甲：100 × 2 × 0.80 × (1 + 1 × 1 × 0.8) = 288
        self.assertAlmostEqual(res["轻甲"]["per_sortie"], 288.0, places=6)


# ---------------------------------------------------------------------------
# 六、动画查表：类型名必须和数据类型完全一致
# ---------------------------------------------------------------------------
class TestAnimTable(unittest.TestCase):
    def test_submarine_torpedo_key_exists(self):
        # 之前写成 "潜艇鱼"，31 件潜艇鱼雷一直吃默认 0.26，比应有的 0.20 慢
        self.assertEqual(core.ANIM_BY_TYPE.get("潜艇鱼雷"), 0.20)
        self.assertNotIn("潜艇鱼", core.ANIM_BY_TYPE)

    def test_all_gun_and_torpedo_types_covered(self):
        wanted = {"驱逐炮", "轻巡炮", "重巡炮", "大口径重巡炮", "战列炮",
                  "导弹", "水面鱼雷", "潜艇鱼雷", "防空炮"}
        self.assertEqual(wanted - set(core.ANIM_BY_TYPE), set())

    def test_submarine_torpedo_cycle_uses_point_two(self):
        params = core.default_params()
        item = make_gun(dmg=(100.0, 3.0), reload=4.0, category="鱼雷",
                        type_="潜艇鱼雷", armor=(80.0, 100.0, 100.0))
        res = core.score_gun(item, params)
        self.assertAlmostEqual(res["cycle"], 4.0 + 0.20, places=6)


# ---------------------------------------------------------------------------
# 七、核心回归：装备自身强化上限必须截断武器库数值
# ---------------------------------------------------------------------------
class TestMaxLevelTruncation(unittest.TestCase):
    """第 9 轮修的 bug：F4F野猫T1 白色只能 +3，武器库却有 +0~+13。

    旧代码直接取 +13 的 68，正确是 +3 的 33。这条测试把它钉死。
    """

    def setUp(self):
        self.params = core.default_params()

    def test_white_plane_uses_plus3_not_plus13(self):
        item = make_plane(max_level=3, dmg={0: 22.0, 3: 33.0, 13: 68.0})
        res = core.score_plane(item, self.params)
        # 单架次对空 = 33 × 6 × (1 + 100/100 × 1) = 396
        self.assertAlmostEqual(res["对空"]["per_sortie"], 396.0, places=6)

    def test_buggy_value_would_be_different(self):
        # 反向确认：如果按 +13 的 68 算，单架次是 816，与正确值不同
        item = make_plane(max_level=3, dmg={0: 22.0, 3: 33.0, 13: 68.0})
        res = core.score_plane(item, self.params)
        self.assertNotAlmostEqual(res["对空"]["per_sortie"], 816.0, places=6)

    def test_gold_plane_can_use_plus13(self):
        item = make_plane(max_level=13, dmg={0: 22.0, 3: 33.0, 13: 68.0})
        res = core.score_plane(item, self.params)
        self.assertAlmostEqual(res["对空"]["per_sortie"], 68.0 * 6 * 2, places=6)

    def test_lower_target_below_cap_is_respected(self):
        # 上限 13 但用户只要 +3，应按 +3 算
        params = core.default_params()
        params["强化等级"] = 3
        item = make_plane(max_level=13, dmg={0: 22.0, 3: 33.0, 13: 68.0})
        res = core.score_plane(item, params)
        self.assertAlmostEqual(res["对空"]["per_sortie"], 396.0, places=6)

    def test_plane_sorties_over_77s(self):
        item = make_plane(max_level=3, dmg={0: 22.0, 3: 33.0, 13: 68.0})
        res = core.score_plane(item, self.params)
        # 出击间隔 = √(200/200) × 4 = 4 秒 → floor(77/4)+1 = 20 架次
        self.assertEqual(res["对空"]["sorties"], 20)
        self.assertAlmostEqual(res["对空"]["value"], 396.0 * 20, places=6)


# ---------------------------------------------------------------------------
# 八、舰炮 / 防空炮的 77 秒口径
# ---------------------------------------------------------------------------
class TestGunScoring(unittest.TestCase):
    def test_shots_count_includes_first_volley(self):
        params = core.default_params()
        params["计入动画"] = False
        res = core.score_gun(make_gun(reload=4.0), params)
        # 间隔 4 秒 → 77/4 = 19 余 1 → t=0 那轮 + 19 = 20 轮
        self.assertAlmostEqual(res["cycle"], 4.0, places=6)
        self.assertEqual(res["shots"], 20)

    def test_animation_adds_to_cycle(self):
        params = core.default_params()   # 计入动画 True，驱逐炮 0.26
        res = core.score_gun(make_gun(reload=4.0, type_="驱逐炮"), params)
        self.assertAlmostEqual(res["cycle"], 4.26, places=6)
        self.assertEqual(res["shots"], int(77 // 4.26) + 1)

    def test_volley_math(self):
        params = core.default_params()
        params["计入动画"] = False
        res = core.score_gun(make_gun(dmg=(100.0, 2.0)), params)
        # 属性系数 = 1 + 100/100 × 1 = 2 → 单发 200 → 单轮 200 × 2 弹 = 400
        self.assertAlmostEqual(res["volley_raw"], 400.0, places=6)
        self.assertAlmostEqual(res["value"], 400.0 * res["shots"], places=6)

    def test_armor_efficiency_applies(self):
        params = core.default_params()
        params["计入动画"] = False
        item = make_gun(armor=(50.0, 100.0, 150.0))
        light = core.score_gun(item, params, key="轻甲")
        heavy = core.score_gun(item, params, key="重甲")
        self.assertAlmostEqual(light["volley"], light["volley_raw"] * 0.5, places=6)
        self.assertAlmostEqual(heavy["volley"], heavy["volley_raw"] * 1.5, places=6)

    def test_aa_gun_has_no_correction_or_armor(self):
        params = core.default_params()
        params["计入动画"] = False
        item = make_gun(correction=50.0, category="防空炮", type_="防空炮")
        res = core.score_gun(item, params, key="对空")
        self.assertEqual(res["kind"], "aa")
        self.assertEqual(res["correction"], 1.0)      # 防空炮不乘修正比例
        self.assertIsNone(res["armor_pct"])           # 也没有对甲
        # 属性系数 2 × 单发 100 × 弹数 2，不吃修正比例（修正填 50 也没影响）
        self.assertAlmostEqual(res["damage"], 100.0, places=6)
        self.assertAlmostEqual(res["volley"], 400.0, places=6)

    def test_non_gun_category_returns_none(self):
        params = core.default_params()
        self.assertIsNone(core.score_gun({"category": "舰载机"}, params))

    def test_missing_reload_returns_none(self):
        params = core.default_params()
        item = make_gun()
        item["levels"]["reload"] = {}
        self.assertIsNone(core.score_gun(item, params))


# ---------------------------------------------------------------------------
# 九、舰载机挂载口径
# ---------------------------------------------------------------------------
class TestPlaneMounts(unittest.TestCase):
    def test_weapon_efficiency_bombs_80pct_rockets_100pct(self):
        self.assertAlmostEqual(core._weapon_eff("1000lb炸弹T1", "bomb"), 0.8)
        self.assertAlmostEqual(core._weapon_eff("HVAR火箭弹T1", "bomb"), 1.0)
        self.assertAlmostEqual(core._weapon_eff("5inch火箭弹", "bomb"), 1.0)
        self.assertAlmostEqual(core._weapon_eff("任何鱼雷", "torp"), 1.0)
        self.assertAlmostEqual(core._weapon_eff("7.7mm机枪", "mg"), 1.0)

    def test_mg_goes_to_aa_and_bombs_to_armor(self):
        item = make_plane(max_level=13, dmg={0: 10.0})
        item["mounts"]["bomb"] = [{"name": "500lb炸弹T1", "count": 2,
                                   "damage": {0: 100.0}, "armor": [80.0, 85.0, 100.0]}]
        res = core.score_plane(item, core.default_params())
        self.assertIn("对空", res)
        self.assertIn("轻甲", res)
        self.assertNotIn("对空", [k for k in res if k != "对空"])

    def test_mg_never_appears_in_armor_columns(self):
        item = make_plane(max_level=13, dmg={0: 10.0})
        item["mounts"]["bomb"] = []
        res = core.score_plane(item, core.default_params())
        self.assertNotIn("轻甲", res)   # 只有机枪的飞机没有对甲评分

    def test_payload_separates_mg_from_bombs(self):
        item = make_plane(max_level=13, dmg={0: 10.0})
        payload = core.plane_payload(item, core.default_params())
        # 10 × 6 × 2 = 120
        self.assertAlmostEqual(payload, 120.0, places=6)


# ---------------------------------------------------------------------------
# 十、数据体检（需要本地缓存，缺了自动跳过）
# ---------------------------------------------------------------------------
class TestDataIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, cls.tag = core.load_data()
        if not cls.items:
            raise unittest.SkipTest("没有 data/equipment.json 缓存，跳过数据体检")

    def test_item_count(self):
        self.assertEqual(len(self.items), 674)

    def test_category_counts(self):
        from collections import Counter
        c = Counter(i["category"] for i in self.items)
        self.assertEqual(c["舰炮"], 296)
        self.assertEqual(c["舰载机"], 177)
        self.assertEqual(c["防空炮"], 119)
        self.assertEqual(c["鱼雷"], 80)
        self.assertEqual(c["导弹"], 2)
        self.assertNotIn("设备", c)
        self.assertNotIn("特殊兵装", c)

    def test_every_item_has_positive_max_level(self):
        # max_level 是 0 会导致 want=0、所有档位都取最低，属于静默错算
        bad = [i["name"] for i in self.items if not int(i.get("max_level") or 0)]
        self.assertEqual(bad, [])

    def test_max_level_is_a_known_tier(self):
        # 强化档位只有这几档；出现别的值说明页面解析串位了
        valid = set(core.ENHANCE_LEVELS) - {0}
        bad = [(i["name"], i["max_level"]) for i in self.items
               if int(i["max_level"]) not in valid]
        self.assertEqual(bad, [])

    def test_white_and_blue_never_exceed_rarity_cap(self):
        # 第 11 轮：白/蓝按稀有度上限截断（蓝 62 件 +7、6 件空字段 13、白 1 件 7）
        over = [(i["name"], i["rarity"], i["max_level"]) for i in self.items
                if i.get("rarity") in ("白色", "蓝色")
                and int(i["max_level"]) > core.RARITY_MAX_LEVEL[i["rarity"]]]
        self.assertEqual(over, [])

    def test_known_blue_cases_capped(self):
        cases = {"305mm连装炮T0": 6,        # 补正写到 +7
                 "四联装340mm主炮Mle1912T3": 6,  # 空的 +13 字段
                 "三联装610mm鱼雷T2": 6}   # 旧代码在 +7 上取到垃圾值 → 整件无分
        for name, want in cases.items():
            it = [i for i in self.items if i["name"] == name]
            self.assertEqual(len(it), 1, name)
            self.assertEqual(it[0]["max_level"], want, name)

    def test_known_white_case_capped(self):
        it = [i for i in self.items if i["name"] == "410mm连装炮T1"]
        self.assertEqual(len(it), 1)
        self.assertEqual(it[0]["max_level"], 3)   # 「强化+7伤害 = 待补充」

    def test_every_item_gets_scored(self):
        # 档位取到空值会让整件装备静默无分，必须一件不漏
        items = [dict(i, score={}) for i in self.items]
        core.score_all(items, core.default_params())
        missing = [i["name"] for i in items if not i["score"]]
        self.assertEqual(missing, [])

    def test_skc_gun_has_plus13_correction(self):
        # 页面 +13 补正字段为空，靠模板兜底应为 130%
        it = [i for i in self.items if i["name"] == "双联装203mmSKC主炮改T0"]
        self.assertEqual(len(it), 1)
        lv = core._int_keys(it[0]["levels"]["correction"])
        self.assertEqual(lv[13], 130.0)

    def test_correction_tier_present_for_max_level(self):
        # 参与评分的四大类，每件都必须有自己稀有度对应的补正档位
        # （页面写了就用页面的，没写就用模板兜底）。舰载机的补正不进评分，不查。
        bad = []
        for i in self.items:
            if i["category"] not in core.CORRECTION_FALLBACK_CATEGORIES:
                continue
            tier = core.CORRECTION_TIER_BY_RARITY.get(i["rarity"])
            if not tier:
                continue
            lv = core._int_keys(i["levels"].get("correction") or {})
            if tier not in lv:
                bad.append((i["name"], i["rarity"], tier))
        self.assertEqual(bad, [])

    def test_rarity_fallback_covers_all_rarities(self):
        # RARITY_MAX_LEVEL 是「页面一个强化字段都没有」时的兜底，
        # 每个出现过的稀有度都必须有对应值，否则会静默按 want 走
        missing = sorted({i.get("rarity") for i in self.items} - set(core.RARITY_MAX_LEVEL))
        self.assertEqual(missing, [])

    def test_f4f_wildcat_known_case(self):
        hit = [i for i in self.items if i["name"] == "F4F野猫T1"]
        self.assertEqual(len(hit), 1)
        it = hit[0]
        self.assertEqual(it["max_level"], 3)
        mg = it["mounts"]["mg"][0]
        self.assertEqual(core.pick_level(mg["damage"], it["max_level"]), 33.0)

    def test_icons_cover_all_items(self):
        icons = core.load_icon_map()
        if not icons:
            self.skipTest("没有 assets/icons/icons.json")
        missing = [i["name"] for i in self.items if not icons.get(i["name"])]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
