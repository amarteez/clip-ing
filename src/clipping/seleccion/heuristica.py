"""Selección heurística de candidatos (fallback sin IA): volumen, habla y cortes de escena."""

from __future__ import annotations

import math

from clipping.config import SeleccionCfg
from clipping.models import Candidato, Escena, Palabra
from clipping.seleccion.tiempos import normalizar_candidato, quitar_solapes

_VENTANA_FONDO = 30  # segundos de media móvil para el "fondo" de volumen
_RADIO_ESCENAS = 3  # ± segundos para suavizar cortes de escena


def _n_bins(duracion: float, paso: float) -> int:
    return max(0, math.ceil(duracion / paso - 1e-9))


def serie_densidad_palabras(
    palabras: list[Palabra], duracion: float, paso: float = 1.0
) -> list[float]:
    """Palabras por segundo en ventanas de `paso` (cada palabra cuenta en el bin de su centro)."""
    n = _n_bins(duracion, paso)
    cuentas = [0.0] * n
    for p in palabras:
        b = int(((p.inicio + p.fin) / 2) / paso)
        if 0 <= b < n:
            cuentas[b] += 1.0
    return [c / paso for c in cuentas]


def serie_escenas(escenas: list[Escena], duracion: float, paso: float = 1.0) -> list[float]:
    """1.0 en el bin de cada corte de escena (excepto t=0), 0.0 en el resto."""
    n = _n_bins(duracion, paso)
    serie = [0.0] * n
    for e in escenas:
        if e.inicio <= 0:
            continue
        b = int(e.inicio / paso)
        if 0 <= b < n:
            serie[b] = 1.0
    return serie


def normalizar(serie: list[float]) -> list[float]:
    """Min-max a [0, 1]; serie vacía o constante -> ceros."""
    if not serie:
        return []
    lo, hi = min(serie), max(serie)
    if hi - lo <= 1e-12:
        return [0.0] * len(serie)
    return [(x - lo) / (hi - lo) for x in serie]


def _remuestrear_rms(rms: list[float] | None, paso_rms: float, n: int) -> list[float]:
    """Lleva el rms a bins de 1 s (promedio por bin; si paso_rms > 1 repite la muestra)."""
    if not rms or n == 0 or paso_rms <= 0:
        return [0.0] * n
    sumas = [0.0] * n
    cuentas = [0] * n
    for i, v in enumerate(rms):
        b = int(i * paso_rms)
        if b >= n:
            break
        sumas[b] += v
        cuentas[b] += 1
    out = []
    for b in range(n):
        if cuentas[b]:
            out.append(sumas[b] / cuentas[b])
        else:
            i = min(int(b / paso_rms), len(rms) - 1)
            out.append(rms[i])
    return out


def _picos_volumen(rms_bins: list[float]) -> list[float]:
    """Volumen normalizado menos su media móvil de 30 s (>= 0), renormalizado."""
    vol = normalizar(rms_bins)
    n = len(vol)
    pref = [0.0]
    for v in vol:
        pref.append(pref[-1] + v)
    r = _VENTANA_FONDO // 2
    picos = []
    for i in range(n):
        a, b = max(0, i - r), min(n, i + r + 1)
        media = (pref[b] - pref[a]) / (b - a)
        picos.append(max(0.0, vol[i] - media))
    return normalizar(picos)


def _suavizar_escenas(esc: list[float]) -> list[float]:
    n = len(esc)
    pref = [0.0]
    for v in esc:
        pref.append(pref[-1] + v)
    return normalizar(
        [pref[min(n, i + _RADIO_ESCENAS + 1)] - pref[max(0, i - _RADIO_ESCENAS)] for i in range(n)]
    )


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _razon(aporte: dict[str, float], vol_max: float, palabras_s: float, cortes: int) -> str:
    dominante = max(aporte, key=lambda k: (aporte[k], k == "volumen"))
    cortes_txt = _plural(cortes, "corte de escena", "cortes de escena")
    if dominante == "volumen":
        return (
            f"Pico de volumen fuerte ({vol_max:.2f}) con {palabras_s:.1f} palabras/s "
            f"y {cortes_txt}"
        )
    if dominante == "palabras":
        return (
            f"Alta densidad de habla ({palabras_s:.1f} palabras/s) con volumen "
            f"{vol_max:.2f} y {cortes_txt}"
        )
    return (
        f"Montaje dinámico ({cortes_txt}) con {palabras_s:.1f} palabras/s "
        f"y volumen {vol_max:.2f}"
    )


def seleccionar(
    duracion: float,
    *,
    rms: list[float] | None,
    paso_rms: float,
    palabras: list[Palabra],
    escenas: list[Escena],
    cfg: SeleccionCfg,
    n: int | None = None,
) -> list[Candidato]:
    """Elige los mejores clips combinando picos de volumen, densidad de habla y cortes."""
    if duracion <= 0 or not (rms or palabras or escenas):
        return []
    n = cfg.n if n is None else n
    if n <= 0:
        return []
    nb = _n_bins(duracion, 1.0)
    if nb == 0:
        return []

    vol = _picos_volumen(_remuestrear_rms(rms, paso_rms, nb))
    dens_raw = serie_densidad_palabras(palabras, duracion, 1.0)
    dens = normalizar(dens_raw)
    esc_raw = serie_escenas(escenas, duracion, 1.0)
    esc = _suavizar_escenas(esc_raw)

    w = cfg.pesos
    total_w = w.volumen + w.palabras + w.escenas
    if total_w <= 0:
        return []
    puntaje_bin = [
        (w.volumen * vol[i] + w.palabras * dens[i] + w.escenas * esc[i]) / total_w
        for i in range(nb)
    ]

    largo = max(1, min(nb, int(round(cfg.objetivo_seg))))
    ventanas: list[tuple[float, int]] = []
    for s in range(0, nb - largo + 1):
        trozo = puntaje_bin[s : s + largo]
        p = 0.6 * (sum(trozo) / largo) + 0.4 * max(trozo)
        ventanas.append((min(1.0, max(0.0, p)), s))
    ventanas.sort(key=lambda t: (-t[0], t[1]))  # desempate determinista: más temprano

    elegidas: list[tuple[float, int]] = []
    for p, s in ventanas:
        if len(elegidas) >= n:
            break
        if all(
            s >= a + largo + cfg.separacion_min_seg or s + largo + cfg.separacion_min_seg <= a
            for _, a in elegidas
        ):
            elegidas.append((p, s))

    cands: list[Candidato] = []
    for k, (p, s) in enumerate(elegidas, start=1):
        e = s + largo
        vol_w, dens_w, esc_w = vol[s:e], dens[s:e], esc[s:e]
        aporte = {
            "volumen": w.volumen * sum(vol_w) / largo,
            "palabras": w.palabras * sum(dens_w) / largo,
            "escenas": w.escenas * sum(esc_w) / largo,
        }
        cortes = int(sum(esc_raw[s:e]))
        c = Candidato(
            id=f"c{k:02d}",
            inicio=float(s),
            fin=float(min(e, duracion)),
            puntaje=round(p, 3),
            razon=_razon(aporte, max(vol_w), sum(dens_raw[s:e]) / largo, cortes),
            titulo="",
            origen="heuristica",
        )
        cands.append(
            normalizar_candidato(
                c,
                palabras=palabras,
                escenas=escenas,
                min_seg=cfg.min_seg,
                max_seg=cfg.max_seg,
                padding=cfg.padding_seg,
                duracion_total=duracion,
            )
        )

    final = quitar_solapes(cands, cfg.separacion_min_seg)
    for k, c in enumerate(final, start=1):
        c.id = f"c{k:02d}"
    return final
