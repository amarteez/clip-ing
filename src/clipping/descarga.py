"""Obtención del video fuente: archivo local o URL (yt-dlp).

Usar la descarga solo con contenido propio o con permiso del titular.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .errores import DependenciaFaltante, ErrorFFmpeg
from .hardware import ejecutar_proceso

_FORMATO = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b"


def es_url(s: str) -> bool:
    return s.strip().lower().startswith(("http://", "https://"))


def obtener_fuente(
    fuente: str, proyecto_dir: Path, *, copiar: bool = False, cookies: str | None = None
) -> tuple[str, str]:
    """Devuelve (archivo, titulo).

    Local sin copiar: ruta absoluta del original. Local con copiar o URL: nombre relativo
    dentro de proyecto_dir.
    """
    proyecto_dir = Path(proyecto_dir)
    if not es_url(fuente):
        origen = Path(fuente).expanduser()
        if not origen.is_file():
            raise FileNotFoundError(f"No existe el archivo de video: {origen}")
        if not copiar:
            return str(origen.resolve()), origen.stem
        proyecto_dir.mkdir(parents=True, exist_ok=True)
        nombre = "fuente" + origen.suffix
        shutil.copy2(origen, proyecto_dir / nombre)
        return nombre, origen.stem

    try:
        from yt_dlp import YoutubeDL  # type: ignore[import-not-found]
    except ImportError as e:
        raise DependenciaFaltante("Falta yt-dlp: ejecuta .\\setup.ps1") from e

    proyecto_dir.mkdir(parents=True, exist_ok=True)
    opts: dict = {
        "format": _FORMATO,
        "merge_output_format": "mp4",
        "outtmpl": str(proyecto_dir / "fuente.%(ext)s"),
        "noplaylist": True,
    }
    if cookies:
        opts["cookiefile"] = cookies
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(fuente, download=True)
        titulo = str(info.get("title") or "")
    candidatos = [
        c for c in sorted(proyecto_dir.glob("fuente.*")) if c.suffix not in (".part", ".ytdl")
    ]
    if not candidatos:
        raise FileNotFoundError("yt-dlp terminó pero no se encontró el archivo descargado")
    mp4 = [c for c in candidatos if c.suffix == ".mp4"]
    return (mp4 or candidatos)[0].name, titulo


def duracion_video(ruta: Path, ffprobe: str = "ffprobe", ejecutar=ejecutar_proceso) -> float:
    codigo, salida = ejecutar([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(ruta),
    ])
    if codigo != 0:
        raise ErrorFFmpeg(f"ffprobe falló (código {codigo}) al leer {ruta}: {salida.strip()}")
    try:
        return float(salida.strip().splitlines()[0])
    except (ValueError, IndexError) as e:
        raise ErrorFFmpeg(f"ffprobe devolvió una duración inválida: {salida!r}") from e
