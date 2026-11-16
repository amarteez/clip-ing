"""Transcripción con faster-whisper (import perezoso)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import TranscripcionCfg
from .errores import DependenciaFaltante
from .hardware import RecomendacionWhisper
from .models import Palabra, Segmento, Transcripcion

log = logging.getLogger(__name__)
_dlls_registradas: set[str] = set()


def registrar_dlls_cuda() -> None:
    """En Windows hace visibles las DLL de cuBLAS/cuDNN de los wheels nvidia-*-cu12."""
    if sys.platform != "win32":
        return
    bins: list[str] = []
    for base in sys.path:
        nvidia = Path(base) / "nvidia"
        if nvidia.is_dir():
            bins += [str(p) for p in sorted(nvidia.glob("*/bin")) if p.is_dir()]
    for b in bins:
        if b in _dlls_registradas:
            continue
        _dlls_registradas.add(b)
        try:
            os.add_dll_directory(b)
        except (OSError, AttributeError):
            pass
        partes = os.environ.get("PATH", "").split(os.pathsep)
        if b not in partes:
            os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def convertir_whisper(
    segmentos_iterable: Iterable[Any],
    idioma: str,
    duracion: float,
    modelo: str,
    progreso: Callable[[float, float], None] | None = None,
) -> Transcripcion:
    """Convierte segmentos de faster-whisper (o equivalentes) en una Transcripcion."""
    segs: list[Segmento] = []
    for s in segmentos_iterable:
        palabras = [
            Palabra(
                texto=str(w.word).strip(),
                inicio=float(w.start),
                fin=float(w.end),
                prob=float(getattr(w, "probability", 1.0)),
            )
            for w in (getattr(s, "words", None) or [])
            if str(w.word).strip()
        ]
        segs.append(Segmento(float(s.start), float(s.end), str(s.text).strip(), palabras))
        if progreso:
            progreso(float(s.end), duracion)
    return Transcripcion(idioma=idioma, duracion=duracion, segmentos=segs, modelo=modelo)


def _es_error_cuda(e: BaseException) -> bool:
    m = str(e).lower()
    return any(k in m for k in ("cuda", "cublas", "cudnn", "cudart", "nvidia", "gpu"))


def _transcribir_una_vez(
    video: Path,
    modelo: str,
    dispositivo: str,
    compute: str,
    cfg: TranscripcionCfg,
    progreso: Callable[[float, float], None] | None,
) -> Transcripcion:
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError as e:
        raise DependenciaFaltante("Falta faster-whisper: ejecuta .\\setup.ps1") from e
    model = WhisperModel(modelo, device=dispositivo, compute_type=compute)
    segmentos, info = model.transcribe(
        str(video),
        language=cfg.idioma,
        beam_size=cfg.beam_size,
        word_timestamps=True,
        vad_filter=cfg.vad,
    )
    return convertir_whisper(segmentos, info.language, info.duration, modelo, progreso)


def transcribir(
    video: Path,
    rec: RecomendacionWhisper,
    cfg: TranscripcionCfg,
    progreso: Callable[[float, float], None] | None = None,
) -> Transcripcion:
    if rec.dispositivo == "cuda":
        registrar_dlls_cuda()
    try:
        return _transcribir_una_vez(
            video, rec.modelo, rec.dispositivo, rec.compute_type, cfg, progreso
        )
    except (RuntimeError, OSError) as e:
        if isinstance(e, DependenciaFaltante) or rec.dispositivo != "cuda" or not _es_error_cuda(e):
            raise
        # En el i5 medium/large en CPU es varias veces más lento que tiempo real: bajar a small.
        modelo_cpu = "small" if rec.modelo.startswith(("medium", "large")) else rec.modelo
        log.warning("Falló CUDA (%s); reintentando en cpu/int8 con %s (más lento).", e, modelo_cpu)
        return _transcribir_una_vez(video, modelo_cpu, "cpu", "int8", cfg, progreso)
