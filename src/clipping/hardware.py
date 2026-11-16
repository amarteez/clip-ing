"""Detección de hardware (GPU NVIDIA, NVENC) y recomendación de configuración de Whisper.

Toda llamada a procesos externos pasa por una función inyectable `ejecutar`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from .config import TranscripcionCfg

Ejecutar = Callable[[list[str]], tuple[int, str]]


def resolver_ejecutable(nombre: str) -> str | None:
    """Ruta completa del ejecutable. En Windows resuelve también .cmd/.bat (p. ej. claude.cmd
    instalado por npm), que subprocess sin shell no encuentra por sí solo."""
    return shutil.which(nombre)


def ejecutar_proceso(cmd: list[str], timeout: float = 30.0) -> tuple[int, str]:
    """Ejecuta un comando y devuelve (código, salida combinada).

    Si el ejecutable no existe devuelve (127, ""); si excede el timeout, (124, "").
    """
    ruta = resolver_ejecutable(cmd[0])
    if ruta is None:
        return 127, ""
    cmd = [ruta, *cmd[1:]]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 126, ""
    return r.returncode, (r.stdout or "") + (r.stderr or "")


@dataclass
class GPU:
    nombre: str
    vram_mb: int
    driver: str
    compute_cap: str | None = None


def _parsear_gpus(salida: str, con_cap: bool) -> list[GPU]:
    gpus: list[GPU] = []
    n_campos = 4 if con_cap else 3
    for linea in salida.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        partes = [p.strip() for p in linea.rsplit(",", n_campos - 1)]
        if len(partes) != n_campos:
            continue
        m = re.search(r"\d+", partes[1])
        if not m:
            continue
        cap: str | None = None
        if con_cap:
            cap = partes[3] if re.fullmatch(r"\d+\.\d+", partes[3]) else None
        gpus.append(GPU(partes[0], int(m.group()), partes[2], cap))
    return gpus


def detectar_gpus(ejecutar: Ejecutar = ejecutar_proceso) -> list[GPU]:
    """Lista GPUs NVIDIA vía nvidia-smi. Devuelve [] si no hay o la salida es inválida."""
    fmt = "--format=csv,noheader,nounits"
    codigo, salida = ejecutar(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap", fmt]
    )
    if codigo == 127:
        return []
    if codigo == 0:
        gpus = _parsear_gpus(salida, True)
        if gpus:
            return gpus
    # Drivers viejos: sin compute_cap
    codigo, salida = ejecutar(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", fmt])
    if codigo != 0:
        return []
    return _parsear_gpus(salida, False)


_PATRONES_PASCAL = [
    r"GTX\s*10\d\d", r"\bP100\b", r"\bP40\b", r"\bP4\b", r"TITAN\s*X",
]


def es_pascal(gpu: GPU) -> bool:
    if gpu.compute_cap and gpu.compute_cap.strip().startswith("6."):
        return True
    return any(re.search(p, gpu.nombre, re.IGNORECASE) for p in _PATRONES_PASCAL)


@dataclass
class RecomendacionWhisper:
    modelo: str
    dispositivo: str
    compute_type: str
    motivo: str


def recomendar_whisper(gpus: list[GPU]) -> RecomendacionWhisper:
    """Recomienda modelo según la VRAM de la mejor GPU. Nunca float16 (siempre int8)."""
    if not gpus:
        return RecomendacionWhisper(
            "small", "cpu", "int8", "No se detectó GPU NVIDIA: se usa CPU con el modelo small."
        )
    mejor = max(gpus, key=lambda g: g.vram_mb)
    if mejor.vram_mb >= 5500:
        modelo = "medium"
    elif mejor.vram_mb >= 2500:
        modelo = "small"
    else:
        return RecomendacionWhisper(
            "small", "cpu", "int8",
            f"{mejor.nombre} tiene solo {mejor.vram_mb} MB de VRAM (insuficiente): se usa CPU.",
        )
    extra = " (Pascal: sin float16 rápido)" if es_pascal(mejor) else ""
    return RecomendacionWhisper(
        modelo, "cuda", "int8",
        f"{mejor.nombre} con {mejor.vram_mb} MB de VRAM{extra}: modelo {modelo} en int8.",
    )


def resolver_transcripcion(cfg: TranscripcionCfg, gpus: list[GPU]) -> RecomendacionWhisper:
    """Resuelve valores 'auto' con la recomendación y respeta los explícitos."""
    rec = recomendar_whisper(gpus)
    valores = (cfg.modelo, cfg.dispositivo, cfg.compute_type)
    if all(v == "auto" for v in valores):
        return rec
    modelo = rec.modelo if cfg.modelo == "auto" else cfg.modelo
    dispositivo = rec.dispositivo if cfg.dispositivo == "auto" else cfg.dispositivo
    compute = rec.compute_type if cfg.compute_type == "auto" else cfg.compute_type
    partes: list[str] = []
    if "auto" in valores:
        partes.append(rec.motivo)
    partes.append("Valores explícitos de la configuración respetados.")
    if cfg.dispositivo == "cuda" and not gpus:
        dispositivo = "cpu"
        partes.append("dispositivo=cuda solicitado pero no hay GPU NVIDIA: se usa cpu.")
    if dispositivo == "cpu" and compute in ("float16", "int8_float16"):
        compute = "int8"
        partes.append("compute_type ajustado a int8 en cpu.")
    return RecomendacionWhisper(modelo, dispositivo, compute, " ".join(partes))


def nvenc_disponible(ffmpeg: str = "ffmpeg", ejecutar: Ejecutar = ejecutar_proceso) -> bool:
    """True si ffmpeg lista h264_nvenc.

    Estar listado no garantiza que funcione (requiere GPU/driver compatibles);
    para comprobarlo de verdad usar `probar_nvenc`.
    """
    codigo, salida = ejecutar([ffmpeg, "-hide_banner", "-encoders"])
    return codigo == 0 and "h264_nvenc" in salida


def probar_nvenc(ffmpeg: str = "ffmpeg", ejecutar: Ejecutar = ejecutar_proceso) -> bool:
    """Codifica 0.1 s de video negro con h264_nvenc; True si ffmpeg termina con 0."""
    codigo, _ = ejecutar([
        ffmpeg, "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
        "-c:v", "h264_nvenc", "-f", "null", "-",
    ])
    return codigo == 0
