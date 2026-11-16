"""Detección de cortes de escena con PySceneDetect (import perezoso)."""

from __future__ import annotations

from pathlib import Path

from clipping.errores import DependenciaFaltante
from clipping.models import Escena


def detectar_escenas(
    video: Path, umbral: float = 27.0, frame_skip: int | None = None
) -> list[Escena]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video  # type: ignore
    except ImportError as e:
        raise DependenciaFaltante("Falta scenedetect: ejecuta .\\setup.ps1") from e
    vid = open_video(str(video))
    duracion = vid.duration.get_seconds()
    if frame_skip is None:
        frame_skip = 0 if duracion < 30 * 60 else 2
    sm = SceneManager()
    sm.auto_downscale = True
    sm.add_detector(ContentDetector(threshold=umbral))
    sm.detect_scenes(vid, frame_skip=frame_skip)
    escenas = [Escena(ini.get_seconds(), fin.get_seconds()) for ini, fin in sm.get_scene_list()]
    return escenas or [Escena(0.0, duracion)]
