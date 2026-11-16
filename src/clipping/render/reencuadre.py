"""Filtros ffmpeg para reencuadrar video horizontal a vertical 9:16."""

from __future__ import annotations

# TODO fase 2: seguimiento de rostro/acción (crop dinámico en vez de centro fijo).


def filtro_centro(ancho: int, alto: int) -> str:
    """Escala para cubrir y recorta al centro."""
    return (
        f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,"
        f"crop={ancho}:{alto},setsar=1"
    )


def filtro_blur(ancho: int, alto: int, sigma: float) -> str:
    """filter_complex: fondo desenfocado a cubrir + primer plano completo centrado.

    El fondo se desenfoca a 1/4 de resolución y luego se reescala: mismo aspecto
    visual y ~10x más barato en CPU (importante con libx264 en un i5).
    """
    w4, h4 = (ancho // 4) // 2 * 2, (alto // 4) // 2 * 2
    sigma4 = max(1.0, sigma / 4)
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={w4}:{h4}:force_original_aspect_ratio=increase,"
        f"crop={w4}:{h4},gblur=sigma={sigma4:g},scale={ancho}:{alto},"
        f"eq=brightness=-0.08[bgb];"
        f"[fg]scale={ancho}:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]"
    )


def construir_filtro(modo: str, ancho: int, alto: int, sigma: float) -> str:
    """Grafo completo de entrada [0:v] y salida [v0]."""
    if modo == "centro":
        return f"[0:v]{filtro_centro(ancho, alto)}[v0]"
    if modo == "blur":
        return filtro_blur(ancho, alto, sigma)
    raise ValueError(f"Modo de reencuadre desconocido: {modo!r}")
