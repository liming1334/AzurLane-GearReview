"""毛玻璃按钮的尺寸回归测试（需要能创建 Tk 窗口，否则自动跳过）。

第 11 轮修的 bug：贴底图时没把 padx/pady 归零，而 Tk 的 Button
请求尺寸 = 图片 + 2×padx + 2×pady，底图又按「当前尺寸」生成，
于是每贴一次宽 +20px、高 +6px，按几次就错位到点不到。

这里直接建真实窗口，反复贴图 / 点击 / 切主题，断言尺寸不漂移。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGlassButtonSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk  # noqa: F401
            from app.ui import App
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"无法创建 Tk 界面：{exc}")
        try:
            cls.app = App()
            cls.app.update()
            cls.app.update_idletasks()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"界面初始化失败：{exc}")
        cls.buttons = [b for b, _ in cls.app._glass_buttons]

    @classmethod
    def tearDownClass(cls):
        app = getattr(cls, "app", None)
        if app is not None:
            try:
                app.destroy()
            except Exception:  # noqa: BLE001
                pass

    def sizes(self):
        self.app.update_idletasks()
        return [(b.winfo_width(), b.winfo_height()) for b in self.buttons]

    def test_buttons_exist(self):
        # 清除背景 / 背景 / 切主题 / 输出测试
        self.assertGreaterEqual(len(self.buttons), 4)

    def test_repeated_glass_apply_is_idempotent(self):
        self.app._apply_glass_all()
        self.app.update()
        base = self.sizes()
        for _ in range(8):
            self.app._apply_glass_all()
            self.app.update()
            self.app.update_idletasks()
        self.assertEqual(self.sizes(), base, "反复贴底图后按钮尺寸发生变化")

    def test_clicks_do_not_grow_buttons(self):
        base = self.sizes()
        for b in self.buttons:
            b.event_generate("<Button-1>")
            b.event_generate("<ButtonRelease-1>")
        self.app.update()
        self.app.update_idletasks()
        self.assertEqual(self.sizes(), base, "点击后按钮尺寸发生变化")

    def test_theme_switch_does_not_grow_buttons(self):
        base = self.sizes()
        want = "night" if self.app.theme_key == "day" else "day"
        self.app.theme_key = want
        self.app._apply_theme()
        self.app.update()
        self.app.update_idletasks()
        self.assertEqual(self.sizes(), base, "切换主题后按钮尺寸发生变化")

    def test_padding_is_baked_into_texture(self):
        # 内边距归零后，底图必须比文字宽，否则文字会贴边
        self.app._apply_glass_all()
        self.app.update()
        for b in self.buttons:
            img = getattr(b, "_glass", None)
            if img is None:
                continue
            self.assertGreaterEqual(img.width(), b.winfo_reqwidth(),
                                    f"{b['text']} 的底图比按钮请求宽度还小")


if __name__ == "__main__":
    unittest.main(verbosity=2)
