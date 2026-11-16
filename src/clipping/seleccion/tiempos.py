"""Utilidades puras de manejo de tiempos para candidatos (snaps, límites, solapes)."""

from __future__ import annotations

import dataclasses
import re

from clipping.models import Candidato, Escena, Palabra

_EPS = 1e-9


def _snap_inicio_palabra(t: float, palabras: list[Palabra], tol: float) -> float:
    for p in palabras:
        if p.inicio < t < p.fin:
            return p.inicio  # no cortar una palabra a la mitad
    mejor = None
    for p in palabras:
        d = abs(p.inicio - t)
        if d <= tol + _EPS and (mejor is None or d < abs(mejor - t)):
            mejor = p.inicio
    return t if mejor is None else mejor


def _snap_fin_palabra(t: float, palabras: list[Palabra], tol: float) -> float:
    for p in palabras:
        if p.inicio < t < p.fin:
            return p.fin
    mejor = None
    for p in palabras:
        d = abs(p.fin - t)
        if d <= tol + _EPS and (mejor is None or d < abs(mejor - t)):
            mejor = p.fin
    return t if mejor is None else mejor


def _validar_par(
    original: tuple[float, float], nuevo_i: float, nuevo_f: float
) -> tuple[float, float]:
    """Si el snap dejó un intervalo inválido, revierte lo mínimo necesario."""
    inicio, fin = original
    if nuevo_f <= nuevo_i:
        nuevo_f = fin
        if nuevo_f <= nuevo_i:
            nuevo_i = inicio
    return nuevo_i, nuevo_f


def snap_a_palabras(
    inicio: float, fin: float, palabras: list[Palabra], tolerancia: float = 1.5
) -> tuple[float, float]:
    """Alinea inicio al comienzo de palabra y fin al final de palabra (±tolerancia)."""
    if not palabras:
        return inicio, fin
    ni = _snap_inicio_palabra(inicio, palabras, tolerancia)
    nf = _snap_fin_palabra(fin, palabras, tolerancia)
    return _validar_par((inicio, fin), ni, nf)


def _corte_cercano(t: float, cortes: list[float], tol: float) -> float:
    mejor = None
    for c in cortes:
        d = abs(c - t)
        if d <= tol + _EPS and (mejor is None or d < abs(mejor - t)):
            mejor = c
    return t if mejor is None else mejor


def snap_a_escenas(
    inicio: float, fin: float, escenas: list[Escena], tolerancia: float = 1.0
) -> tuple[float, float]:
    """Alinea inicio/fin al corte de escena más cercano si está a <= tolerancia."""
    cortes = [e.inicio for e in escenas if e.inicio > 0]
    if not cortes:
        return inicio, fin
    return _validar_par(
        (inicio, fin),
        _corte_cercano(inicio, cortes, tolerancia),
        _corte_cercano(fin, cortes, tolerancia),
    )


def ajustar_duracion(
    inicio: float, fin: float, min_seg: float, max_seg: float, duracion_total: float
) -> tuple[float, float]:
    """Fuerza min_seg <= duración <= max_seg dentro de [0, duracion_total]."""
    if duracion_total < min_seg:
        return 0.0, duracion_total
    inicio = max(0.0, inicio)
    fin = min(duracion_total, fin)
    if fin < inicio:
        fin = inicio
    dur = fin - inicio
    if dur < min_seg:
        falta = min_seg - dur
        inicio -= falta / 2
        fin += falta / 2
        if inicio < 0:
            fin += -inicio
            inicio = 0.0
        if fin > duracion_total:
            inicio -= fin - duracion_total
            fin = duracion_total
        inicio = max(0.0, inicio)
    elif dur > max_seg:
        fin = inicio + max_seg
    return inicio, fin


def aplicar_padding(
    inicio: float, fin: float, padding: float, duracion_total: float
) -> tuple[float, float]:
    """Extiende ambos extremos `padding` segundos, limitado a [0, duracion_total]."""
    return max(0.0, inicio - padding), min(duracion_total, fin + padding)


def quitar_solapes(candidatos: list[Candidato], separacion_min: float) -> list[Candidato]:
    """Descarta candidatos que solapan (o distan < separacion_min) de uno mejor ya aceptado."""
    aceptados: list[Candidato] = []
    for c in sorted(candidatos, key=lambda x: -x.puntaje):  # sort estable
        if all(
            c.inicio >= a.fin + separacion_min - _EPS or c.fin <= a.inicio - separacion_min + _EPS
            for a in aceptados
        ):
            aceptados.append(c)
    return aceptados


def normalizar_candidato(
    c: Candidato,
    *,
    palabras: list[Palabra],
    escenas: list[Escena],
    min_seg: float,
    max_seg: float,
    padding: float,
    duracion_total: float,
) -> Candidato:
    """Pipeline: snap escenas, snap palabras, padding, ajuste de duración y redondeo."""
    inicio, fin = c.inicio, c.fin
    inicio, fin = snap_a_escenas(inicio, fin, escenas)
    inicio, fin = snap_a_palabras(inicio, fin, palabras)
    inicio, fin = aplicar_padding(inicio, fin, padding, duracion_total)
    inicio, fin = ajustar_duracion(inicio, fin, min_seg, max_seg, duracion_total)
    inicio, fin = round(inicio, 3), round(fin, 3)
    if duracion_total >= min_seg:
        # el redondeo puede romper los límites por 1 ms
        if fin - inicio > max_seg + _EPS:
            fin = round(inicio + max_seg, 3)
        elif fin - inicio < min_seg - _EPS:
            fin = round(inicio + min_seg, 3)
            if fin > duracion_total:
                fin = round(duracion_total, 3)
                inicio = round(fin - min_seg, 3)
    return dataclasses.replace(c, inicio=inicio, fin=fin)


def formatear_tiempo(seg: float) -> str:
    """Segundos -> 'HH:MM:SS.mmm'."""
    ms_tot = int(round(max(0.0, seg) * 1000))
    h, resto = divmod(ms_tot, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


_RE_ENTERO = re.compile(r"^\d+$")
_RE_DECIMAL = re.compile(r"^\d+(\.\d+)?$")


def parsear_tiempo(texto: str) -> float:
    """Acepta 'SS', 'MM:SS' o 'HH:MM:SS' (con decimales opcionales en los segundos)."""
    if not isinstance(texto, str):
        raise ValueError(f"Tiempo inválido: {texto!r}")
    partes = texto.strip().split(":")
    if not 1 <= len(partes) <= 3:
        raise ValueError(f"Tiempo inválido: {texto!r}")
    if not _RE_DECIMAL.match(partes[-1]) or not all(_RE_ENTERO.match(p) for p in partes[:-1]):
        raise ValueError(f"Tiempo inválido: {texto!r}")
    total = 0.0
    for p in partes[:-1]:
        total = total * 60 + int(p)
    return total * 60 + float(partes[-1]) if len(partes) > 1 else float(partes[-1])
