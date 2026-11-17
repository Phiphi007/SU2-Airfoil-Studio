from __future__ import annotations

import json
import unittest

from PIL import Image

from core_modules.post_analyzer import REPORT_PANELS
from tests.tmp_workspace import workspace_temp_dir


class LastResultTests(unittest.TestCase):
    def test_report_page_loads_four_images_into_separate_tabs(self) -> None:
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            report_directory = directory / "Aerodynamic_Report"
            report_directory.mkdir()
            for index, (_, _, filename) in enumerate(REPORT_PANELS):
                Image.new("RGB", (320, 180), (220 - index * 20, 230, 240)).save(
                    report_directory / filename
                )
            app = AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.update_idletasks()
                app._load_report(report_directory / REPORT_PANELS[0][2])
                app.update_idletasks()
                self.assertEqual(len(app.report_notebook.tabs()), 4)
                self.assertEqual(len(app.report_sources), 4)
            finally:
                app.destroy()

    def test_streamed_iteration_is_enough_for_partial_summary(self) -> None:
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            summary = AutoFoilStudio._read_result_summary(
                directory,
                fallback_point=(37, -5.25, 0.6123, 0.0184),
                residual_target=-8.0,
            )
        values = dict(summary)
        self.assertEqual(values["最后有效迭代步"], "37")
        self.assertEqual(values["升力系数 CL"], "0.6123")
        self.assertIn("未达到目标", values["收敛状态"])

    def test_last_result_json_records_incomplete_state(self) -> None:
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            path = AutoFoilStudio._write_last_result(
                directory,
                "incomplete",
                [("结果状态", "用户终止"), ("升力系数 CL", "0.5")],
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "incomplete")
        self.assertEqual(payload["metrics"]["升力系数 CL"], "0.5")


if __name__ == "__main__":
    unittest.main()
