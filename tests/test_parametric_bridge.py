from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from parametric_adjoint.bridge import prepare_case_config


class BridgeTests(unittest.TestCase):
    def test_prepare_existing_case(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            case, binary = root / "case", root / "bin"
            case.mkdir(); binary.mkdir()
            for name in ("mesh.su2", "run.cfg", "restart_flow.dat"):
                (case / name).write_text("test\n", encoding="utf-8")
            (case / "last_result.json").write_text(json.dumps({
                "metrics": {"升力系数 CL": "0.31", "阻力系数 CD": "0.012"}
            }), encoding="utf-8")
            target = root / "study.json"
            prepare_case_config(
                case_dir=case, su2_bin=binary, output_config=target,
                runtime_bin=None, mode="relay", objective_mode="fixed_aoa",
                target_cl=None, dcl_dalpha=None, dcd_dcl=None,
            )
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["parameterization"]["mode"], "relay")
            self.assertEqual(payload["case"]["initial_cl"], 0.31)
            self.assertEqual(payload["case"]["initial_cd"], 0.012)
            suffix = ".exe" if os.name == "nt" else ""
            self.assertTrue(payload["executables"]["cfd"].endswith(f"SU2_CFD{suffix}"))

    def test_converged_api_result_can_seed_case(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            case, binary = root / "case", root / "bin"
            case.mkdir(); binary.mkdir()
            for name in ("mesh.su2", "run.cfg", "restart_flow.dat"):
                (case / name).write_text("test\n", encoding="utf-8")
            (case / "api_result.json").write_text(json.dumps({
                "mode": "solve", "ok": True, "residual_target_met": True,
                "last_values": {"CL": 0.42, "CD": 0.018},
            }), encoding="utf-8")
            target = root / "study.json"
            prepare_case_config(
                case_dir=case, su2_bin=binary, output_config=target,
                runtime_bin=None, mode="bce", objective_mode="fixed_aoa",
                target_cl=None, dcl_dalpha=None, dcd_dcl=None,
            )
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["case"]["initial_cl"], 0.42)
            self.assertEqual(payload["case"]["initial_cd"], 0.018)


if __name__ == "__main__":
    unittest.main()
