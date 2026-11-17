from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core_modules.process_control import ProcessController
from core_modules.su2_driver import generate_config
from tests.tmp_workspace import workspace_temp_dir


ROOT = Path(__file__).resolve().parents[1]


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15


class ProcessControllerTests(unittest.TestCase):
    def test_pending_pause_is_applied_when_process_attaches(self) -> None:
        controller = ProcessController()
        process = _FakeProcess()
        self.assertFalse(controller.pause())
        with patch("core_modules.process_control._suspend_process") as suspend:
            controller.attach(process)  # type: ignore[arg-type]
        suspend.assert_called_once_with(process)
        self.assertTrue(controller.paused)

    def test_resume_and_terminate_control_the_attached_process(self) -> None:
        controller = ProcessController()
        process = _FakeProcess()
        controller.attach(process)  # type: ignore[arg-type]
        with (
            patch("core_modules.process_control._suspend_process") as suspend,
            patch("core_modules.process_control._resume_process") as resume,
        ):
            self.assertTrue(controller.pause())
            self.assertTrue(controller.resume())
            self.assertTrue(controller.pause())
            self.assertTrue(controller.terminate())
        self.assertEqual(suspend.call_count, 2)
        self.assertEqual(resume.call_count, 2)
        self.assertTrue(process.terminated)
        self.assertTrue(controller.termination_requested)


class Su2DriverTests(unittest.TestCase):
    def test_replaces_all_template_values(self) -> None:
        with workspace_temp_dir() as temporary_directory:
            config = generate_config(
                {"MACH": 0.7, "AOA": 3.5, "ITERATIONS": 25},
                ROOT / "config_template.cfg",
                temporary_directory,
            )
            text = config.read_text(encoding="utf-8")
            self.assertIn("MACH_NUMBER= 0.7", text)
            self.assertIn("AOA= 3.5", text)
            self.assertIn("MARKER_FAR= ( farfield_inlet, farfield_outlet )", text)
            self.assertIn("MESH_QUALITY", text)
            self.assertIn("NUM_METHOD_GRAD_RECON= LEAST_SQUARES", text)
            self.assertNotIn("{{", text)

    def test_centered_scheme_disables_separate_reconstruction_gradient(self) -> None:
        with workspace_temp_dir() as directory:
            config = generate_config({"FLOW_SCHEME": "JST", "MUSCL_FLOW": "NO"},
                                     ROOT / "config_template.cfg", directory)
            self.assertIn("NUM_METHOD_GRAD_RECON= NONE", config.read_text(encoding="utf-8"))

    def test_explicit_legacy_reconstruction_remains_available(self) -> None:
        with workspace_temp_dir() as directory:
            config = generate_config({"RECONSTRUCTION_GRADIENT": "WEIGHTED_LEAST_SQUARES"},
                                     ROOT / "config_template.cfg", directory)
            self.assertIn("NUM_METHOD_GRAD_RECON= WEIGHTED_LEAST_SQUARES",
                          config.read_text(encoding="utf-8"))

    def test_missing_template_raises_file_not_found(self) -> None:
        with workspace_temp_dir() as temporary_directory:
            with self.assertRaises(FileNotFoundError):
                generate_config({}, ROOT / "no_such_template.cfg", temporary_directory)


if __name__ == "__main__":
    unittest.main()
