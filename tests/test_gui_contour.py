from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from core_modules.field_visualizer import prepare_contour_data
from tests.test_field_visualizer import _build_appended_vtu
from tests.tmp_workspace import workspace_temp_dir


class ContourDataTests(unittest.TestCase):
    def test_pressure_is_reported_as_gauge_pressure(self) -> None:
        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            prepared = prepare_contour_data(vtu, "Pressure")
        # 合成数据：远场节点（离形心最远的 2%）压力为 101000 与 100500。
        # 表压 = p - p_inf，p_inf 取远场均值 100750。
        self.assertEqual(prepared["label"], "p - p_inf [Pa]")
        self.assertLess(prepared["vmin"], 0.0)
        self.assertGreater(prepared["vmax"], 0.0)

    def test_color_range_uses_percentiles_not_extremes(self) -> None:
        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            prepared = prepare_contour_data(vtu, "Mach")
        # Mach 数据含一个 0.9 的离群点；色标应取分位范围而非极值。
        self.assertLess(prepared["vmax"], 0.9)


class GuiContourPathTests(unittest.TestCase):
    """headless 验证 GUI 云图页的完整事件路径（worker -> 主线程绘制）。"""

    def _make_app(self, directory) -> "AutoFoilStudio":
        from gui_app import AutoFoilStudio

        app = AutoFoilStudio(smoke_test=True)
        app.withdraw()
        app.update_idletasks()
        app.active_case_dir = Path(directory)
        return app

    def test_contour_worker_draws_interactive_canvas(self) -> None:
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            np.savetxt(
                directory / "processed_airfoil.dat",
                np.array([[1.0, 0.0], [0.5, 0.05], [0.0, 0.0], [0.5, -0.05]]),
                fmt="%.6f",
            )
            app = AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.update_idletasks()
                app.active_case_dir = Path(directory)
                app.contour_field_var.set("Mach")
                app._contour_worker("Mach", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                self.assertEqual(app.contour_field_shown, "Mach")
                self.assertIsNotNone(app.contour_data)
                self.assertIn("values", app.contour_data)
            finally:
                app.destroy()

    def test_redrawing_contour_replaces_colorbar_without_crash(self) -> None:
        """连续绘制两个场必须能正常替换 colorbar（回归：旧 colorbar.remove 崩溃）。"""
        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            app = self._make_app(directory)
            try:
                for field in ("Mach", "Pressure", "Mach"):
                    app.contour_field_var.set(field)
                    app._contour_worker(field, app.active_case_dir)
                    app.update()
                    app._drain_events()
                    app.update_idletasks()
                    self.assertEqual(app.contour_field_shown, field)
                    self.assertTrue(
                        (app.active_case_dir / f"Contour_{field}.png").is_file()
                    )
            finally:
                app.destroy()

    def test_auto_and_custom_color_ranges(self) -> None:
        with workspace_temp_dir() as directory:
            _build_appended_vtu(directory / "flow.vtu")
            app = self._make_app(directory)
            try:
                app._contour_worker("Mach", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                auto_min = app.contour_data["auto_vmin"]
                auto_max = app.contour_data["auto_vmax"]
                self.assertLess(auto_min, auto_max)
                self.assertEqual(str(app.contour_vmin_entry.cget("state")), "disabled")

                app.contour_range_mode_var.set("自定义")
                app._toggle_contour_range_controls()
                app.contour_vmin_var.set("0.12")
                app.contour_vmax_var.set("0.34")
                self.assertEqual(app._selected_contour_limits(), (0.12, 0.34))
                app._apply_contour_range()
                self.assertEqual(app.contour_data["vmin"], 0.12)
                self.assertEqual(app.contour_data["vmax"], 0.34)

                app.contour_range_mode_var.set("自动")
                app._on_contour_range_mode_changed()
                self.assertEqual(app.contour_data["vmin"], auto_min)
                self.assertEqual(app.contour_data["vmax"], auto_max)

                app.contour_range_mode_var.set("自定义")
                app._toggle_contour_range_controls()
                app.contour_vmin_var.set("0.5")
                app.contour_vmax_var.set("0.1")
                with self.assertRaises(ValueError):
                    app._selected_contour_limits()
            finally:
                app.destroy()

    def test_contour_field_combo_filters_unavailable_fields(self) -> None:
        """下拉框应只列出当前 flow.vtu 中真实存在的变量。"""
        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            app = self._make_app(directory)
            try:
                app._refresh_contour_fields(app.active_case_dir)
                values = list(app.contour_field_combo.cget("values"))
                self.assertIn("Mach", values)
                self.assertNotIn("Eddy_Viscosity", values)
                self.assertNotIn("Nu_Tilde", values)
                self.assertNotIn("Y_Plus", values)
            finally:
                app.destroy()

    def test_constant_field_gives_friendly_error_and_keeps_previous_plot(self) -> None:
        """恒值场（如层流算例的 Y_Plus）应给出明确提示且不破坏已显示的云图。"""
        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            app = self._make_app(directory)
            try:
                app.contour_field_var.set("Mach")
                app._contour_worker("Mach", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                # 合成文件没有 Y_Plus：应走“字段缺失”的友好错误路径，
                # 已显示的 Mach 云图保持不动。
                app._contour_worker("Y_Plus", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                self.assertEqual(app.contour_field_shown, "Mach")
            finally:
                app.destroy()

    def test_scroll_wheel_zooms_around_cursor(self) -> None:
        """滚轮缩放应以光标位置为中心。"""
        from types import SimpleNamespace

        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            app = self._make_app(directory)
            try:
                app.contour_field_var.set("Mach")
                app._contour_worker("Mach", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                xlim_before = app.contour_ax.get_xlim()
                width_before = xlim_before[1] - xlim_before[0]
                # 光标放在 (0.5, 0.5)，向上滚动放大。
                app._on_contour_scroll(
                    SimpleNamespace(
                        inaxes=app.contour_ax, xdata=0.5, ydata=0.5, button="up"
                    )
                )
                xlim_after = app.contour_ax.get_xlim()
                width_after = xlim_after[1] - xlim_after[0]
                self.assertLess(width_after, width_before)
                # 光标相对位置不变：中点仍在 0.5。
                self.assertAlmostEqual(
                    (xlim_after[0] + xlim_after[1]) / 2.0, 0.5, places=9
                )
                # 向下滚动应放大视图。
                app._on_contour_scroll(
                    SimpleNamespace(
                        inaxes=app.contour_ax, xdata=0.5, ydata=0.5, button="down"
                    )
                )
                width_back = app.contour_ax.get_xlim()[1] - app.contour_ax.get_xlim()[0]
                self.assertGreater(width_back, width_after)
            finally:
                app.destroy()

    def test_drag_pans_the_view(self) -> None:
        """左键拖动应按鼠标位移平移视图。"""
        from types import SimpleNamespace

        with workspace_temp_dir() as directory:
            vtu = directory / "flow.vtu"
            _build_appended_vtu(vtu)
            app = self._make_app(directory)
            try:
                app.contour_field_var.set("Mach")
                app._contour_worker("Mach", app.active_case_dir)
                app.update()
                app._drain_events()
                app.update_idletasks()
                xlim0 = app.contour_ax.get_xlim()
                ylim0 = app.contour_ax.get_ylim()
                app._on_contour_press(
                    SimpleNamespace(
                        inaxes=app.contour_ax, xdata=0.5, ydata=0.5, button=1
                    )
                )
                app._on_contour_motion(
                    SimpleNamespace(
                        inaxes=app.contour_ax, xdata=0.6, ydata=0.4
                    )
                )
                app._on_contour_release(SimpleNamespace())
                xlim1 = app.contour_ax.get_xlim()
                ylim1 = app.contour_ax.get_ylim()
                # 鼠标向右下拖动 (0.5,0.5)->(0.6,0.4)：内容随鼠标移动，
                # 视图窗口向左上平移（x 下限减小、y 下限增大）。
                self.assertLess(xlim1[0], xlim0[0])
                self.assertGreater(ylim1[0], ylim0[0])
                self.assertAlmostEqual(
                    xlim1[1] - xlim1[0], xlim0[1] - xlim0[0], places=9
                )
                self.assertAlmostEqual(
                    ylim1[1] - ylim1[0], ylim0[1] - ylim0[0], places=9
                )
            finally:
                app.destroy()


class MeshDefaultsButtonTests(unittest.TestCase):
    """全结构网格「默认参数」按钮的取值逻辑。"""

    def test_restore_structured_mesh_defaults(self) -> None:
        from gui_app import AutoFoilStudio

        app = AutoFoilStudio(smoke_test=True)
        try:
            app.withdraw()
            app.update_idletasks()
            app.surface_point_count_var.set("50")
            app._restore_mesh_defaults()
            self.assertEqual(app.surface_point_count_var.get(), "100")
            self.assertEqual(app.global_refinement_var.get(), "1.0")
            self.assertEqual(
                app.control_point_sizes_var.get(),
                "0.0015, 0.0015, 0.0015",
            )
            self.assertEqual(app.wake_refinement_var.get(), "2.0")
            self.assertEqual(app.y_plus_var.get(), "1.0")
            self.assertEqual(app.farfield_var.get(), "20")
            self.assertEqual(app.domain_scale_var.get(), "1.0")
            self.assertEqual(app.growth_ratio_var.get(), "1.15")
            self.assertEqual(app.bl_thickness_var.get(), "0.08")
            self.assertEqual(app.farfield_size_var.get(), "0.4")
        finally:
            app.destroy()


class ResultsMonitorTests(unittest.TestCase):
    def test_log_and_convergence_share_one_monitor_page_with_stage_progress(self) -> None:
        from gui_app import AutoFoilStudio

        app = AutoFoilStudio(smoke_test=True)
        try:
            app.withdraw()
            app.update_idletasks()
            tab_texts = [
                app.result_notebook.tab(tab_id, "text")
                for tab_id in app.result_notebook.tabs()
            ]
            self.assertIn("实时监控", tab_texts)
            self.assertNotIn("实时日志", tab_texts)
            self.assertNotIn("实时收敛", tab_texts)
            self.assertTrue(str(app.log_text).startswith(str(app.monitor_tab)))
            self.assertTrue(str(app.live_canvas.get_tk_widget()).startswith(str(app.monitor_tab)))

            app.events.put(("stage_progress", (50, "网格质量检查")))
            app._drain_events()
            self.assertEqual(float(app.progress["value"]), 50.0)
            self.assertIn("网格质量检查", app.progress_text_var.get())
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
