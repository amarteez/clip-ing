"""Búsqueda por texto sin IA: ventanas deslizantes sobre las palabras."""

from __future__ import annotations

import re
import unicodedata

from clipping.config import SeleccionCfg
from clipping.models import Candidato, Escena, Transcripcion
from clipping.seleccion.tiempos import normalizar_candidato, quitar_solapes

STOPWORDS = frozenset(
    """
    a al algo ante con de del el ella ellos en es esa ese eso esta este esto la las lo los
    me mi muy no o para pero por que se si sin su sus te tu un una uno y ya yo como cuando
    donde the an and or of to in on at is are was were be it this that for with as by from
    i you he she we they my your but not so
    """.split()
)


def normalizar_texto(s: str) -> str:
    """Minúsculas, sin acentos, sin puntuación y con espacios colapsados."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _terminos(consulta: str) -> list[str]:
    vistos: list[str] = []
    for t in normalizar_texto(consulta).split():
        if t not in STOPWORDS and t not in vistos:
            vistos.append(t)
    return vistos


def buscar_por_texto(
    t: Transcripcion, consulta: str, *, n: int, cfg: SeleccionCfg, escenas: list[Escena]
) -> list[Candidato]:
    terminos = _terminos(consulta)
    palabras = t.palabras()
    if not terminos or not palabras or n <= 0:
        return []
    frase = f" {normalizar_texto(consulta)} "
    es_segs = [(s.inicio, s.fin, normalizar_texto(s.texto_es)) for s in t.segmentos if s.texto_es]
    norm = [normalizar_texto(p.texto) for p in palabras]
    largo = cfg.objetivo_seg
    paso = max(1.0, largo / 3)
    crudos: list[Candidato] = []
    ini = 0.0
    fin_total = max(t.duracion, palabras[-1].fin)
    while ini < fin_total:
        fin = ini + largo
        idx = [i for i, p in enumerate(palabras) if ini <= (p.inicio + p.fin) / 2 < fin]
        if idx:
            texto = " ".join(norm[i] for i in idx)
            texto_es = " ".join(e for a, b, e in es_segs if a < fin and b > ini)
            conjunto = set(texto.split()) | set(texto_es.split())
            hallados = [x for x in terminos if x in conjunto]
            if hallados:
                p = len(hallados) / len(terminos)
                if len(terminos) > 1 and (frase in f" {texto} " or frase in f" {texto_es} "):
                    p += 0.3
                crudos.append(
                    Candidato(
                        id="",
                        inicio=palabras[idx[0]].inicio,
                        fin=palabras[idx[-1]].fin,
                        puntaje=round(min(1.0, p), 3),
                        razon="Coincide: " + ", ".join(hallados),
                        origen="buscar",
                    )
                )
        ini += paso
    crudos.sort(key=lambda c: (-c.puntaje, c.inicio))
    normalizados = [
        normalizar_candidato(
            c,
            palabras=palabras,
            escenas=escenas,
            min_seg=cfg.min_seg,
            max_seg=cfg.max_seg,
            padding=cfg.padding_seg,
            duracion_total=t.duracion,
        )
        for c in crudos
    ]
    final = sorted(
        quitar_solapes(normalizados, cfg.separacion_min_seg), key=lambda c: (-c.puntaje, c.inicio)
    )[:n]
    for k, c in enumerate(final, 1):
        c.id = f"c{k:02d}"
    return final
