"""Serie de volumen (RMS en dBFS) vía ffmpeg en streaming, sin numpy."""

from __future__ import annotations

import math
import subprocess
import tempfile
from array import array
from pathlib import Path
from typing import Sequence

from clipping.errores import ErrorFFmpeg
from clipping.hardware import resolver_ejecutable

# 8 kHz basta para medir volumen y reduce a la mitad el trabajo en Python puro
# (un stream de 8 h ≈ 230 M muestras).
_SR = 8000
_PISO_DB = -90.0


def rms_dbfs(muestras: Sequence[int]) -> float:
    """RMS en dBFS de muestras int16 (0 dBFS = onda cuadrada a fondo de escala); mínimo -90."""
    if not muestras:
        return _PISO_DB
    media = sum(m * m for m in muestras) / len(muestras)
    if media <= 0:
        return _PISO_DB
    return max(_PISO_DB, 20 * math.log10(math.sqrt(media) / 32768.0))


def serie_rms(video: Path, paso: float = 0.5, ffmpeg: str = "ffmpeg") -> list[float]:
    ruta = resolver_ejecutable(ffmpeg)
    if ruta is None:
        raise ErrorFFmpeg(f"No se encontró {ffmpeg} en el PATH")
    cmd = [
        ruta, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(_SR),
        "-f", "s16le", "-",
    ]
    ventana = max(1, int(round(paso * _SR)))
    serie: list[float] = []
    pendiente = array("h")
    resto = b""
    # stderr a archivo temporal: si fuera PIPE sin leer, un video corrupto con muchos
    # errores llenaría el buffer y bloquearía a ffmpeg (deadlock).
    err_f = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_f)
    assert proc.stdout is not None
    try:
        while True:
            bloque = proc.stdout.read(1 << 20)
            if not bloque:
                break
            datos = resto + bloque
            util = len(datos) - (len(datos) % 2)
            resto = datos[util:]
            nuevos = array("h")
            nuevos.frombytes(datos[:util])  # little-endian (Windows/x86)
            pendiente.extend(nuevos)
            n = len(pendiente) // ventana
            for i in range(n):
                serie.append(rms_dbfs(pendiente[i * ventana : (i + 1) * ventana]))
            del pendiente[: n * ventana]
        if len(pendiente) >= ventana // 2:
            serie.append(rms_dbfs(pendiente))
        codigo = proc.wait()
        err_f.seek(0)
        err = err_f.read().decode("utf-8", errors="replace")
    finally:
        if proc.poll() is None:
            proc.kill()
        err_f.close()
    if codigo != 0:
        raise ErrorFFmpeg(f"ffmpeg falló (código {codigo}): {err.strip()[-500:]}")
    return serie
