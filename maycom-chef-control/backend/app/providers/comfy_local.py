"""Real loopback-only ComfyUI motion generation; no paid API or fallback.

The fixed workflow uses Wan VACE 1.3B, CPU ONNX pose estimation, a character
reference, CPU text encoder, and tiled VAE decoding. AMD/DirectML inference is
experimental and must be validated on the user's machine.
"""
import asyncio
import json
import os
from pathlib import Path, PurePosixPath
import secrets
from urllib.parse import urlsplit

import httpx

from .fal_motion import ProviderError


MODEL = "wan2.1_vace_1.3B_fp16.safetensors"
ENCODER = "umt5_xxl_fp16.safetensors"
VAE = "wan_2.1_vae.safetensors"
MODEL_LABEL = "Wan VACE 1.3B"
REQUIRED_NODES = (
    "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "LoadImage",
    "LoadVideo", "GetVideoComponents", "DWPreprocessor", "WanVaceToVideo",
    "ModelSamplingSD3", "KSampler", "TrimVideoLatent", "VAEDecodeTiled",
    "CreateVideo", "SaveVideo",
)


def local_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if (parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost")
                or parts.username or parts.password or parts.path not in ("", "/")
                or parts.query or parts.fragment or not parts.port or not 1024 <= parts.port <= 65535):
            raise ValueError()
        # Normalize localhost to an IP literal. No external DNS or proxy used.
        return f"http://127.0.0.1:{parts.port}"
    except (ValueError, AttributeError):
        raise ValueError("Use um endereço local como http://127.0.0.1:8188.") from None


def _choices(info, node, field):
    data = info.get(node, {}).get("input", {})
    value = data.get("required", {}).get(field) or data.get("optional", {}).get(field)
    return value[0] if isinstance(value, list) and value and isinstance(value[0], list) else []


def _model_name(info, node, field, filename):
    return next((name for name in _choices(info, node, field)
                 if isinstance(name, str) and name.replace("\\", "/").split("/")[-1] == filename), None)


class ComfyLocalProvider:
    def __init__(self, url, *, http_client=None):
        self.url = local_url(url)
        self.client = http_client or httpx.AsyncClient(
            base_url=self.url, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(60, connect=3),
        )
        self.owns_client = http_client is None

    async def aclose(self):
        if self.owns_client:
            await self.client.aclose()

    async def _json(self, method, path, *, allow_empty=False, **kwargs):
        try:
            response = await self.client.request(method, self.url + path, follow_redirects=False, **kwargs)
        except httpx.RequestError:
            raise ProviderError("Não foi possível conectar ao ComfyUI local. Abra o motor no seu computador.", code="local_unavailable") from None
        if response.status_code >= 300:
            raise ProviderError("O motor local recusou a solicitação. Verifique os modelos, os nós e o console do ComfyUI.", code="local_rejected")
        if allow_empty and not response.content:
            return {}
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            raise ProviderError("Resposta inválida do motor local.", code="local_invalid_response") from None

    async def inspect(self):
        result = {"url": self.url, "ready": False, "configured": False, "issues": [],
                  "model": MODEL_LABEL, "gpu": {"available": False, "name": None, "vram_gb": None}}
        try:
            stats, info = await asyncio.gather(self._json("GET", "/system_stats"), self._json("GET", "/object_info"))
        except ProviderError as exc:
            result["issues"].append(str(exc))
            return result
        result["configured"] = True
        devices = stats.get("devices", [])
        device = next((d for d in devices if d.get("type") != "cpu"), None)
        if device:
            result["gpu"] = {"available": True, "name": str(device.get("name", "GPU local")),
                             "vram_gb": round((device.get("vram_total") or 0) / 1024**3, 1) or None}
        else:
            result["issues"].append("ComfyUI está usando CPU. A RX 6600 requer um backend AMD compatível; DirectML é experimental.")
        missing = [node for node in REQUIRED_NODES if node not in info]
        if missing:
            result["issues"].append("Nós ausentes: " + ", ".join(missing) + ". Instale o ComfyUI compatível e o pacote controlnet_aux.")
        for node, field, filename in (("UNETLoader", "unet_name", MODEL), ("CLIPLoader", "clip_name", ENCODER), ("VAELoader", "vae_name", VAE)):
            if not _model_name(info, node, field, filename):
                result["issues"].append("Modelo ausente: " + filename)
        result["ready"] = not result["issues"]
        return result

    @staticmethod
    def workflow(character, reference, settings, info, prefix):
        def node(kind, **inputs):
            return {"class_type": kind, "inputs": inputs}
        width, height = settings["local_width"], settings["local_height"]
        length = int(settings["duration"] * 16) // 4 * 4 + 1
        graph = {
            "1": node("UNETLoader", unet_name=_model_name(info, "UNETLoader", "unet_name", MODEL), weight_dtype="default"),
            "2": node("CLIPLoader", clip_name=_model_name(info, "CLIPLoader", "clip_name", ENCODER), type="wan", device="cpu"),
            "3": node("VAELoader", vae_name=_model_name(info, "VAELoader", "vae_name", VAE)),
            "4": node("CLIPTextEncode", clip=["2", 0], text="An adult fictional character follows the body movements in the pose sequence. Natural motion, consistent clothing and appearance. " + settings.get("prompt", "")),
            "5": node("CLIPTextEncode", clip=["2", 0], text="deformed hands, distorted anatomy, flicker, blurry, low quality"),
            "6": node("LoadImage", image=character),
            "7": node("LoadVideo", file=reference),
            "8": node("GetVideoComponents", video=["7", 0]),
            "9": node("DWPreprocessor", image=["8", 0], detect_hand="enable", detect_body="enable", detect_face="enable", resolution=480, bbox_detector="yolox_l.onnx", pose_estimator="dw-ll_ucoco_384.onnx", scale_stick_for_xinsr_cn="disable"),
            "10": node("WanVaceToVideo", positive=["4", 0], negative=["5", 0], vae=["3", 0], width=width, height=height, length=length, batch_size=1, strength=1.0, reference_image=["6", 0], control_video=["9", 0]),
            "11": node("ModelSamplingSD3", model=["1", 0], shift=8.0),
            "12": node("KSampler", model=["11", 0], positive=["10", 0], negative=["10", 1], latent_image=["10", 2], seed=secrets.randbits(48), steps=30 if settings.get("quality") == "pro" else 20, cfg=6.0, sampler_name="uni_pc", scheduler="simple", denoise=1.0),
            "13": node("TrimVideoLatent", samples=["12", 0], trim_amount=["10", 3]),
            "14": node("VAEDecodeTiled", samples=["13", 0], vae=["3", 0], tile_size=256, overlap=64, temporal_size=16, temporal_overlap=4),
            "15": node("CreateVideo", images=["14", 0], fps=16.0),
            "16": node("SaveVideo", video=["15", 0], filename_prefix=prefix, format="mp4", codec="h264"),
        }
        return graph

    async def _upload(self, path, suffix):
        # Unique basename and no subfolder avoid file picker inconsistencies.
        filename = "maycom-" + secrets.token_hex(16) + suffix
        with Path(path).open("rb") as source:
            data = await self._json("POST", "/upload/image", files={"image": (filename, source)}, data={"type": "input", "overwrite": "false"})
        if data.get("name") != filename or data.get("subfolder") not in (None, ""):
            raise ProviderError("O motor local retornou um caminho de entrada inválido.")
        return filename

    async def submit(self, character_path, reference_path, settings):
        state = await self.inspect()
        if not state["ready"]:
            raise ProviderError(" ".join(state["issues"]), code="local_not_ready")
        info = await self._json("GET", "/object_info")
        character = await self._upload(character_path, ".png")
        reference = await self._upload(reference_path, ".mp4")
        graph = self.workflow(character, reference, settings, info, "maycom/" + secrets.token_hex(16))
        data = await self._json("POST", "/prompt", json={"prompt": graph, "client_id": "maycom-" + secrets.token_hex(16)})
        return self._request_id(data.get("prompt_id"))

    @staticmethod
    def _request_id(value):
        import re
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise ProviderError("Identificador de tarefa local inválido.")
        return value

    async def _history(self, request_id):
        ident = self._request_id(request_id)
        history = (await self._json("GET", "/history/" + ident)).get(ident)
        if history and history.get("status", {}).get("status_str") == "error":
            # Console diagnostics may contain paths and prompt contents.
            raise ProviderError("A geração local falhou. Verifique o console do ComfyUI; na RX 6600 pode haver falta de memória ou operação incompatível com DirectML.", code="local_inference_failed")
        return history

    async def status(self, request_id):
        history = await self._history(request_id)
        if history and history.get("status", {}).get("completed"):
            return {"status": "COMPLETED"}
        queue = await self._json("GET", "/queue")
        if any(len(item) > 1 and item[1] == request_id for item in queue.get("queue_running", [])):
            return {"status": "IN_PROGRESS"}
        if any(len(item) > 1 and item[1] == request_id for item in queue.get("queue_pending", [])):
            return {"status": "IN_QUEUE"}
        # A task removed from the local queue cannot be resumed remotely.
        if await self._history(request_id):
            return {"status": "COMPLETED"}
        raise ProviderError("Tarefa não encontrada no motor local. Ele pode ter reiniciado; gere novamente.", code="local_request_missing")

    async def result(self, request_id):
        history = await self._history(request_id)
        outputs = (history or {}).get("outputs", {}).get("16", {})
        files = outputs.get("images", [])
        if not files:
            raise ProviderError("O motor local não produziu o MP4 esperado.")
        output = files[0]
        filename, folder = output.get("filename", ""), output.get("subfolder", "")
        if (not filename.endswith(".mp4") or PurePosixPath(filename).name != filename or "\\" in filename
                or not folder.startswith("maycom") or ".." in PurePosixPath(folder).parts or "\\" in folder
                or PurePosixPath(folder).is_absolute() or output.get("type") != "output"):
            raise ProviderError("Caminho de resultado local inválido.")
        return {"video_url": json.dumps({"filename": filename, "subfolder": folder, "type": "output"})}

    async def download_result(self, descriptor, destination):
        # A JSON descriptor is passed back to the same loopback endpoint. Never
        # accept a remote URL from history, and never send a fal/API credential.
        params = json.loads(descriptor)
        destination = Path(destination)
        temporary = destination.with_suffix(".part")
        try:
            async with self.client.stream("GET", self.url + "/view", params=params, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ProviderError("Não foi possível ler o resultado do motor local.")
                total = 0
                with temporary.open("wb") as out:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > 512 * 1024 * 1024:
                            raise ProviderError("Resultado local excede o limite de 512 MiB.")
                        out.write(chunk)
            with temporary.open("rb") as source:
                header = source.read(12)
            if header[4:8] != b"ftyp":
                raise ProviderError("O motor local não retornou um MP4 válido.")
            os.replace(temporary, destination)
        except httpx.RequestError:
            raise ProviderError("A conexão com o motor local foi interrompida.") from None
        finally:
            temporary.unlink(missing_ok=True)

    async def cancel(self, request_id):
        ident = self._request_id(request_id)
        await self._json("POST", "/queue", allow_empty=True, json={"delete": [ident]})
        queue = await self._json("GET", "/queue")
        running = queue.get("queue_running", [])
        if len(running) == 1 and len(running[0]) > 1 and running[0][1] == ident:
            # ComfyUI's interruption is server-wide. Use a dedicated instance;
            # never interrupt if another user's task is observed as active.
            try:
                response = await self.client.post(self.url + "/interrupt", json={})
                response.raise_for_status()
            except httpx.HTTPError:
                raise ProviderError("Cancelamento solicitado; confirme a interrupção no ComfyUI local.") from None


async def inspect_local(settings):
    provider = ComfyLocalProvider(settings.comfy_url)
    try:
        return await provider.inspect()
    finally:
        await provider.aclose()
