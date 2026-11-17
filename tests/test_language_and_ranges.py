from __future__ import annotations

import unittest

from gui_app import AutoFoilStudio, BUILTIN_AIRFOIL_LABEL_EN


class LanguageAndRangeTests(unittest.TestCase):
    def test_header_uses_content_height_and_does_not_clip_subtitle(self) -> None:
        app = AutoFoilStudio(smoke_test=True)
        try:
            app.deiconify()
            app.update()
            self.assertGreaterEqual(
                app.header_subtitle_label.winfo_height(),
                app.header_subtitle_label.winfo_reqheight(),
            )
            self.assertGreaterEqual(
                app.header.winfo_height(),
                app.header.winfo_reqheight(),
            )
        finally:
            app.destroy()

    def test_live_language_switch_and_extended_refinement_ranges(self) -> None:
        app = AutoFoilStudio(smoke_test=True)
        try:
            app.language_var.set("English")
            app._on_language_changed()
            self.assertEqual(app.language_code, "en")
            self.assertEqual(app.airfoil_path_var.get(), BUILTIN_AIRFOIL_LABEL_EN)
            self.assertEqual(app.main_notebook.tab(app.geometry_tab, "text"), "Airfoil & Mesh")
            app.global_refinement_var.set("10")
            app.wake_refinement_var.set("12")
            app.domain_scale_var.set("2.5")
            settings = app._collect_settings()
            self.assertEqual(settings.global_refinement, 10.0)
            self.assertEqual(settings.wake_refinement, 12.0)
            self.assertEqual(settings.domain_scale, 2.5)
            self.assertEqual(settings.language, "en")
            app.language_var.set("中文")
            app._on_language_changed()
            self.assertEqual(app.main_notebook.tab(app.geometry_tab, "text"), "翼型与网格")
            app.global_refinement_var.set("0.05")
            self.assertEqual(app._collect_settings().global_refinement, 0.05)
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
