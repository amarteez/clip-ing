"""Diagnóstico del entorno: herramientas, GPU, espacio y configuración recomendada."""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, Literal

from .config import Config
from .hardware import (
    Ejecutar,
    RecomendacionWhisper,
    detectar_gpus,
    ejecutar_proceso,
    es_pascal,
    nvenc_disponible,
    probar_nvenc,
    resolver_transcripcion,
)

Estado = Literal["ok", "aviso", "error"]


@dataclass
class Chequeo:
    nombre: str
    estado: Estado
    detalle: str
    sugerencia: str = ""


def _version(salida: str) -> str:
    m = re.search(r"version\s+(\S+)", salida, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\d+(?:\.\d+)+", salida)
    return m.group(0) if m else (salida.strip().splitlines() or ["?"])[0]


def _chequeo_python(version: tuple[int, int, int]) -> Chequeo:
    v = ".".join(map(str, version))
    if version < (3, 11):
        return Chequeo("Python", "error", f"Python {v} (se requiere >= 3.11)",
                       "Instala Python 3.11: winget install Python.Python.3.11")
    if version >= (3, 12):
        return Chequeo("Python", "aviso", f"Python {v}: el objetivo es 3.11 pero funciona")
    return Chequeo("Python", "ok", f"Python {v}")


def _chequeo_binario(nombre: str, cmd: list[str], ejecutar: Ejecutar, sug: str) -> Chequeo:
    codigo, salida = ejecutar(cmd)
    if codigo != 0:
        return Chequeo(nombre, "error", "no encontrado o no responde", sug)
    return Chequeo(nombre, "ok", f"versión {_version(salida)}")


def _modulo(nombre: str) -> bool:
    try:
        return importlib.util.find_spec(nombre) is not None
    except (ImportError, ValueError):
        return False


def _ram_mb() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = _MemStatus()
        st.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return None
        return int(st.ullTotalPhys // (1024 * 1024))
    except Exception:
        return None


def _cuda_ctranslate2() -> Chequeo:
    if not _modulo("ctranslate2"):
        return Chequeo("ctranslate2 CUDA", "aviso", "ctranslate2 no instalado",
                       "Ejecuta .\\setup.ps1 (instala faster-whisper, que incluye ctranslate2)")
    try:
        import ctranslate2  # type: ignore[import-not-found]

        n = int(ctranslate2.get_cuda_device_count())
    except Exception as e:  # noqa: BLE001
        return Chequeo("ctranslate2 CUDA", "aviso", f"no se pudo consultar CUDA ({e})",
                       "Se usará CPU; revisa drivers NVIDIA y cuBLAS/cuDNN")
    if n > 0:
        return Chequeo("ctranslate2 CUDA", "ok", f"{n} dispositivo(s) CUDA visibles")
    return Chequeo("ctranslate2 CUDA", "aviso", "sin dispositivos CUDA visibles; se usará CPU",
                   "Instala el driver NVIDIA reciente y las DLL cuBLAS/cuDNN (ver setup.ps1)")


def ejecutar_doctor(
    cfg: Config,
    *,
    ejecutar: Ejecutar = ejecutar_proceso,
    disco_ruta: str = ".",
    probar_encoder: bool = True,
    version_python: tuple[int, int, int] | None = None,
    uso_disco: Callable[[str], tuple[int, int, int]] = shutil.disk_usage,
) -> tuple[list[Chequeo], RecomendacionWhisper]:
    chequeos: list[Chequeo] = []
    vp = version_python or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    chequeos.append(_chequeo_python(vp))

    sug_ff = "winget install Gyan.FFmpeg (luego reabre la terminal)"
    chequeos.append(_chequeo_binario("ffmpeg", ["ffmpeg", "-version"], ejecutar, sug_ff))
    chequeos.append(_chequeo_binario("ffprobe", ["ffprobe", "-version"], ejecutar, sug_ff))
    ffmpeg_ok = chequeos[-2].estado == "ok"

    gpus = detectar_gpus(ejecutar)
    if gpus:
        for g in gpus:
            det = f"{g.nombre}, {g.vram_mb} MB VRAM, driver {g.driver}"
            if g.compute_cap:
                det += f", cc {g.compute_cap}"
            if es_pascal(g):
                det += " (Pascal: sin float16, se usa int8)"
            chequeos.append(Chequeo("GPU NVIDIA", "ok", det))
    else:
        chequeos.append(Chequeo(
            "GPU NVIDIA", "aviso", "no detectada (nvidia-smi ausente o sin GPU)",
            "Instala/actualiza el driver NVIDIA; sin GPU todo funciona en CPU, más lento"))

    # NVENC
    if not ffmpeg_ok:
        chequeos.append(Chequeo("NVENC", "aviso", "no verificable sin ffmpeg", sug_ff))
    elif not nvenc_disponible("ffmpeg", ejecutar):
        chequeos.append(Chequeo("NVENC", "aviso", "h264_nvenc no listado en ffmpeg",
                                "Usa un build completo: winget install Gyan.FFmpeg; se usará libx264"))
    elif probar_encoder:
        if probar_nvenc("ffmpeg", ejecutar):
            chequeos.append(Chequeo("NVENC", "ok", "h264_nvenc listado y prueba real exitosa"))
        else:
            chequeos.append(Chequeo("NVENC", "aviso", "h264_nvenc listado pero la prueba real falló",
                                    "Actualiza el driver NVIDIA; se usará libx264"))
    else:
        chequeos.append(Chequeo("NVENC", "ok", "h264_nvenc listado (sin prueba real)"))

    if _modulo("faster_whisper"):
        chequeos.append(Chequeo("faster-whisper", "ok", "instalado"))
    else:
        chequeos.append(Chequeo("faster-whisper", "error", "no instalado",
                                "Ejecuta .\\setup.ps1 o: pip install faster-whisper"))
    chequeos.append(_cuda_ctranslate2())

    if _modulo("yt_dlp"):
        chequeos.append(Chequeo("yt-dlp", "ok", "módulo instalado"))
    else:
        c, s = ejecutar(["yt-dlp", "--version"])
        if c == 0:
            chequeos.append(Chequeo("yt-dlp", "ok", f"ejecutable versión {s.strip()}"))
        else:
            chequeos.append(Chequeo("yt-dlp", "aviso", "no instalado (solo afecta a URLs)",
                                    "Ejecuta .\\setup.ps1 o: pip install yt-dlp"))

    if _modulo("scenedetect"):
        chequeos.append(Chequeo("scenedetect", "ok", "instalado"))
    else:
        chequeos.append(Chequeo("scenedetect", "aviso", "no instalado (sin detección de escenas)",
                                "Ejecuta .\\setup.ps1 o: pip install scenedetect"))

    cmd_claude = cfg.claude.comando
    c, s = ejecutar([cmd_claude, "--version"])
    if c == 0:
        chequeos.append(Chequeo("claude CLI", "ok", f"versión {_version(s)}"))
    else:
        chequeos.append(Chequeo("claude CLI", "aviso",
                                "no encontrado: se usará la heurística (sin IA)",
                                "Instala Claude Code y ejecuta 'claude' para iniciar sesión"))

    try:
        libre_gb = uso_disco(disco_ruta)[2] / 1024**3
        det = f"{libre_gb:.1f} GB libres"
        if libre_gb < 20:
            chequeos.append(Chequeo("Espacio en disco", "error", det,
                                    "Libera espacio: se necesitan al menos 20 GB"))
        elif libre_gb < 50:
            chequeos.append(Chequeo("Espacio en disco", "aviso", det,
                                    "Recomendado >= 50 GB para videos largos"))
        else:
            chequeos.append(Chequeo("Espacio en disco", "ok", det))
    except OSError as e:
        chequeos.append(Chequeo("Espacio en disco", "aviso", f"no se pudo medir ({e})"))

    ram = _ram_mb()
    if ram is not None:
        det = f"{ram / 1024:.1f} GB"
        if ram < 8000:
            chequeos.append(Chequeo("RAM", "aviso", det, "Se recomiendan >= 16 GB"))
        else:
            chequeos.append(Chequeo("RAM", "ok", det))

    rec = resolver_transcripcion(cfg.transcripcion, gpus)
    return chequeos, rec


_ICONOS = {"ok": "[OK]", "aviso": "[!!]", "error": "[XX]"}


def formatear_reporte(chequeos: list[Chequeo], recomendacion: RecomendacionWhisper) -> str:
    ancho = max((len(c.nombre) for c in chequeos), default=10)
    lineas = ["Diagnóstico del entorno", "=" * 23]
    for c in chequeos:
        lineas.append(f"{_ICONOS[c.estado]} {c.nombre.ljust(ancho)}  {c.detalle}")
        if c.sugerencia and c.estado != "ok":
            lineas.append(f"     {' ' * ancho}  -> {c.sugerencia}")
    gpu_nvenc = next((c for c in chequeos if c.nombre == "NVENC"), None)
    encoder = "h264_nvenc" if gpu_nvenc and gpu_nvenc.estado == "ok" else "libx264"
    lineas += [
        "",
        "Configuración recomendada",
        "-------------------------",
        f"# {recomendacion.motivo}",
        "transcripcion:",
        f"  modelo: {recomendacion.modelo}",
        f"  dispositivo: {recomendacion.dispositivo}",
        f"  compute_type: {recomendacion.compute_type}",
        "render:",
        f"  encoder: {encoder}",
    ]
    return "\n".join(lineas)
