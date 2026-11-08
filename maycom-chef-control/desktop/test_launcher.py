"""Desktop process protocol checks; no remote inference is invoked."""
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
from http.cookiejar import CookieJar
import urllib.error
import urllib.request


def test_ready_handshake_authentication_and_stdin_shutdown(tmp_path):
    launcher = Path(__file__).with_name("launcher.py")
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path)
    env["LOCALAPPDATA"] = str(tmp_path)
    # Keep an unlistened port reserved so this check cannot contact a real
    # ComfyUI or execute inference, even if one is already running locally.
    unavailable_motor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unavailable_motor.bind(("127.0.0.1", 0))
    motor_port = unavailable_motor.getsockname()[1]
    motor_url = f"http://127.0.0.1:{motor_port}"
    env["MAYCOM_COMFY_URL"] = motor_url
    env["FAL_KEY"] = "test-only-old-paid-key-must-not-enable-generation"
    process = subprocess.Popen(
        [sys.executable, str(launcher), "--server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env,
    )
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
    try:
        line = ready.get(timeout=90)
        message = json.loads(line)
        assert message["pid"] == process.pid
        assert message["url"].startswith("http://127.0.0.1:")
        assert "/desktop/start/" in message["url"]
        base = message["url"].split("/desktop/start/", 1)[0]
        client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )
        try:
            client.open(base + "/api/assets", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Unprotected desktop API")
        with client.open(message["url"], timeout=10) as response:
            assert b"MAYCOM CHEF CONTROL" in response.read()
        with client.open(base + "/api/assets", timeout=10) as response:
            assert json.load(response) == []
        with client.open(base + "/api/capabilities", timeout=10) as response:
            capabilities = json.load(response)
            assert capabilities["provider"]["id"] == "comfy-local"
            assert capabilities["provider"]["configured"] is False
        with client.open(base + "/api/local/settings", timeout=10) as response:
            settings = json.load(response)
            assert settings["url"] == motor_url
            assert settings["ready"] is False and settings["issues"]
        req = urllib.request.Request(base + "/api/local/settings", method="PUT",
                                     data=json.dumps({"url": f"http://localhost:{motor_port}"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with client.open(req, timeout=10) as response:
            saved = json.load(response)
            assert saved["url"] == motor_url and saved["ready"] is False
        stored = tmp_path / "MAYCOMCHEFCONTROL" / "local-engine.json"
        assert json.loads(stored.read_text(encoding="utf-8")) == {"url": motor_url}
        for method in ("GET", "PUT", "DELETE"):
            req = urllib.request.Request(base + "/api/desktop/settings", method=method,
                                         data=b'{"fal_key":"unused-test-key"}' if method == "PUT" else None,
                                         headers={"Content-Type": "application/json"})
            try:
                client.open(req, timeout=10)
            except urllib.error.HTTPError as exc:
                assert exc.code == 410
            else:
                raise AssertionError("Paid settings endpoint is still available")
        process.stdin.close()
        assert process.wait(timeout=20) == 0
        assert process.stdout.read() == "", "Only the ready JSON may be written to stdout"
        logs = process.stderr.read()
        assert message["url"].split("/desktop/start/", 1)[1] not in logs
    finally:
        unavailable_motor.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
