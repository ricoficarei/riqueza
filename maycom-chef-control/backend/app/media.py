"""Content-based validation and real, bounded media processing.

These helpers never infer a person's age, consent, identity or anatomy. Callers
must enforce the application's review and authorization policy separately.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import warnings
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError


class MediaError(ValueError):
    """A safe media-processing error suitable for an API response."""


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_VIDEO_SECONDS = 300
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        raise MediaError("FFmpeg/FFprobe não está instalado no servidor.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("O processamento excedeu o tempo permitido. Use um arquivo menor.") from exc
    except OSError as exc:
        raise MediaError("Não foi possível iniciar o processamento da mídia.") from exc
    if result.returncode:
        # Tool output can include local paths and user-controlled container tags.
        # Do not send it verbatim to a client or to public job logs.
        raise MediaError("Não foi possível processar a mídia. Verifique o formato e a integridade do arquivo.")
    return result


def _positive_number(value: Any, default: float = 0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else default
    except (TypeError, ValueError):
        return default


def _probe(path: Path) -> dict[str, Any]:
    result = _run(
        [
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-format_whitelist", "mov,matroska,webm",
            "-show_streams", "-show_format", "-of", "json", str(path),
        ],
        timeout=30,
    )
    try:
        data = json.loads(result.stdout)
        streams = data["streams"]
        video = next(
            stream for stream in streams
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic")
        )
        container = data.get("format", {})
        width, height = int(video["width"]), int(video["height"])
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise MediaError("O arquivo não contém uma faixa de vídeo válida.") from exc
    fps = 0.0
    for field in ("avg_frame_rate", "r_frame_rate"):
        try:
            fps = float(Fraction(video.get(field, "0/1")))
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        if math.isfinite(fps) and fps > 0:
            break
    duration = _positive_number(container.get("duration")) or _positive_number(video.get("duration"))
    if not fps or not duration or not width or not height:
        raise MediaError("Não foi possível determinar duração, dimensões ou FPS do vídeo.")
    # FFprobe reports encoded dimensions separately from display rotation.
    rotation = 0
    for side_data in video.get("side_data_list", []):
        rotation = side_data.get("rotation", rotation)
    try:
        rotation = int(rotation or video.get("tags", {}).get("rotate", 0))
    except (TypeError, ValueError):
        rotation = 0
    if abs(rotation) % 180 == 90:
        width, height = height, width
    frame_count = int(_positive_number(video.get("nb_frames"))) or round(duration * fps)
    return {
        "kind": "video",
        "width": width,
        "height": height,
        "duration": round(duration, 4),
        "fps": round(fps, 4),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "codec": video.get("codec_name", "unknown"),
        "format": container.get("format_name", "unknown"),
        "frame_count": frame_count,
        "rotation": rotation,
    }


def inspect_asset(path: Path, role: str, original_name: str) -> dict[str, Any]:
    """Validate uploaded bytes, rather than trusting the name or MIME header.

    Long references may be uploaded for selection, but generation must use
    ``trim_reference`` to select a three-to-thirty second interval.
    """
    path = Path(path)
    if role not in {"character", "reference"}:
        raise MediaError("Tipo de arquivo inválido.")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MediaError("O arquivo enviado não está disponível.") from exc
    if not path.is_file() or size <= 0:
        raise MediaError("O arquivo enviado está vazio ou não é válido.")
    if size > MAX_VIDEO_BYTES:
        raise MediaError("O arquivo excede o limite de 150 MiB.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image_format = image.format
                if image_format not in IMAGE_TYPES:
                    raise MediaError("Envie uma imagem JPEG, PNG ou WebP, ou um vídeo MP4, MOV ou WebM.")
                width, height = image.size
                if size > MAX_IMAGE_BYTES:
                    raise MediaError("A imagem excede o limite de 20 MiB.")
                if width * height > MAX_IMAGE_PIXELS or max(width, height) > 16384:
                    raise MediaError("A imagem excede o limite de 40 megapixels ou 16384 pixels por lado.")
                if min(width, height) < 64:
                    raise MediaError("A imagem deve ter pelo menos 64 pixels em cada dimensão.")
                image.verify()
            with Image.open(path) as image:
                orientation = image.getexif().get(274, 1)
                if orientation in {5, 6, 7, 8}:
                    width, height = height, width
            if role == "reference":
                raise MediaError("A referência de movimento deve ser um vídeo.")
            return {
                "kind": "image", "width": width, "height": height,
                "duration": None, "fps": None, "has_audio": False,
                "content_type": IMAGE_TYPES[image_format], "format": image_format.lower(),
                "codec": None, "frame_count": 1, "size": size,
                "original_name": Path(original_name).name,
            }
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MediaError("A imagem excede o limite seguro de dimensões.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, MediaError):
            raise
        # The image decoder did not recognize it. FFprobe independently checks
        # whether it is one of the video containers the application supports.
        pass

    metadata = _probe(path)
    formats = set(metadata["format"].split(","))
    if not formats.intersection({"mov", "mp4", "matroska", "webm"}):
        raise MediaError("Formato de vídeo não suportado. Use MP4, MOV ou WebM.")
    if metadata["duration"] > MAX_VIDEO_SECONDS:
        raise MediaError("Envie vídeos de até 5 minutos e selecione o trecho para geração.")
    if min(metadata["width"], metadata["height"]) < 64 or max(metadata["width"], metadata["height"]) > 7680:
        raise MediaError("As dimensões do vídeo devem estar entre 64 e 7680 pixels.")
    if metadata["fps"] > 120:
        raise MediaError("Envie um vídeo com até 120 FPS.")
    metadata.update({
        "content_type": "video/webm" if "webm" in formats and "mov" not in formats else "video/mp4",
        "size": size,
        "original_name": Path(original_name).name,
    })
    return metadata


def prepare_character(source: Path, destination: Path, kind: str) -> Path:
    """Create an RGB PNG without source EXIF, or use video frame zero.

    Video input is an identity *still*, not a video-to-video model adapter.
    The API and UI should communicate this explicitly to the user.
    """
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "image":
        try:
            with Image.open(source) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise MediaError("A imagem excede o limite seguro de dimensões.")
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.save(destination, format="PNG")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            if isinstance(exc, MediaError):
                raise
            raise MediaError("Não foi possível preparar a imagem da personagem.") from exc
    elif kind == "video":
        _run([
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2",
            "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm", "-i", str(source),
            "-map", "0:v:0", "-frames:v", "1", "-map_metadata", "-1",
            "-threads", "2", "-c:v", "png", str(destination),
        ], timeout=60)
    else:
        raise MediaError("O arquivo da personagem deve ser imagem ou vídeo.")
    if not destination.is_file() or not destination.stat().st_size:
        raise MediaError("Não foi possível extrair a imagem da personagem.")
    return destination


def trim_reference(source: Path, destination: Path, start: float, duration: float) -> Path:
    """Re-encode the chosen real video interval into a provider-ready MP4."""
    try:
        start, duration = float(start), float(duration)
    except (ValueError, TypeError) as exc:
        raise MediaError("O intervalo selecionado é inválido.") from exc
    if not math.isfinite(start) or start < 0 or not math.isfinite(duration) or not 3 <= duration <= 30:
        raise MediaError("Selecione um trecho de 3 a 30 segundos com início válido.")
    metadata = _probe(Path(source))
    if start + duration > metadata["duration"] + 0.05:
        raise MediaError("O trecho selecionado ultrapassa a duração do vídeo.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2",
        "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm", "-ss", str(start), "-i", str(source),
        "-t", str(duration), "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "-1", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "2",
        "-filter_threads", "2", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(destination),
    ], timeout=240)
    actual = _probe(destination)
    if actual["duration"] < 2.9 or abs(actual["duration"] - duration) > 0.35:
        raise MediaError("Não foi possível preparar o trecho com a duração selecionada.")
    return destination


def prepare_local_reference(source: Path, destination: Path):
    """Use actual reference motion at the local model's 16 FPS and 480p."""
    metadata = _probe(source)
    width, height = (480, 832) if metadata["height"] > metadata["width"] else (832, 480)
    _run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2",
        "-i", str(source), "-an", "-map_metadata", "-1",
        "-vf", f"fps=16,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-threads", "2", "-filter_threads", "2", "-pix_fmt", "yuv420p", "-crf", "18", str(destination),
    ], timeout=120)
    return Path(destination), width, height


def restore_reference_audio(video: Path, reference: Path, destination: Path, start: float, duration: float):
    """Copy authorized reference audio over real generated frames, if present."""
    _run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video),
        "-ss", str(start), "-i", str(reference), "-t", str(duration),
        "-map", "0:v:0", "-map", "1:a?", "-map_metadata", "-1",
        "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(destination),
    ], timeout=120)


def export_video(source: Path, destination: Path, fps: int) -> dict[str, Any]:
    """Export a newly generated video as MP4 without inventing missing frames.

    FFmpeg's FPS resampling duplicates/drops frames; it does not perform neural
    frame interpolation. The original resolution is preserved.
    """
    if fps not in {24, 30}:
        raise MediaError("A exportação permite 24 ou 30 FPS.")
    _probe(Path(source))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2",
        "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "-1",
        "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-threads", "2", "-filter_threads", "2", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(destination),
    ], timeout=300)
    metadata = _probe(destination)
    metadata.update({"content_type": "video/mp4", "size": destination.stat().st_size})
    return metadata
