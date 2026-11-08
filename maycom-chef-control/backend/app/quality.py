"""Measured visual diagnostics, explicitly separate from biometric validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .media import MediaError, _probe


LIMITATION = (
    "Estas métricas medem variações visuais, não verificam idade, consentimento, "
    "identidade, anatomia, mãos, roupas ou qualidade cinematográfica. "
    "A preservação da personagem e a naturalidade exigem revisão humana."
)


def _sample_metrics(path: Path, max_samples: int = 48) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {
            "available": False,
            "reason": "OpenCV/NumPy não está disponível para análise visual.",
            "limitation": LIMITATION,
        }
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise MediaError("Não foi possível analisar os frames do vídeo.")
    frames_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frames_total < 2:
        cap.release()
        raise MediaError("O vídeo não contém frames suficientes para análise temporal.")
    sample_count = min(max_samples, frames_total)
    positions = np.unique(np.linspace(0, frames_total - 1, sample_count, dtype=int))
    brightness: list[float] = []
    sharpness: list[float] = []
    motion: list[float] = []
    frame_difference: list[float] = []
    histogram_distances: list[float] = []
    previous = None
    previous_histogram = None
    try:
        for position in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = cap.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            scale = min(1, 320 / max(width, height))
            small = cv2.resize(frame, (max(2, round(width * scale)), max(2, round(height * scale))))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            brightness.append(float(gray.mean()))
            sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            histogram = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(histogram, histogram)
            if previous is not None and previous.shape == gray.shape:
                flow = cv2.calcOpticalFlowFarneback(previous, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                magnitude = np.linalg.norm(flow, axis=2)
                motion.append(float(np.mean(magnitude)))
                frame_difference.append(float(cv2.absdiff(previous, gray).mean() / 255))
                histogram_distances.append(float(cv2.compareHist(previous_histogram, histogram, cv2.HISTCMP_BHATTACHARYYA)))
            previous, previous_histogram = gray, histogram
    finally:
        cap.release()
    if len(brightness) < 2:
        raise MediaError("Não foi possível decodificar frames suficientes para análise visual.")
    brightness_jumps = np.abs(np.diff(brightness)) / 255
    # A histogram shift plus an image difference is an approximate scene-change
    # detector; it deliberately makes no claim of temporal-generation failure.
    scene_cuts = sum(
        histogram > 0.55 and difference > 0.2
        for histogram, difference in zip(histogram_distances, frame_difference)
    )
    return {
        "available": True,
        "sampled_frames": len(brightness),
        "sampling": "uniform_frames_at_max_320px",
        "motion_magnitude": round(float(np.mean(motion)) if motion else 0, 5),
        "motion_unit": "pixels_per_sample_at_analysis_resolution",
        "scene_cuts": int(scene_cuts),
        "mean_frame_difference": round(float(np.mean(frame_difference)) if frame_difference else 0, 5),
        "mean_brightness": round(float(np.mean(brightness)), 4),
        "max_brightness_jump": round(float(np.max(brightness_jumps)), 5),
        "brightness_jump_unit": "fraction_of_255_luminance_between_sampled_frames",
        "mean_sharpness": round(float(np.mean(sharpness)), 4),
        "sharpness_unit": "laplacian_variance_at_analysis_resolution",
        "limitation": LIMITATION,
    }


def analyze_reference(path: Path) -> dict[str, Any]:
    """Measure reference motion with CPU optical flow, not a human-pose model."""
    result = _sample_metrics(Path(path))
    result["method"] = "OpenCV Farneback optical flow and frame statistics"
    result["pose_estimation_available"] = False
    result["warning"] = (
        "Fluxo óptico mede movimento de pixels, inclusive de câmera; "
        "não extrai esqueleto, expressões ou poses anatômicas."
    )
    return result


def assess_output(path: Path) -> dict[str, Any]:
    """Return measured checks without treating absent AI validators as passing."""
    metadata = _probe(Path(path))
    metrics = _sample_metrics(Path(path))
    checks: list[dict[str, str]] = [{
        "name": "video_decodable",
        "status": "passed",
        "message": "Vídeo decodificável com dimensões, FPS e duração válidos.",
    }]
    if not metrics["available"]:
        checks.append({"name": "visual_metrics", "status": "warning", "message": metrics["reason"]})
    else:
        checks.extend([
            {
                "name": "brightness_continuity",
                "status": "warning" if metrics["max_brightness_jump"] > 0.20 else "passed",
                "message": (
                    "Variação de luminância elevada nas amostras; revise iluminação e cortes."
                    if metrics["max_brightness_jump"] > 0.20
                    else "As amostras não apresentaram saltos elevados de luminância."
                ),
            },
            {
                "name": "scene_continuity",
                "status": "warning" if metrics["scene_cuts"] else "passed",
                "message": (
                    "Foram detectadas mudanças visuais que podem indicar cortes; revise o vídeo."
                    if metrics["scene_cuts"]
                    else "Não foram detectadas mudanças abruptas de histograma nas amostras."
                ),
            },
            {
                "name": "sharpness",
                "status": "warning" if metrics["mean_sharpness"] < 20 else "passed",
                "message": (
                    "A nitidez medida é baixa; cenas uniformes também podem produzir este aviso."
                    if metrics["mean_sharpness"] < 20
                    else "A variância de bordas está acima do limiar de aviso."
                ),
            },
        ])
    checks.append({
        "name": "identity_anatomy_and_consent",
        "status": "warning",
        "message": LIMITATION,
    })
    return {
        "status": "review_required",
        "metadata": metadata,
        "metrics": metrics,
        "checks": checks,
        "automatic_corrections": [],
        "limitation": LIMITATION,
    }
