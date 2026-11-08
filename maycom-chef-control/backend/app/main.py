import asyncio
import hmac
import json
import hashlib
import os
import re
import shutil
import uuid
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings, storage_bytes
from .database import ACTIVE, Database, now
from .media import MediaError, inspect_asset
from .quality import analyze_reference
from .schemas import CreateJob, ReviewAsset
from .worker import Worker
from .providers.comfy_local import inspect_local, local_url, MODEL_LABEL
from .process_lock import acquire_worker_lock


class LocalConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=100)

    @field_validator("url")
    @classmethod
    def clean_url(cls, value):
        return local_url(value)


def public_asset(asset):
    return {k: v for k, v in asset.items() if k not in ("path",)}


def public_job(job):
    return {k: v for k, v in job.items() if k not in ("output_path", "provider_request_id")}


def create_app(settings: Settings | None = None, provider_factory=None):
    config = settings or Settings()
    config.prepare()
    # Paid credentials from earlier releases are never loaded or used.
    local_settings_path = config.data_dir / "local-engine.json"
    if config.desktop_mode and local_settings_path.is_file():
        try:
            config.comfy_url = local_url(json.loads(local_settings_path.read_text())["url"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    local_url(config.comfy_url)
    local_cache = None
    local_cache_time = 0.0

    async def local_state(refresh=False):
        nonlocal local_cache, local_cache_time
        if refresh or local_cache is None or time.monotonic() - local_cache_time > 20:
            local_cache = await inspect_local(config)
            local_cache_time = time.monotonic()
        return local_cache
    db = Database(config.data_dir / "studio.sqlite3")
    worker = Worker(db, config, provider_factory)

    @asynccontextmanager
    async def lifespan(app):
        task = None
        lock = None
        if config.worker_enabled:
            lock = acquire_worker_lock(config.data_dir / "worker.lock")
            db.recover(local_only=True)
            task = asyncio.create_task(worker.run())
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if lock:
                lock.close()

    app = FastAPI(title="MAYCOM CHEF CONTROL", version="0.1.0", lifespan=lifespan)
    app.state.db, app.state.settings, app.state.worker = db, config, worker
    app.state.desktop_nonce = None
    upload_lock = asyncio.Lock()

    def valid_session(cookie):
        try:
            stamp, signature = (cookie or "").split(".", 1)
            age = time.time() - int(stamp)
            expected = hmac.new(config.access_token.encode(), stamp.encode(), hashlib.sha256).hexdigest()
            return 0 <= age < 8 * 3600 and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError):
            return False

    @app.middleware("http")
    async def security(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            origin = request.headers.get("origin")
            same_origin = str(request.base_url).rstrip("/")
            allowed_origins = (same_origin,) if config.desktop_mode else (*config.allowed_origins, same_origin)
            if origin and origin not in allowed_origins:
                return JSONResponse({"detail": "Origem não autorizada."}, status_code=403)
            if config.desktop_mode and request.url.hostname not in ("127.0.0.1", "localhost", "testserver"):
                return JSONResponse({"detail": "Host local não autorizado."}, status_code=403)
            if config.access_token and path not in ("/api/health", "/api/capabilities", "/api/session"):
                expected = "Bearer " + config.access_token
                if not hmac.compare_digest(request.headers.get("authorization", "").encode(), expected.encode()) and not valid_session(request.cookies.get("maycom_session")):
                    return JSONResponse({"detail": "Informe o token de acesso do estúdio."}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def get_asset(ident):
        value = db.asset(ident)
        if not value:
            raise HTTPException(404, "Arquivo não encontrado.")
        return value

    def get_job(ident):
        value = db.job(ident)
        if not value:
            raise HTTPException(404, "Geração não encontrada.")
        return value

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "app_name": "MAYCOM CHEF CONTROL"}

    def set_session_cookie(response, request):
        stamp = str(int(time.time()))
        signature = hmac.new(config.access_token.encode(), stamp.encode(), hashlib.sha256).hexdigest()
        response.set_cookie("maycom_session", f"{stamp}.{signature}", max_age=8 * 3600, httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/api")

    @app.get("/desktop/start/{nonce}", include_in_schema=False)
    async def desktop_start(nonce: str, request: Request):
        expected = app.state.desktop_nonce
        if not config.desktop_mode or not expected or not hmac.compare_digest(nonce.encode(), expected.encode()):
            raise HTTPException(403, "A abertura do aplicativo expirou. Feche e abra novamente.")
        if request.url.hostname not in ("127.0.0.1", "localhost", "testserver"):
            raise HTTPException(403, "Host local não autorizado.")
        app.state.desktop_nonce = None
        result = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
        set_session_cookie(result, request)
        return result

    @app.post("/api/session")
    async def login(request: Request):
        if config.access_token and not hmac.compare_digest(request.headers.get("authorization", "").encode(), ("Bearer " + config.access_token).encode()):
            raise HTTPException(401, "Token de acesso inválido.")
        result = JSONResponse({"authenticated": True})
        if config.access_token:
            set_session_cookie(result, request)
        return result

    @app.post("/api/session/logout")
    async def logout():
        result = JSONResponse({"authenticated": False})
        result.delete_cookie("maycom_session", path="/api")
        return result

    @app.get("/api/capabilities")
    async def capabilities():
        state = await local_state()
        return {
            "app_name": "MAYCOM CHEF CONTROL",
            "desktop_mode": config.desktop_mode,
            "provider": {"id": "comfy-local", "label": "IA local — sem créditos", "configured": state["ready"], "model": MODEL_LABEL, "reason": " ".join(state["issues"]) or None},
            "local": {k: v for k, v in state.items() if k != "url"},
            "review": {"configured": bool(config.review_token), "required": True, "desktop_owner": config.desktop_mode},
            "limits": {"image_mb": 20, "video_mb": 150, "min_duration": 3, "max_duration_video": 5, "max_duration_image": 5},
            "features": {"character_video_mode": "first_frame", "pose_estimation": state["ready"], "identity_verification": False, "motion_intensity": False, "face_preservation_control": False},
            "auth_required": bool(config.access_token),
            "quality_notice": "RX 6600/DirectML experimental: geração e qualidade precisam de validação no seu computador. Não há garantia de identidade, anatomia ou movimentos perfeitos.",
        }

    @app.get("/api/local/settings")
    async def local_settings():
        if not config.desktop_mode:
            raise HTTPException(404, "Configuração disponível no aplicativo local. No servidor, use MAYCOM_COMFY_URL.")
        return await local_state(refresh=True)

    @app.put("/api/local/settings")
    async def local_settings_save(body: LocalConnection):
        if not config.desktop_mode:
            raise HTTPException(404, "Configuração disponível no aplicativo local. No servidor, use MAYCOM_COMFY_URL.")
        if any(j["status"] in ACTIVE for j in db.jobs()):
            raise HTTPException(409, "Aguarde ou cancele as gerações antes de alterar o motor local.")
        temporary = local_settings_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps({"url": body.url}), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, local_settings_path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise HTTPException(500, "Não foi possível salvar a configuração local.") from None
        config.comfy_url = body.url
        return await local_state(refresh=True)

    @app.api_route("/api/desktop/settings", methods=["GET", "PUT", "DELETE"])
    async def removed_paid_connection():
        raise HTTPException(410, "A conexão paga foi removida. Configure o motor local em /api/local/settings.")

    @app.get("/api/assets")
    async def assets():
        return [public_asset(a) for a in db.assets()]

    @app.post("/api/assets", status_code=201)
    async def upload_asset(file: UploadFile = File(...), role: str = Form(...)):
        if role not in ("character", "reference"):
            raise HTTPException(422, "O papel do arquivo deve ser character ou reference.")
        ident = uuid.uuid4().hex
        directory = config.data_dir / "assets" / ident
        path = directory / "source"
        async with upload_lock:
            used = storage_bytes(config.data_dir)
            if used >= config.storage_quota_bytes:
                raise HTTPException(507, "Armazenamento cheio. Exclua arquivos ou resultados.")
            directory.mkdir(mode=0o700)
            try:
                total = 0
                with path.open("xb") as out:
                    os.chmod(path, 0o600)
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > config.max_upload_bytes:
                            raise HTTPException(413, "Arquivo maior que 150 MiB.")
                        if used + total > config.storage_quota_bytes:
                            raise HTTPException(507, "A cota de armazenamento foi excedida.")
                        out.write(chunk)
                filename = re.sub(r"[\x00-\x1f\x7f]", "", (file.filename or "arquivo").replace("\\", "/").split("/")[-1])[:180] or "arquivo"
                info = await asyncio.to_thread(inspect_asset, path, role, filename)
                if role == "reference" and info["kind"] != "video":
                    raise MediaError("A referência de movimento precisa ser um vídeo.")
                if role == "reference" and info["duration"] < 3:
                    raise MediaError("A referência de movimento precisa ter pelo menos 3 segundos.")
                analysis = await asyncio.to_thread(analyze_reference, path) if info["kind"] == "video" else {}
                asset = {**info, "id": ident, "role": role, "filename": filename, "size": total, "path": str(path), "file_url": f"/api/assets/{ident}/file", "review_status": "pending", "created_at": now(), "analysis": analysis}
                db.put_asset(asset)
                return public_asset(asset)
            except MediaError as exc:
                shutil.rmtree(directory, ignore_errors=True)
                raise HTTPException(422, str(exc))
            except BaseException:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            finally:
                await file.close()

    @app.get("/api/assets/{ident}/file")
    async def asset_file(ident: str):
        asset = get_asset(ident)
        return FileResponse(asset["path"], media_type=asset["content_type"], filename=asset["filename"], content_disposition_type="inline")

    @app.post("/api/assets/{ident}/review")
    async def review_asset(ident: str, body: ReviewAsset, x_review_token: str = Header(default="")):
        if not config.review_token:
            raise HTTPException(503, "A revisão exige MAYCOM_REVIEW_TOKEN configurado pelo operador.")
        if not config.desktop_mode and not hmac.compare_digest(x_review_token.encode(), config.review_token.encode()):
            raise HTTPException(403, "Token de revisão inválido.")
        asset = get_asset(ident)
        if any(j["status"] in ACTIVE and ident in (j["character_id"], j["reference_id"]) for j in db.jobs()):
            raise HTTPException(409, "Este arquivo está vinculado a uma geração ativa.")
        if body.decision == "approved" and not (body.fictional_adult_confirmed and body.non_intimate_confirmed):
            raise HTTPException(422, "A revisão deve confirmar personagem adulta fictícia e ausência de conteúdo íntimo.")
        asset.update(review_status=body.decision, reviewed_at=now())
        db.put_asset(asset)
        return public_asset(asset)

    @app.delete("/api/assets/{ident}", status_code=204)
    async def delete_asset(ident: str):
        get_asset(ident)
        if any(ident in (j["character_id"], j["reference_id"]) for j in db.jobs()):
            raise HTTPException(409, "Exclua primeiro as gerações que usam este arquivo.")
        shutil.rmtree(config.data_dir / "assets" / ident, ignore_errors=True)
        db.remove_asset(ident)

    @app.get("/api/jobs")
    async def jobs():
        return [public_job(j) for j in db.jobs()]

    @app.post("/api/jobs", status_code=202)
    async def create_job(body: CreateJob):
        state = await local_state(refresh=True)
        if not state["ready"]:
            raise HTTPException(503, " ".join(state["issues"]))
        if not config.review_token:
            raise HTTPException(503, "Configure a revisão de segurança antes de gerar.")
        character, reference = get_asset(body.character_id), get_asset(body.reference_id)
        if character["role"] != "character" or reference["role"] != "reference" or reference["kind"] != "video":
            raise HTTPException(422, "Selecione uma personagem e um vídeo de referência válidos.")
        if any(a["review_status"] != "approved" for a in (character, reference)):
            raise HTTPException(409, "Os dois arquivos precisam ser aprovados pelo operador antes da geração.")
        if body.settings.trim_start + body.settings.duration > (reference.get("duration") or 0) + 0.05:
            raise HTTPException(422, "O intervalo escolhido excede a duração do vídeo de referência.")
        # This product deliberately rejects intimate content rather than infer consent/age.
        if re.search(r"\b(nude|naked|nud[ae]s?|nudez|porn\w*|sex(?:ual|o)?|underage|minor|menor(?:es)?|child|crian[çc]a)\b", body.settings.prompt, flags=re.I):
            raise HTTPException(422, "Use apenas personagens adultas fictícias em cenas não íntimas.")
        ident, stamp = uuid.uuid4().hex, now()
        job = {"id": ident, "status": "queued", "stage": "Na fila local", "progress": None, "character_id": body.character_id, "reference_id": body.reference_id, "settings": {**body.settings.model_dump(), "engine": "comfy-local"}, "created_at": stamp, "updated_at": stamp, "error": None, "output_url": None, "quality_report": None, "provider_request_id": None, "logs": [{"time": stamp, "message": "Direitos, uso adulto fictício e ausência de conteúdo íntimo confirmados; arquivos revisados."}]}
        try:
            db.enqueue(job, config.max_queue)
        except ValueError as exc:
            raise HTTPException(429, str(exc))
        return public_job(job)

    @app.get("/api/jobs/{ident}")
    async def job(ident: str):
        return public_job(get_job(ident))

    @app.post("/api/jobs/{ident}/cancel")
    async def cancel_job(ident: str):
        value = get_job(ident)
        if value["status"] not in ACTIVE:
            raise HTTPException(409, "A geração já terminou.")
        result = db.update_job(ident, status="cancelled", stage="Cancelada", message="Cancelamento solicitado ao motor local. Aguarde a interrupção do processamento antes de excluir.")
        await worker.cancel_remote(value)
        if worker.current_id != ident:
            shutil.rmtree(config.data_dir / "jobs" / ident, ignore_errors=True)
        return public_job(result)

    @app.delete("/api/jobs/{ident}", status_code=204)
    async def delete_job(ident: str):
        value = get_job(ident)
        if value["status"] in ACTIVE or worker.current_id == ident:
            raise HTTPException(409, "Cancele ou aguarde o encerramento da tarefa antes de excluir.")
        shutil.rmtree(config.data_dir / "jobs" / ident, ignore_errors=True)
        db.remove_job(ident)

    @app.get("/api/jobs/{ident}/output")
    async def output(ident: str, download: bool = False):
        value = get_job(ident)
        if value["status"] != "completed" or not value.get("output_path") or not Path(value["output_path"]).is_file():
            raise HTTPException(404, "O vídeo ainda não está disponível.")
        return FileResponse(value["output_path"], media_type="video/mp4", filename=f"MAYCOM-CHEF-CONTROL-{ident[:8]}.mp4", content_disposition_type="attachment" if download else "inline")

    frontend = Path(os.getenv("MAYCOM_FRONTEND_DIR", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")))
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="studio")
    return app


app = create_app()
