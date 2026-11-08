"""Kling Motion Control through the official fal.ai queue and storage APIs.

This adapter never generates a stand-in video. An API key, available fal credit,
and access to the provider are required for inference. Local tests may inject
HTTP clients and an uploader, but production defaults always call real services.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urljoin, urlsplit

import httpx


class ProviderError(RuntimeError):
    """A safe error suitable for job records; never includes tokens or raw URLs."""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


Uploader = Callable[[Path], Awaitable[str]]


class FalMotionProvider:
    """Async adapter for verified Kling v3/v2.6 Motion Control endpoints.

    ``submit`` returns the provider request ID, suitable for durable storage.
    Poll/result/cancel URLs are rebuilt from the fixed official queue route,
    never accepted from a browser or followed blindly from a provider response.

    Character input must be an image. The application may explicitly extract a
    selected frame from a character video before submitting it. This is image
    identity conditioning, not character-video-to-video conditioning.
    """

    MODELS = {
        (version, quality): f"fal-ai/kling-video/{version}/{quality}/motion-control"
        for version in ("v3", "v2.6")
        for quality in ("standard", "pro")
    }
    QUEUE_BASE = "https://queue.fal.run"
    REQUEST_BASE = "https://queue.fal.run/fal-ai/kling-video/requests"
    DEFAULT_RESULT_HOSTS = ("fal.media", "*.fal.media")
    SUPPORTED_SETTINGS = {"model_version", "quality", "character_orientation", "keep_original_sound", "prompt"}

    def __init__(
        self,
        key: str,
        model: str = MODELS[("v3", "pro")],
        *,
        http_client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
        uploader: Uploader | None = None,
        result_hosts: tuple[str, ...] = DEFAULT_RESULT_HOSTS,
        max_result_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        if not key or not key.strip():
            raise ProviderError("Configure FAL_KEY para habilitar geração real.", code="missing_credentials")
        if model not in self.MODELS.values():
            raise ProviderError("Endpoint de Motion Control não suportado por este adaptador.", code="unsupported_model")
        if max_result_bytes < 1024:
            raise ValueError("max_result_bytes must be at least 1024")
        self._key = key
        self.model = model
        self._client = http_client
        self._download_client = download_client
        self._owns_client = http_client is None
        self._owns_download_client = download_client is None
        self._uploader = uploader
        self._upload_client: Any = None
        self._result_hosts = result_hosts
        self.max_result_bytes = max_result_bytes

    async def aclose(self) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
        if self._owns_download_client and self._download_client:
            await self._download_client.aclose()
        # fal-client does not expose a public close method for AsyncClient.
        # Its storage uploads use context-managed HTTP clients internally.

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(90, connect=20),
                follow_redirects=False,
                trust_env=True,
            )
        return self._client

    def _download_http(self) -> httpx.AsyncClient:
        if self._download_client is None:
            # Deliberately separate from queue authentication: never transmit
            # FAL_KEY to a result CDN or a signed download URL.
            self._download_client = httpx.AsyncClient(
                timeout=httpx.Timeout(180, connect=20),
                follow_redirects=False,
                trust_env=True,
            )
        return self._download_client

    @staticmethod
    def _request_id(request_id: str) -> str:
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            raise ProviderError("Identificador de tarefa do provedor inválido.", code="invalid_request_id")
        return quote(request_id, safe="")

    @staticmethod
    def _safe_status_error(status_code: int) -> ProviderError:
        if status_code in (401, 403):
            return ProviderError(
                "Acesso ao provedor recusado. Verifique a chave, os créditos e a política de rede.",
                code="provider_access_denied",
            )
        if status_code == 429:
            return ProviderError("Limite temporário do provedor atingido.", code="provider_rate_limit", retryable=True)
        if status_code in (400, 422):
            return ProviderError(
                "O provedor recusou os arquivos ou parâmetros; verifique conteúdo, enquadramento e duração.",
                code="provider_input_rejected",
            )
        if status_code == 404:
            return ProviderError("Tarefa não encontrada no provedor.", code="provider_request_missing")
        return ProviderError(
            f"Falha HTTP {status_code} no provedor.",
            code="provider_unavailable",
            retryable=status_code >= 500,
        )

    async def _json_request(self, method: str, url: str, *, allow_empty: bool = False, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._http().request(
                method,
                url,
                headers={"Authorization": f"Key {self._key}", "Accept": "application/json"},
                follow_redirects=False,
                **kwargs,
            )
        except httpx.RequestError:
            raise ProviderError(
                "Não foi possível comunicar com o provedor. Verifique a rede e tente novamente.",
                code="provider_network_error",
                retryable=True,
            ) from None
        if response.status_code >= 300:
            raise self._safe_status_error(response.status_code)
        if allow_empty and not response.content:
            return {}
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("Resposta inválida do provedor.", code="provider_invalid_response") from None
        if not isinstance(data, dict):
            raise ProviderError("Resposta inválida do provedor.", code="provider_invalid_response")
        return data

    async def _upload(self, path: Path) -> str:
        if self._uploader:
            return await self._uploader(path)
        try:
            import fal_client
            from fal_client.client import StorageSettings
        except ImportError:
            raise ProviderError(
                "Dependência fal-client ausente. Instale as dependências do backend.",
                code="missing_dependency",
            ) from None
        if self._upload_client is None:
            self._upload_client = fal_client.AsyncClient(key=self._key)
        try:
            # Official CDN storage with an explicit one-day object expiration.
            # No alternate repository is used if the configured path is denied.
            return await self._upload_client.upload_file(
                path,
                repository="fal_v3",
                fallback_repository=[],
                lifecycle=StorageSettings(expires_in="1d"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # SDK exceptions can contain signed URLs and request metadata.
            raise ProviderError(
                "Não foi possível enviar os arquivos ao armazenamento fal.ai. Verifique credenciais e rede.",
                code="provider_upload_error",
                retryable=True,
            ) from None

    async def submit(self, character_path: Path, reference_path: Path, settings: dict[str, Any]) -> str:
        unsupported = set(settings) - self.SUPPORTED_SETTINGS
        if unsupported:
            raise ProviderError(
                "Configuração não suportada pelo modelo selecionado.", code="unsupported_settings"
            )
        default_version, default_quality = next(key for key, model in self.MODELS.items() if model == self.model)
        version = settings.get("model_version", default_version)
        quality = settings.get("quality", default_quality)
        orientation = settings.get("character_orientation", "video")
        sound = settings.get("keep_original_sound", True)
        prompt = settings.get("prompt", "")
        if (version, quality) not in self.MODELS or orientation not in ("image", "video"):
            raise ProviderError("Qualidade ou orientação inválida.", code="invalid_settings")
        if not isinstance(sound, bool) or not isinstance(prompt, str) or len(prompt) > 2500:
            raise ProviderError("Parâmetros de geração inválidos.", code="invalid_settings")
        character_path, reference_path = Path(character_path), Path(reference_path)
        if not character_path.is_file() or not reference_path.is_file():
            raise ProviderError("Arquivo de entrada não encontrado.", code="input_missing")
        image_type = mimetypes.guess_type(character_path.name)[0] or ""
        video_type = mimetypes.guess_type(reference_path.name)[0] or ""
        if not image_type.startswith("image/") or not video_type.startswith("video/"):
            raise ProviderError(
                "O adaptador exige uma imagem da personagem e um vídeo de movimento.", code="invalid_input_type"
            )
        # Sequential uploads avoid doubling peak memory for large video input.
        image_url = await self._upload(character_path)
        video_url = await self._upload(reference_path)
        arguments = {
            "image_url": image_url,
            "video_url": video_url,
            "character_orientation": orientation,
            "keep_original_sound": sound,
            "enable_safety_checker": True,
        }
        if prompt.strip():
            arguments["prompt"] = prompt.strip()
        # Never retry this POST automatically: a lost response could otherwise
        # create a second chargeable generation.
        data = await self._json_request("POST", f"{self.QUEUE_BASE}/{self.MODELS[(version, quality)]}", json=arguments)
        request_id = data.get("request_id")
        self._request_id(request_id)
        return request_id

    async def status(self, request_id: str) -> dict[str, Any]:
        rid = self._request_id(request_id)
        data = await self._json_request("GET", f"{self.REQUEST_BASE}/{rid}/status", params={"logs": "false"})
        status = data.get("status")
        if status not in ("IN_QUEUE", "IN_PROGRESS", "COMPLETED"):
            raise ProviderError("Estado de tarefa inesperado no provedor.", code="provider_invalid_response")
        result: dict[str, Any] = {"status": status, "logs": []}
        position = data.get("queue_position")
        if isinstance(position, int) and not isinstance(position, bool) and position >= 0:
            result["queue_position"] = position
        # Fal does not expose an accurate percent for this endpoint. Do not
        # invent progress, ETA, model metrics, or a duration from queue state.
        return result

    async def result(self, request_id: str) -> dict[str, Any]:
        rid = self._request_id(request_id)
        data = await self._json_request("GET", f"{self.REQUEST_BASE}/{rid}")
        video = data.get("video")
        if not isinstance(video, dict) or not isinstance(video.get("url"), str):
            raise ProviderError("O provedor não retornou um vídeo.", code="provider_missing_video")
        self._validate_result_url(video["url"])
        return {
            "video_url": video["url"],
            "content_type": video.get("content_type") or "video/mp4",
            "file_size": video.get("file_size"),
        }

    async def cancel(self, request_id: str) -> None:
        rid = self._request_id(request_id)
        # Queue cancel responds with JSON on the official API. Do not follow
        # any returned URL or describe an in-flight model as stopped instantly.
        await self._json_request("PUT", f"{self.REQUEST_BASE}/{rid}/cancel", allow_empty=True)

    def _validate_result_url(self, url: str) -> None:
        try:
            parts = urlsplit(url)
            hostname = (parts.hostname or "").lower().rstrip(".")
            valid_port = parts.port in (None, 443)
        except ValueError:
            raise ProviderError("URL de vídeo inválida.", code="unsafe_result_url") from None
        allowed = any(
            hostname == pattern.lower()
            if not pattern.startswith("*.")
            else hostname.endswith(pattern[1:].lower()) and hostname != pattern[2:].lower()
            for pattern in self._result_hosts
        )
        if (
            parts.scheme != "https"
            or not allowed
            or not valid_port
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
        ):
            raise ProviderError("O vídeo retornou fora do CDN permitido.", code="unsafe_result_url")

    async def download_result(self, url: str, destination: Path) -> None:
        """Stream a real result to disk with strict CDN/size/MP4 checks.

        Signed URLs are used only in memory, never returned in error strings.
        Each redirect is checked before sending a request to its destination.
        Partial files are removed after failures and cancellation.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            for hop in range(4):
                self._validate_result_url(url)
                async with self._download_http().stream(
                    "GET", url, headers={"Accept": "video/mp4,application/octet-stream"}, follow_redirects=False
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location or hop == 3:
                            raise ProviderError("Redirecionamento de vídeo inválido.", code="unsafe_result_url")
                        url = urljoin(url, location)
                        self._validate_result_url(url)
                        continue
                    if response.status_code != 200:
                        raise ProviderError(
                            "Não foi possível baixar o vídeo gerado.",
                            code="result_download_failed",
                            retryable=response.status_code >= 500,
                        )
                    length = response.headers.get("content-length")
                    if length:
                        try:
                            too_large = int(length) > self.max_result_bytes or int(length) <= 0
                        except ValueError:
                            raise ProviderError("Tamanho de vídeo inválido.", code="invalid_result") from None
                        if too_large:
                            raise ProviderError("Vídeo excede o limite de armazenamento.", code="result_too_large")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                    if content_type not in ("video/mp4", "application/octet-stream", ""):
                        raise ProviderError("O resultado não é um arquivo MP4.", code="invalid_result")
                    total = 0
                    with tempfile.NamedTemporaryFile(
                        prefix=".maycom-result-", suffix=".part", dir=destination.parent, delete=False
                    ) as output:
                        temporary = Path(output.name)
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            total += len(chunk)
                            if total > self.max_result_bytes:
                                raise ProviderError("Vídeo excede o limite de armazenamento.", code="result_too_large")
                            output.write(chunk)
                    with temporary.open("rb") as downloaded:
                        header = downloaded.read(12)
                    if total < 12 or header[4:8] != b"ftyp":
                        raise ProviderError("O resultado não contém um MP4 válido.", code="invalid_result")
                    os.replace(temporary, destination)
                    temporary = None
                    return
            raise ProviderError("Redirecionamentos excessivos.", code="unsafe_result_url")
        except httpx.RequestError:
            raise ProviderError(
                "Falha de rede ao baixar o vídeo gerado.", code="result_network_error", retryable=True
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
