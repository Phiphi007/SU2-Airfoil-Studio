from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from gui_app import AutoFoilStudio


class GeometryLayoutTests(unittest.TestCase):
    def make_app(self, scaling: float = 4 / 3) -> AutoFoilStudio:
        configure_style = AutoFoilStudio._configure_style

        def scaled_style(app: AutoFoilStudio) -> None:
            app.tk.call("tk", "scaling", scaling)
            configure_style(app)

        with patch.object(AutoFoilStudio, "_configure_style", scaled_style):
            app = AutoFoilStudio(smoke_test=True)
        self.addCleanup(app.destroy)
        return app

    def assert_inside(self, widget: tk.Misc, parent: tk.Misc) -> None:
        self.assertTrue(widget.winfo_ismapped(), str(widget))
        x = widget.winfo_rootx() - parent.winfo_rootx()
        y = widget.winfo_rooty() - parent.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), parent.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), parent.winfo_height())

    def test_mesh_actions_remain_visible_after_resize_and_translation(self) -> None:
        app = self.make_app()
        for geometry in ("1360x880", "1180x680", "960x540"):
            for language in ("中文", "English", "中文"):
                with self.subTest(geometry=geometry, language=language):
                    app.geometry(geometry)
                    app.language_var.set(language)
                    app._on_language_changed()
                    app.update()
                    for button in (app.mesh_preview_button, app.mesh_defaults_button):
                        self.assert_inside(button, app.geometry_controls)
                        self.assert_inside(button, app)
                        self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                    self.assertGreater(app.geometry_form.canvas.winfo_height(), 100)
                    self.assert_inside(app.preview_canvas.get_tk_widget(), app.geometry_tab)
                    self.assert_inside(app.header_subtitle_label, app.header)
                    self.assertGreaterEqual(app.header_subtitle_label.winfo_height(),
                                            app.header_subtitle_label.winfo_reqheight())

    def test_high_dpi_form_fields_fit_available_width(self) -> None:
        app = self.make_app(scaling=8 / 3)  # 200% Windows scale, 192 pixels/inch.
        app.geometry("960x600")
        app.language_var.set("English")
        app._on_language_changed()
        app.update()

        def check_fields(parent: tk.Misc) -> None:
            for widget in parent.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Label)):
                    with self.subTest(widget=str(widget)):
                        left = widget.winfo_rootx() - app.geometry_form.content.winfo_rootx()
                        self.assertGreaterEqual(left, 0)
                        self.assertLessEqual(left + widget.winfo_width(),
                                             app.geometry_form.content.winfo_width())
                        self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())
                        if isinstance(widget, ttk.Button):
                            self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
                check_fields(widget)

        check_fields(app.geometry_form.content)
        for button in (app.mesh_preview_button, app.mesh_defaults_button):
            self.assert_inside(button, app)
            self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())

    def test_scroll_and_keyboard_focus_expose_fields_without_moving_actions(self) -> None:
        app = self.make_app()
        app.geometry("960x600")
        app.update()
        form = app.geometry_form
        button_y = app.mesh_preview_button.winfo_rooty()
        self.assertEqual(form.canvas.yview()[0], 0)
        # Wheel over a field scrolls only the form, not the plot or entire window.
        app.mesh_last_entry.event_generate("<MouseWheel>", delta=-120)
        app.update()
        self.assertGreater(form.canvas.yview()[0], 0)
        self.assertFalse(app.bind_all("<MouseWheel>"))
        form.canvas.yview_moveto(0)
        app.mesh_last_entry.event_generate("<FocusIn>")
        app.update()
        self.assert_inside(app.mesh_last_entry, form.canvas)
        self.assertEqual(app.mesh_preview_button.winfo_rooty(), button_y)
        form.canvas.yview_moveto(1)
        app.update()
        self.assert_inside(app.mesh_preview_button, app)
        app.global_refinement_var.set("8")
        app.mesh_defaults_button.invoke()
        self.assertEqual(float(app.global_refinement_var.get()), 1.0)

    def test_checkbuttons_use_checkmark_images_instead_of_clam_x(self) -> None:
        app = self.make_app()
        layout = ttk.Style(app).layout("Industrial.TCheckbutton")
        self.assertIn("Industrial.Checkbutton.indicator", str(layout))
        checked = app._checkbox_checked_image.get(4, 8)
        unchecked = app._checkbox_unchecked_image.get(4, 8)
        self.assertNotEqual(checked, unchecked)


if __name__ == "__main__":
    unittest.main()
