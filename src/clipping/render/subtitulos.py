"""Generación de subtítulos ASS estilo viral (palabra activa resaltada)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from clipping.config import SubtitulosCfg
from clipping.models import Palabra

_PUNTUACION_CORTE = (".", "?", "!", ",")


def agrupar_palabras(
    palabras: list[Palabra],
    max_palabras: int,
    max_hueco: float = 0.6,
    max_dur: float = 2.5,
) -> list[list[Palabra]]:
    """Agrupa palabras en líneas cortas de subtítulo."""
    max_palabras = max(1, max_palabras)
    grupos: list[list[Palabra]] = []
    actual: list[Palabra] = []
    for p in palabras:
        if actual:
            hueco = p.inicio - actual[-1].fin
            if (
                len(actual) >= max_palabras
                or hueco > max_hueco
                or p.fin - actual[0].inicio > max_dur
            ):
                grupos.append(actual)
                actual = []
        actual.append(p)
        if p.texto.rstrip().endswith(_PUNTUACION_CORTE):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def escapar_ass(texto: str) -> str:
    """Escapa caracteres especiales de ASS; los saltos de línea pasan a espacio."""
    texto = texto.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return texto.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def tiempo_ass(seg: float) -> str:
    """Formatea segundos como H:MM:SS.cc (centésimas, redondeo half-up, nunca negativo)."""
    cs = int((Decimal(repr(max(0.0, float(seg)))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    h, resto = divmod(cs, 360000)
    m, resto = divmod(resto, 6000)
    s, c = divmod(resto, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def color_override(color_ass: str) -> str:
    """Convierte '&HAABBGGRR' (o '&HBBGGRR') a la forma de override '&HBBGGRR&'."""
    hexa = color_ass.strip().upper().lstrip("&").lstrip("H").rstrip("&")
    hexa = hexa[-6:].rjust(6, "0")
    return f"&H{hexa}&"


def _recortar(
    palabras: list[Palabra], inicio_clip: float, fin_clip: float
) -> list[Palabra]:
    dur = fin_clip - inicio_clip
    out: list[Palabra] = []
    for p in palabras:
        if p.fin <= inicio_clip or p.inicio >= fin_clip or not p.texto.strip():
            continue
        ini = max(0.0, p.inicio - inicio_clip)
        fin = min(dur, p.fin - inicio_clip)
        if fin <= ini:
            continue
        out.append(Palabra(texto=p.texto.strip(), inicio=ini, fin=fin, prob=p.prob))
    return out


def generar_ass(
    palabras: list[Palabra],
    *,
    inicio_clip: float,
    fin_clip: float,
    cfg: SubtitulosCfg,
    ancho: int = 1080,
    alto: int = 1920,
) -> str:
    """Genera el contenido ASS. Las palabras vienen en tiempo de la fuente."""
    rel = _recortar(palabras, inicio_clip, fin_clip)
    grupos = agrupar_palabras(rel, cfg.palabras_por_linea)
    resalte = color_override(cfg.color_resaltado)

    lineas = [
        "[Script Info]",
        "; Generado por clipping",
        "ScriptType: v4.00+",
        f"PlayResX: {ancho}",
        f"PlayResY: {alto}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Viral,{cfg.fuente},{cfg.tamano},{cfg.color},{cfg.color},"
        f"{cfg.color_contorno},&H64000000,-1,0,0,0,100,100,0,0,1,{cfg.contorno},"
        f"{cfg.sombra},2,60,60,{cfg.margen_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def _txt(p: Palabra) -> str:
        t = escapar_ass(p.texto)
        return t.upper() if cfg.mayusculas else t

    for grupo in grupos:
        fin_grupo = grupo[-1].fin
        for i, activa in enumerate(grupo):
            ini = activa.inicio
            fin = grupo[i + 1].inicio if i + 1 < len(grupo) else fin_grupo
            if fin <= ini:
                continue
            partes = []
            for j, p in enumerate(grupo):
                if j == i:
                    partes.append(f"{{\\c{resalte}\\fscx115\\fscy115}}{_txt(p)}{{\\r}}")
                else:
                    partes.append(_txt(p))
            texto = " ".join(partes)
            if i == 0:
                texto = "{\\fad(60,0)}" + texto
            lineas.append(
                f"Dialogue: 0,{tiempo_ass(ini)},{tiempo_ass(fin)},Viral,,0,0,0,,{texto}"
            )
    return "\n".join(lineas) + "\n"


def escribir_ass(ruta: Path, contenido: str) -> None:
    """Escribe el .ass en UTF-8 con BOM."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8-sig")
