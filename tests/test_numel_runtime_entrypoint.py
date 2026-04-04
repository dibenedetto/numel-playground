from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"


class NumelRuntimeEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = PROJECT_ROOT / "storage" / "_test_runs" / f"numel_runtime_{uuid.uuid4().hex[:8]}"
        self._workspace = self._tmpdir / "workspace"
        self._artifacts = self._tmpdir / "artifacts"
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._artifacts.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run_entrypoint(self, asset_path: str, inputs: dict[str, object] | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(APP_DIR),
                str(PROJECT_ROOT),
                existing_pythonpath,
            ]
        ).strip(os.pathsep)
        env.update(
            {
                "NUMEL_CONTRACT_VERSION": "1",
                "NUMEL_EXECUTION_ID": "exec_test",
                "NUMEL_USER_ID": "user_1",
                "NUMEL_SPACE_ID": "space_1",
                "NUMEL_ASSET_PATH": asset_path,
                "NUMEL_ASSET_KIND": "workflow",
                "NUMEL_REF": "main",
                "NUMEL_INPUTS_JSON": json.dumps(inputs or {}),
                "NUMEL_WORKSPACE_DIR": str(self._workspace),
                "NUMEL_ARTIFACTS_DIR": str(self._artifacts),
                "NUMEL_OUTPUTS_PATH": str(self._artifacts / "outputs.json"),
                "NUMEL_ERROR_PATH": str(self._artifacts / "error.txt"),
                "NUMEL_STATUS_PATH": str(self._artifacts / "status.json"),
            }
        )
        return subprocess.run(
            [sys.executable, "-m", "runtime.numel_runtime.entrypoint"],
            cwd=str(PROJECT_ROOT),
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )

    def test_entrypoint_writes_outputs_and_status_for_valid_workflow(self) -> None:
        (self._workspace / "workflow.json").write_text(
            json.dumps(
                {
                    "type": "workflow",
                    "options": {"name": "Runtime Workflow"},
                    "nodes": [
                        {"type": "start_flow", "extra": {"name": "Start"}},
                        {"type": "end_flow", "extra": {"name": "End"}},
                    ],
                    "edges": [{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"}],
                }
            ),
            encoding="utf-8",
        )

        result = self._run_entrypoint("workflow.json", inputs={"foo": 1, "bar": True})
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        outputs = json.loads((self._artifacts / "outputs.json").read_text(encoding="utf-8"))
        status = json.loads((self._artifacts / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(outputs["workflow"]["name"], "Runtime Workflow")
        self.assertEqual(outputs["workflow"]["node_count"], 2)
        self.assertEqual(outputs["runtime"]["input_keys"], ["bar", "foo"])
        self.assertGreater(outputs["runtime"]["event_count"], 0)
        self.assertEqual(outputs["execution"]["status"], "completed")
        self.assertTrue(outputs["execution"]["engine_execution_id"])
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["engine_execution_id"], outputs["execution"]["engine_execution_id"])

    def test_entrypoint_writes_failure_contract_for_missing_asset(self) -> None:
        result = self._run_entrypoint("missing.json")
        self.assertNotEqual(result.returncode, 0)

        status = json.loads((self._artifacts / "status.json").read_text(encoding="utf-8"))
        error_text = (self._artifacts / "error.txt").read_text(encoding="utf-8")
        self.assertEqual(status["state"], "failed")
        self.assertIn("Asset file not found", error_text)


if __name__ == "__main__":
    unittest.main()
