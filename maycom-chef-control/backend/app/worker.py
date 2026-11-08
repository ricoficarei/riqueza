import asyncio
import shutil
from pathlib import Path

from .database import ACTIVE, now
from .config import storage_bytes
from .media import MediaError, prepare_character, trim_reference, export_video, prepare_local_reference, restore_reference_audio
from .quality import assess_output
from .providers import ProviderError
from .providers.comfy_local import ComfyLocalProvider


class JobCancelled(Exception):
    pass


class Worker:
    def __init__(self, db, settings, provider_factory=None):
        self.db, self.settings = db, settings
        # Production uses only loopback inference. Explicit test providers can
        # exercise queue/media handling; there is no paid runtime fallback.
        self.local = provider_factory is None
        self.provider_factory = provider_factory or (lambda options: ComfyLocalProvider(settings.comfy_url))
        self.current_id = None

    def alive(self, ident):
        job = self.db.job(ident)
        if not job or job["status"] == "cancelled":
            raise JobCancelled()
        return job

    async def run(self):
        while True:
            job = self.db.claim()
            if not job:
                await asyncio.sleep(0.5)
                continue
            self.current_id = job["id"]
            try:
                await asyncio.wait_for(self.process(job), timeout=self.settings.max_job_seconds)
            except JobCancelled:
                pass
            except asyncio.TimeoutError:
                await self.cancel_remote(self.db.job(job["id"]))
                self.db.update_job(job["id"], status="failed", stage="Tempo limite", error="O processamento excedeu o tempo limite. Confira o console do motor local.", message="Tempo limite excedido; interrupção solicitada quando disponível.")
            except (ProviderError, MediaError) as exc:
                current = self.db.job(job["id"])
                message = str(exc)
                if not self.local and current and current["status"] == "submitting" and not current.get("provider_request_id"):
                    message += " Se o envio chegou ao provedor, a cobrança pode ter ocorrido. Confira o painel fal.ai antes de reenviar."
                self.db.update_job(job["id"], status="failed", stage="Falha no processamento", error=message, message="Processamento encerrado com erro; nenhum resultado foi simulado.")
            except asyncio.CancelledError:
                # Keep remote request IDs for recovery; do not re-submit on restart.
                raise
            except Exception:
                self.db.update_job(job["id"], status="failed", stage="Falha interna", error="O processamento falhou. Verifique a configuração e tente novamente.", message="Erro interno; detalhes sensíveis foram omitidos.")
            finally:
                self.current_id = None
                # Partial work is private and retained only for active jobs.
                current = self.db.job(job["id"])
                if current and current["status"] in ("failed", "cancelled"):
                    shutil.rmtree(self.settings.data_dir / "jobs" / job["id"], ignore_errors=True)

    async def cancel_remote(self, job):
        if job and job.get("provider_request_id"):
            provider = self.provider_factory(job["settings"])
            try:
                await provider.cancel(job["provider_request_id"])
                return True
            except Exception:
                return False
            finally:
                await provider.aclose()
        return False

    async def process(self, job):
        provider = self.provider_factory(job["settings"])
        try:
            await self._process(job, provider)
        finally:
            await provider.aclose()

    async def _process(self, job, provider):
        ident, options = job["id"], job["settings"]
        directory = self.settings.data_dir / "jobs" / ident
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        request_id = job.get("provider_request_id")
        if not request_id:
            used = storage_bytes(self.settings.data_dir)
            reserve = 1200 * 1024 * 1024
            if used + reserve > self.settings.storage_quota_bytes or shutil.disk_usage(directory).free < reserve:
                raise MediaError("Libere pelo menos 1,2 GiB para preparar, baixar e exportar a geração.")
            character = self.db.asset(job["character_id"])
            reference = self.db.asset(job["reference_id"])
            if not character or not reference or any(a["review_status"] != "approved" for a in (character, reference)):
                raise MediaError("Os arquivos precisam estar presentes e aprovados na revisão.")
            self.alive(ident)
            self.db.update_job(ident, stage="Preparando identidade e intervalo de movimento", message="Preparação real via FFmpeg; vídeos da personagem usam o primeiro frame como identidade.")
            image_path = await asyncio.to_thread(prepare_character, Path(character["path"]), directory / "character.png", character["kind"])
            self.alive(ident)
            reference_path = await asyncio.to_thread(trim_reference, Path(reference["path"]), directory / "reference.mp4", options["trim_start"], options["duration"])
            self.alive(ident)
            inference_options = {k: options[k] for k in ("model_version", "quality", "character_orientation", "keep_original_sound", "prompt")}
            if self.local:
                reference_path, width, height = await asyncio.to_thread(prepare_local_reference, reference_path, directory / "motion16.mp4")
                inference_options.update(duration=options["duration"], local_width=width, local_height=height)
            self.alive(ident)
            self.db.update_job(ident, status="submitting", stage="Enviando ao motor local", message="Preparando geração neste computador, sem conta ou créditos de API.")
            request_id = await provider.submit(image_path, reference_path, inference_options)
            # Persist the ID even if cancellation happened during the HTTP submission.
            self.db.update_job(ident, allow_terminal=True, provider_request_id=request_id)
            if self.db.job(ident)["status"] == "cancelled":
                await self.cancel_remote(self.db.job(ident))
                raise JobCancelled()
        self.db.update_job(ident, status="running", stage="Na fila do motor", message="Tarefa identificada; progresso indeterminado até a geração terminar.")
        while True:
            self.alive(ident)
            remote = await self.retry_read(lambda: provider.status(request_id))
            state = remote.get("status")
            if state == "COMPLETED":
                break
            if state not in ("IN_QUEUE", "IN_PROGRESS"):
                raise ProviderError("O provedor retornou um estado inesperado.")
            stage = "Gerando movimentos" if state == "IN_PROGRESS" else "Na fila do motor"
            self.db.update_job(ident, stage=stage, queue_position=remote.get("queue_position"))
            await asyncio.sleep(self.settings.poll_interval)
        self.alive(ident)
        result = await self.retry_read(lambda: provider.result(request_id))
        self.db.update_job(ident, status="validating", stage="Verificando vídeo", message="Validando o vídeo gerado e exportando MP4.")
        raw = directory / "provider.mp4"
        await self.retry_read(lambda: provider.download_result(result["video_url"], raw))
        self.alive(ident)
        if self.local and options["keep_original_sound"]:
            reference = self.db.asset(job["reference_id"])
            if reference:
                await asyncio.to_thread(restore_reference_audio, raw, Path(reference["path"]), directory / "with-audio.mp4", options["trim_start"], options["duration"])
                raw.unlink(missing_ok=True)
                (directory / "with-audio.mp4").replace(raw)
            self.alive(ident)
        final = directory / "output.mp4"
        await asyncio.to_thread(export_video, raw, final, options["output_fps"])
        self.alive(ident)
        report = await asyncio.to_thread(assess_output, final)
        self.alive(ident)
        raw.unlink(missing_ok=True)
        # Retain only final output; input assets have their own delete lifecycle.
        for name in ("character.png", "reference.mp4", "motion16.mp4"):
            (directory / name).unlink(missing_ok=True)
        self.db.update_job(ident, status="completed", stage="Vídeo disponível", output_path=str(final), output_url=f"/api/jobs/{ident}/output", quality_report=report, message="MP4 gerado e validado. Revise rosto, mãos e movimentos; métricas temporais não comprovam identidade ou anatomia.")

    @staticmethod
    async def retry_read(operation):
        for attempt in range(3):
            try:
                return await operation()
            except ProviderError as exc:
                if not exc.retryable or attempt == 2:
                    raise
                await asyncio.sleep(2 ** (attempt + 1))
