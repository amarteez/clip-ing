"""Títulos simples sin IA."""

from __future__ import annotations

import re


def titulo_simple(texto: str, max_chars: int = 60) -> str:
    """Primera frase con sentido (>= 3 palabras si es posible), capitalizada y recortada."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if not texto:
        return ""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    frase = next((f for f in frases if len(f.split()) >= 3), frases[0])
    frase = frase.strip(" ,;:-¿¡").rstrip(".")
    if not frase:
        return ""
    frase = frase[0].upper() + frase[1:]
    if len(frase) <= max_chars:
        return frase
    corte = frase[: max_chars - 1]
    if " " in corte and frase[max_chars - 1] != " ":
        corte = corte.rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:.-") + "…"
