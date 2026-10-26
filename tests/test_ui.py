"""界面回归测试（需要能创建 Tk 窗口，否则自动跳过）。

覆盖两件事：

1. **详情重建不泄漏**（第 12 轮修掉的 bug）。
   旧实现把每张卡片单独 `create_window` 到画布上，切换装备时只
   `canvas.delete("card")` —— 画布项没了，但卡片控件的父窗口仍是画布，
   所以每点一次就残留一批。开得多了详情内容会错位到屏幕左上角。
   现在所有卡片放在画布里的单个内层 Frame 中，重建时整体销毁。

2. **毛玻璃 / 背景功能已移除**：顶栏只留主题切换，没有背景相关按钮，
   按钮也不再挂图片。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter  # noqa: F401
            from app.ui import App
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"无法创建 Tk 界面：{exc}")
        try:
            cls.app = App()
            cls.app.update()
            cls.app.update_idletasks()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"界面初始化失败：{exc}")
        cls.app.var_cat.set("舰炮")
        cls.app._sync_types()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        app = getattr(cls, "app", None)
        if app is not None:
            try:
                app.destroy()
            except Exception:  # noqa: BLE001
                pass

    def _open(self, idx):
        ids = self.app.tree.get_children()
        self.app.tree.selection_set(ids[idx])
        self.app.tree.event_generate("<<TreeviewSelect>>")
        self.app.update()
        self.app.update_idletasks()

    # ---- 详情重建 -------------------------------------------------------
    def test_detail_rebuild_does_not_accumulate_widgets(self):
        self._open(0)
        first = len(self.app.detail_body.winfo_children())
        self.assertGreater(first, 0, "详情没有渲染出任何卡片")
        for i in range(1, 12):
            self._open(i)
            self.assertEqual(
                len(self.app.detail_body.winfo_children()), first,
                f"第 {i} 次打开后卡片控件数量变了，说明旧卡片没有销毁")
        # 画布只该挂一个内层 Frame
        self.assertEqual(len(self.app.canvas.winfo_children()), 1)

    def test_detail_widgets_stay_inside_canvas(self):
        self._open(3)
        self.app.update_idletasks()
        cx = self.app.canvas.winfo_rootx()
        cy = self.app.canvas.winfo_rooty()
        cw = self.app.canvas.winfo_width()
        for w in self.app.detail_body.winfo_children():
            x, y = w.winfo_rootx(), w.winfo_rooty()
            self.assertGreaterEqual(x, cx - 2, "卡片跑到画布左边外面")
            self.assertGreaterEqual(y, cy - 2, "卡片跑到画布上边外面")
            self.assertLessEqual(x, cx + cw + 2, "卡片跑到画布右边外面")

    def test_detail_resets_scroll_position(self):
        self._open(0)
        self.app.canvas.yview_moveto(1.0)
        self._open(1)
        self.assertLess(self.app.canvas.yview()[0], 0.01, "换装备后没有回到顶部")

    # ---- 主题 -----------------------------------------------------------
    def test_theme_toggle_switches_colors(self):
        start = self.app.theme_key
        self.app.toggle_theme()
        self.app.update()
        self.assertNotEqual(self.app.theme_key, start)
        self.assertEqual(self.app.cget("bg"), self.app.theme["window"])
        self.app.toggle_theme()      # 还原
        self.app.update()
        self.assertEqual(self.app.theme_key, start)

    def test_theme_toggle_keeps_detail_intact(self):
        self._open(2)
        before = len(self.app.detail_body.winfo_children())
        self.app.toggle_theme()
        self.app.update()
        self.assertEqual(len(self.app.detail_body.winfo_children()), before)
        self.app.toggle_theme()
        self.app.update()

    # ---- 已移除的功能 ---------------------------------------------------
    def test_header_has_only_theme_button(self):
        texts = []
        for w in self.app.header.winfo_children():
            try:
                if w.winfo_class() == "Button":
                    texts.append(w.cget("text"))
            except Exception:  # noqa: BLE001
                continue
        self.assertEqual(len(texts), 1, f"顶栏按钮应只剩主题切换，实际：{texts}")
        self.assertIn("夜间", texts[0] + "白天")

    def test_no_background_api_left(self):
        for name in ("choose_background", "clear_background",
                     "_render_background", "_apply_glass_all", "_glass_image"):
            self.assertFalse(hasattr(self.app, name), f"{name} 应已移除")

    def test_buttons_have_no_image(self):
        for w in self.app.header.winfo_children():
            if w.winfo_class() != "Button":
                continue
            self.assertEqual(str(w.cget("image")), "", "按钮不该再挂毛玻璃底图")


if __name__ == "__main__":
    unittest.main(verbosity=2)
