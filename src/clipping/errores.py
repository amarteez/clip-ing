"""Excepciones compartidas del motor."""

from __future__ import annotations


class DependenciaFaltante(RuntimeError):
    """Una dependencia pesada (yt-dlp, faster-whisper, scenedetect...) no está instalada."""


class ErrorClaude(RuntimeError):
    """Fallo al usar `claude -p` (no instalado, timeout, error o respuesta inutilizable)."""


class ErrorFFmpeg(RuntimeError):
    """Fallo al ejecutar ffmpeg/ffprobe."""
