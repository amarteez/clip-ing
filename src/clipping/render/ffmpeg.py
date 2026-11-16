"""Construcción de comandos ffmpeg (no ejecuta nada)."""

from __future__ import annotations

from pathlib import Path

from clipping.config import RenderCfg
from clipping.render.reencuadre import construir_filtro


def ruta_filtro_ass(ruta: Path) -> str:
    """Escapa una ruta (Windows incluida) para el filtro subtitles= de ffmpeg."""
    r = str(ruta).replace("\\", "/")
    r = r.replace(":", "\\:").replace("'", "'\\\\\\''")
    return f"subtitles='{r}'"


def elegir_encoder(cfg_encoder: str, nvenc_disponible: bool) -> str:
    """Devuelve el encoder que realmente se usará."""
    if cfg_encoder == "auto":
        return "h264_nvenc" if nvenc_disponible else "libx264"
    if cfg_encoder == "h264_nvenc" and not nvenc_disponible:
        return "libx264"
    return cfg_encoder


def construir_comando_clip(
    *,
    entrada: Path,
    salida: Path,
    inicio: float,
    fin: float,
    ass: Path | None,
    cfg: RenderCfg,
    encoder: str,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    dur = max(0.0, fin - inicio)
    grafo = construir_filtro(cfg.reencuadre, cfg.ancho, cfg.alto, cfg.blur_sigma)
    if ass is not None:
        grafo += f";[v0]{ruta_filtro_ass(ass)},fps={cfg.fps}[v]"
    else:
        grafo += f";[v0]fps={cfg.fps}[v]"

    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{inicio:.3f}", "-i", str(entrada), "-t", f"{dur:.3f}",
        "-filter_complex", grafo,
        "-map", "[v]", "-map", "0:a?",
    ]
    if encoder == "h264_nvenc":
        cmd += [
            "-c:v", "h264_nvenc", "-preset", cfg.preset_nvenc, "-rc", "vbr",
            "-cq", str(cfg.cq), "-b:v", "0", "-pix_fmt", "yuv420p",
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-preset", cfg.preset_x264, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p",
        ]
    cmd += [
        "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000",
        "-movflags", "+faststart", str(salida),
    ]
    return cmd


def comando_a_texto(cmd: list[str]) -> str:
    """Representación legible estilo PowerShell."""

    def q(a: str) -> str:
        if a == "" or any(c in a for c in " \t;[]()&$`\"'"):
            return "'" + a.replace("'", "''") + "'"
        return a

    return " ".join(q(str(a)) for a in cmd)
