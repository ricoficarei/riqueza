"""Bundled desktop backend for MAYCOM CHEF CONTROL.

Electron starts ``MaycomBackend.exe --server`` with stdin/stdout pipes. A single
JSON line on stdout announces the authenticated bootstrap URL; closing stdin
requests a graceful shutdown. All application logs go to stderr/private storage.
No Python, Node.js or FFmpeg installation is needed on the target machine.
"""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
import webbrowser


APP_NAME = "MAYCOM CHEF CONTROL"


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def user_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "MAYCOMCHEFCONTROL"


def prepare_runtime(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        data_dir.chmod(0o700)
    root = bundle_root()
    bins = root / "bin"
    os.environ["PATH"] = str(bins) + os.pathsep + os.environ.get("PATH", "")
    os.environ["MAYCOM_DATA_DIR"] = str(data_dir)
    os.environ["MAYCOM_DESKTOP"] = "1"
    os.environ["MAYCOM_FRONTEND_DIR"] = str(root / "frontend" / "dist")
    # Source runs use the checked-out backend; frozen runs contain app modules.
    backend = root / "backend"
    if backend.is_dir():
        sys.path.insert(0, str(backend))
    handlers = [logging.FileHandler(data_dir / "desktop.log", encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers, force=True)


def local_opener(cookie_jar: CookieJar | None = None):
    handlers = [urllib.request.ProxyHandler({})]
    if cookie_jar is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(cookie_jar))
    return urllib.request.build_opener(*handlers)


class DesktopServer:
    def __init__(self, data_dir: Path):
        prepare_runtime(data_dir)
        from app.config import Settings
        from app.main import create_app
        import uvicorn

        self.nonce = secrets.token_urlsafe(32)
        self.config = Settings(
            data_dir=data_dir,
            fal_key="",  # create_app loads the protected desktop settings file.
            access_token=secrets.token_urlsafe(48),
            review_token=secrets.token_urlsafe(48),
            desktop_mode=True,
            desktop_config_path=data_dir / "settings.dat",
        )
        self.app = create_app(self.config)
        self.app.state.desktop_nonce = self.nonce
        self.app.state.desktop_shutdown = self.request_shutdown
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.url = f"{self.base_url}/desktop/start/{self.nonce}"
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=self.port,
            log_config=None, access_log=False, log_level="warning",
            timeout_graceful_shutdown=5, ws="none", loop="asyncio", http="h11",
        )
        self.server = uvicorn.Server(config)
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._serve, name="maycom-local-api", daemon=True)

    def _serve(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as exc:
            self.error = exc
            logging.exception("Falha ao iniciar o servidor local.")

    def start(self):
        self.thread.start()
        opener = local_opener()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.error or not self.thread.is_alive():
                raise RuntimeError("Não foi possível iniciar o servidor local. Consulte desktop.log.")
            try:
                with opener.open(self.base_url + "/api/health", timeout=1) as response:
                    health = json.load(response)
                if health.get("status") == "ok" and health.get("app_name") == APP_NAME:
                    return
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(0.1)
        raise RuntimeError("O aplicativo demorou demais para iniciar. Consulte desktop.log.")

    def request_shutdown(self):
        self.server.should_exit = True

    def stop(self):
        self.request_shutdown()
        self.thread.join(timeout=15)
        self.socket.close()
        if self.thread.is_alive():
            logging.error("O servidor local não encerrou no tempo esperado.")

    def wait_for_parent(self):
        """Electron owns stdin; EOF means its window/process was closed."""
        def watch_stdin():
            try:
                if sys.stdin is not None:
                    sys.stdin.buffer.read()
            except (OSError, AttributeError):
                pass
            self.request_shutdown()

        threading.Thread(target=watch_stdin, name="maycom-parent-lifetime", daemon=True).start()
        while self.thread.is_alive() and not self.server.should_exit:
            time.sleep(0.2)


def _multipart(role: str, filename: str, content_type: str, data: bytes):
    boundary = "MaycomDesktopTest" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"role\"\r\n\r\n{role}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def self_test(destination: Path) -> int:
    """Exercise the packaged backend and media tools without model inference."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Existing evidence must not be silently overwritten.
    with destination.open("x", encoding="utf-8"):
        pass
    report = {"app_name": APP_NAME, "passed": False, "frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform, "python": sys.version, "checks": [], "limitations": []}
    server = None
    test_root = Path(tempfile.mkdtemp(prefix="maycom-desktop-selftest-", dir=destination.parent))
    # Reserve a non-listening loopback port throughout validation. Even when a
    # real ComfyUI is already running, this disposable profile must never submit
    # a generation or borrow the user's models/session.
    unavailable_motor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unavailable_motor.bind(("127.0.0.1", 0))
    motor_port = unavailable_motor.getsockname()[1]
    motor_url = f"http://127.0.0.1:{motor_port}"
    previous_motor_url = os.environ.get("MAYCOM_COMFY_URL")
    os.environ["MAYCOM_COMFY_URL"] = motor_url
    try:
        server = DesktopServer(test_root / "data")
        server.start()
        jar = CookieJar()
        client = local_opener(jar)

        def check(name, condition=True):
            if not condition:
                raise AssertionError(name)
            report["checks"].append({"name": name, "passed": True})

        def request(route, method="GET", data=None, content_type="application/json"):
            if data is not None and not isinstance(data, bytes):
                data = json.dumps(data).encode()
            req = urllib.request.Request(server.base_url + route, method=method, data=data)
            if data is not None:
                req.add_header("Content-Type", content_type)
            with client.open(req, timeout=120) as response:
                body = response.read()
                return response.status, json.loads(body) if body and response.headers.get_content_type() == "application/json" else body

        try:
            request("/api/assets")
        except urllib.error.HTTPError as exc:
            check("private_api_requires_session", exc.code == 401)
        else:
            raise AssertionError("Private API unexpectedly accessible without authentication")
        with client.open(server.url, timeout=30) as response:
            html = response.read().decode("utf-8")
        check("bootstrap_cookie_and_bundled_frontend", bool(list(jar)) and APP_NAME in html)
        try:
            with client.open(server.url, timeout=30):
                pass
        except urllib.error.HTTPError as exc:
            check("bootstrap_nonce_is_single_use", exc.code == 403)
        else:
            raise AssertionError("The desktop bootstrap nonce was reusable")
        _, capabilities = request("/api/capabilities")
        check("desktop_mode_and_review_ready", capabilities.get("desktop_mode") is True and capabilities["review"]["configured"])
        check("only_free_local_engine_is_exposed", capabilities["provider"]["id"] == "comfy-local" and capabilities["provider"]["configured"] is False)
        _, initial = request("/api/local/settings")
        check("unavailable_local_engine_is_visible", initial["ready"] is False and initial["issues"] and initial["url"] == motor_url)
        _, saved = request("/api/local/settings", "PUT", {"url": f"http://localhost:{motor_port}"})
        _, configured = request("/api/local/settings")
        check("local_settings_form_saves_without_model_inference", saved["url"] == motor_url and configured["url"] == motor_url and configured["ready"] is False)
        stored_file = test_root / "data" / "local-engine.json"
        check("local_settings_file_contains_only_loopback_url", json.loads(stored_file.read_text(encoding="utf-8")) == {"url": motor_url})
        if os.name != "nt":
            check("local_settings_file_has_private_permissions", stored_file.stat().st_mode & 0o777 == 0o600)
        for method in ("GET", "PUT", "DELETE"):
            try:
                request("/api/desktop/settings", method, {"fal_key": "unused-test-only-key"} if method == "PUT" else None)
            except urllib.error.HTTPError as exc:
                check(f"paid_settings_{method.lower()}_removed", exc.code == 410)
            else:
                raise AssertionError("Paid settings endpoint was not removed")
        report["limitations"].append(
            "Nenhum modelo de IA foi executado. A geração com VACE/DirectML, a compatibilidade da RX 6600 "
            "e a qualidade visual continuam pendentes de validação no computador do usuário."
        )

        from PIL import Image, ImageDraw
        image = test_root / "self-test-character.png"
        canvas = Image.new("RGB", (320, 240), "#242038")
        ImageDraw.Draw(canvas).rectangle((90, 30, 230, 220), fill="#7860b8")
        canvas.save(image)
        video = test_root / "self-test-reference.mp4"
        result = subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=3.2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=3.2",
            "-c:v", "libx264", "-threads", "2", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        check("bundled_ffmpeg_creates_real_test_media", result.returncode == 0 and video.stat().st_size > 1000)
        assets = []
        for path, role, mime in ((image, "character", "image/png"), (video, "reference", "video/mp4")):
            body, mime_type = _multipart(role, path.name, mime, path.read_bytes())
            status, asset = request("/api/assets", "POST", body, mime_type)
            check(f"{role}_upload_and_content_validation", status == 201 and asset["review_status"] == "pending")
            if role == "reference":
                check("bundled_ffprobe_and_opencv_analysis", asset["has_audio"] and asset["analysis"]["available"])
            status, _ = request(asset["file_url"])
            check(f"{role}_preview_served_privately", status == 200)
            _, reviewed = request(f"/api/assets/{asset['id']}/review", "POST", {
                "decision": "approved", "fictional_adult_confirmed": True, "non_intimate_confirmed": True,
            })
            check(f"{role}_desktop_owner_review", reviewed["review_status"] == "approved")
            assets.append(asset)
        try:
            request("/api/jobs", "POST", {
                "character_id": assets[0]["id"], "reference_id": assets[1]["id"],
                "settings": {"duration": 3}, "rights_confirmed": True,
                "fictional_adult_confirmed": True, "non_intimate_confirmed": True,
            })
        except urllib.error.HTTPError as exc:
            check("missing_local_engine_does_not_fake_generation", exc.code == 503)
        else:
            raise AssertionError("Generation unexpectedly accepted without a local model engine")
        for asset in assets:
            status, _ = request(f"/api/assets/{asset['id']}", "DELETE")
            check(f"{asset['role']}_delete", status == 204)
        _, jobs = request("/api/jobs")
        check("no_paid_or_simulated_jobs_created", jobs == [])
        report["passed"] = True
    except BaseException as exc:
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        if server is not None:
            server.stop()
        unavailable_motor.close()
        if previous_motor_url is None:
            os.environ.pop("MAYCOM_COMFY_URL", None)
        else:
            os.environ["MAYCOM_COMFY_URL"] = previous_motor_url
        # Windows denies deletion while FileHandler still owns desktop.log.
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, logging.FileHandler):
                handler.flush()
                handler.close()
                root_logger.removeHandler(handler)
        shutil.rmtree(test_root, ignore_errors=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--server", action="store_true", help="Managed backend mode for the bundled desktop shell")
    parser.add_argument("--self-test", type=Path, metavar="REPORT_JSON", help="Run local package validation without paid inference")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.self_test)
    server = None
    try:
        server = DesktopServer(user_data_dir())
        server.start()
        if args.server:
            # This is the only stdout record: Electron parses it as the ready signal.
            if sys.stdout is None:
                raise RuntimeError("O modo servidor exige o executável console empacotado.")
            sys.stdout.write(json.dumps({"url": server.url, "pid": os.getpid()}) + "\n")
            sys.stdout.flush()
            server.wait_for_parent()
        else:
            webbrowser.open(server.url)
            while server.thread.is_alive():
                time.sleep(0.2)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.exception("Falha no aplicativo desktop.")
        if os.name == "nt" and not args.server:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "Não foi possível iniciar o aplicativo. Consulte o arquivo desktop.log na pasta de dados do MAYCOM CHEF CONTROL.", APP_NAME, 0x10)
        return 1
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
