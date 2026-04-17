from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import unittest
import uuid
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@unittest.skipUnless(PYTHON_EXE.exists(), "repo virtualenv Python is required")
@unittest.skipUnless(shutil.which("node"), "node is required for frontend starter smoke tests")
@unittest.skipUnless((WEB_DIR / "node_modules" / "playwright").exists(), "Playwright must be installed in web/node_modules")
class FrontendStarterSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"starter_browser_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._runtime_root = self._root / "runtime"
        self._platform_config = self._root / "platform_backend.json"
        self._db_path = self._root / "platform.db"
        self._spaces_root = self._root / "spaces"
        self._artifacts_root = self._root / "artifacts"
        self._port = _free_port()
        self._base_url = f"http://127.0.0.1:{self._port}"
        self._frontend_root = self._root / "web"
        self._frontend_port = _free_port()
        self._frontend_url = f"http://127.0.0.1:{self._frontend_port}"
        self._username = "starter"
        self._email = f"{self._username}@local"
        self._password = "pass1234"

        self._platform_config.write_text(
            json.dumps(
                {
                    "backend": "local",
                    "local": {
                        "database": {"url": f"sqlite:///{self._db_path.as_posix()}"},
                        "git": {"repos_root": str(self._spaces_root)},
                        "artifacts": {"root_path": str(self._artifacts_root)},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["NUMEL_DATA_ROOT"] = str(self._runtime_root)
        env["NUMEL_PLATFORM_CONFIG"] = str(self._platform_config)
        env["PYTHONUNBUFFERED"] = "1"
        self._server_env = env

        self._prepare_frontend_harness()

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._server = subprocess.Popen(
            [str(PYTHON_EXE), "app/app.py", "--port", str(self._port)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self._static_server = subprocess.Popen(
            [str(PYTHON_EXE), "-m", "http.server", str(self._frontend_port), "--bind", "127.0.0.1"],
            cwd=str(self._frontend_root),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self._wait_for_ready()
        self._seed_user_and_space()
        self._wait_for_frontend()

    def tearDown(self) -> None:
        if hasattr(self, "_server") and self._server.poll() is None:
            self._server.terminate()
            try:
                self._server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server.kill()
                self._server.wait(timeout=10)
        if hasattr(self, "_static_server") and self._static_server.poll() is None:
            self._static_server.terminate()
            try:
                self._static_server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._static_server.kill()
                self._static_server.wait(timeout=10)
        if hasattr(self, "_server") and self._server.stdout:
            try:
                self._server.stdout.close()
            except Exception:
                pass
        if hasattr(self, "_static_server") and self._static_server.stdout:
            try:
                self._static_server.stdout.close()
            except Exception:
                pass
        shutil.rmtree(self._root, ignore_errors=True)

    def _server_output(self) -> str:
        if not getattr(self, "_server", None) or not self._server.stdout:
            return ""
        if self._server.poll() is None:
            return ""
        try:
            return self._server.stdout.read() or ""
        except Exception:
            return ""

    def _static_server_output(self) -> str:
        if not getattr(self, "_static_server", None) or not self._static_server.stdout:
            return ""
        if self._static_server.poll() is None:
            return ""
        try:
            return self._static_server.stdout.read() or ""
        except Exception:
            return ""

    def _prepare_frontend_harness(self) -> None:
        shutil.copytree(
            WEB_DIR,
            self._frontend_root,
            ignore=shutil.ignore_patterns("node_modules", "src"),
        )
        index_path = self._frontend_root / "index.html"
        html = index_path.read_text(encoding="utf-8")
        original = '<input type="hidden" id="serverUrl" autocomplete="off">'
        replacement = f'<input type="hidden" id="serverUrl" autocomplete="off" value="{self._base_url}">'
        if original not in html:
            self.fail("Could not find serverUrl input in frontend index.html")
        index_path.write_text(html.replace(original, replacement, 1), encoding="utf-8")

        workflow_ui_path = self._frontend_root / "numel-workflow-ui.js"
        workflow_ui = workflow_ui_path.read_text(encoding="utf-8")
        old_server_url_line = "$('serverUrl').value = window.location.origin;"
        new_server_url_line = "$('serverUrl').value = $('serverUrl').value || window.location.origin;"
        if old_server_url_line not in workflow_ui:
            self.fail("Could not patch frontend harness serverUrl bootstrap")
        workflow_ui_path.write_text(
            workflow_ui.replace(old_server_url_line, new_server_url_line, 1),
            encoding="utf-8",
        )

    def _wait_for_ready(self) -> None:
        deadline = time.time() + 60
        last_error = None
        while time.time() < deadline:
            if self._server.poll() is not None:
                output = self._server_output()
                self.fail(f"Numel server exited early with code {self._server.returncode}\n{output}")
            try:
                response = httpx.get(f"{self._base_url}/health/ready", timeout=2.0)
                if response.status_code == 200:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.5)
        output = self._server_output()
        self.fail(f"Numel server did not become ready at {self._base_url}: {last_error}\n{output}")

    def _wait_for_frontend(self) -> None:
        deadline = time.time() + 30
        last_error = None
        while time.time() < deadline:
            if self._static_server.poll() is not None:
                output = self._static_server_output()
                self.fail(f"Frontend static server exited early with code {self._static_server.returncode}\n{output}")
            try:
                response = httpx.get(f"{self._frontend_url}/index.html", timeout=2.0)
                if response.status_code == 200:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.3)
        output = self._static_server_output()
        self.fail(f"Frontend static server did not become ready at {self._frontend_url}: {last_error}\n{output}")

    def _seed_user_and_space(self) -> None:
        with httpx.Client(base_url=self._base_url, timeout=10.0) as client:
            register = client.post(
                "/auth/register",
                json={
                    "username": self._username,
                    "email": self._email,
                    "password": self._password,
                },
            )
            if register.status_code != 200:
                self.fail(f"Failed to seed smoke user: {register.status_code} {register.text}")
            token = register.json().get("token")
            if not token:
                self.fail("Smoke user registration did not return a token")
            create = client.post(
                "/spaces/create",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": "Starter Space",
                    "description": "Starter browser smoke space",
                    "visibility": "private",
                },
            )
            if create.status_code != 200:
                self.fail(f"Failed to seed starter space: {create.status_code} {create.text}")

    def test_browser_starter_modal_and_hello_flow(self) -> None:
        env = os.environ.copy()
        env["NUMEL_TEST_BASE_URL"] = self._frontend_url
        env["NUMEL_TEST_USERNAME"] = self._username
        env["NUMEL_TEST_EMAIL"] = self._email
        env["NUMEL_TEST_PASSWORD"] = self._password
        env["NUMEL_TEST_AUTH_MODE"] = "login"

        def _maybe_skip_for_browser_environment(stderr_text: str) -> None:
            text = stderr_text or ""
            if "spawn EPERM" in text:
                self.skipTest("Playwright browser launch is blocked on this machine (spawn EPERM)")

        try:
            result = subprocess.run(
                ["node", "tests/starter-smoke.mjs", self._frontend_url],
                cwd=str(WEB_DIR),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            server_output = self._server_output()
            static_output = self._static_server_output()
            _maybe_skip_for_browser_environment(exc.stderr or "")
            self.fail(
                "Starter browser smoke timed out\n"
                f"stdout:\n{exc.stdout or ''}\n"
                f"stderr:\n{exc.stderr or ''}\n"
                f"server:\n{server_output}\n"
                f"static:\n{static_output}"
            )
        _maybe_skip_for_browser_environment(result.stderr)
        if result.returncode != 0:
            server_output = self._server_output()
            static_output = self._static_server_output()
            self.fail(
                "Starter browser smoke failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}\n"
                f"server:\n{server_output}\n"
                f"static:\n{static_output}"
            )


if __name__ == "__main__":
    unittest.main()



