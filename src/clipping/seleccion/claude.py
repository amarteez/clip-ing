"""Selección de clips con `claude -p` (Claude Code headless, suscripción del usuario)."""

from __future__ import annotations

import json
import math
import subprocess
from typing import Any, Callable

from clipping.config import ClaudeCfg, SeleccionCfg
from clipping.errores import ErrorClaude
from clipping.hardware import resolver_ejecutable
from clipping.models import Candidato, Escena, Transcripcion
from clipping.seleccion.tiempos import normalizar_candidato, parsear_tiempo, quitar_solapes

Correr = Callable[[list[str], str, float], tuple[int, str, str]]

_MAX_TITULO = 60


def _mmss(seg: float) -> str:
    s = int(max(0.0, seg))
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def formatear_transcripcion(t: Transcripcion, max_chars: int = 120_000) -> str:
    """Una línea "[MM:SS-MM:SS] texto" por segmento (texto_es si existe).

    Estrategia si excede max_chars: se fusionan k segmentos consecutivos por línea
    (k crece hasta que quepa el encabezado) y luego el texto de cada línea se trunca con
    "…" a un presupuesto uniforme de caracteres. Así se conserva la cobertura de TODO el
    video en vez de cortar solo el final.
    """
    items = [
        (s.inicio, s.fin, (s.texto_es or s.texto).strip()) for s in t.segmentos
    ]
    items = [i for i in items if i[2]]

    def render(grupos: list[tuple[float, float, str]], limite: int | None) -> str:
        lineas = []
        for a, b, txt in grupos:
            if limite is not None and len(txt) > limite:
                txt = txt[: max(1, limite - 1)].rstrip() + "…"
            lineas.append(f"[{_mmss(a)}-{_mmss(b)}] {txt}")
        return "\n".join(lineas)

    completo = render(items, None)
    if len(completo) <= max_chars or not items:
        return completo

    cabecera = len("[00:00-00:00] ") + 1  # ver nota: horas añaden pocos caracteres más
    k = 1
    while True:
        grupos = [
            (g[0][0], g[-1][1], " ".join(x[2] for x in g))
            for g in (items[i : i + k] for i in range(0, len(items), k))
        ]
        # presupuesto de texto por línea (con margen para horas)
        presupuesto = max_chars // len(grupos) - (cabecera + 6)
        if presupuesto >= 40 or len(grupos) == 1:
            break
        k += 1
    presupuesto = max(10, presupuesto)
    texto = render(grupos, presupuesto)
    while len(texto) > max_chars and presupuesto > 10:
        presupuesto = max(10, int(presupuesto * 0.9))
        texto = render(grupos, presupuesto)
    return texto[:max_chars]


_FORMATO_JSON = (
    '{"clips":[{"inicio":segundos,"fin":segundos,"puntaje":0-1,"razon":"...",'
    '"titulo":"título viral corto en español, máx 60 chars"}]}'
)


def _reglas(n: int, cfg: SeleccionCfg) -> str:
    return (
        f"Los clips son para TikTok / YouTube Shorts / Instagram Reels. Cada clip debe durar "
        f"entre {cfg.min_seg:g} y {cfg.max_seg:g} segundos, ser autocontenido (se entiende sin "
        f"ver el resto) y tener un gancho fuerte en los primeros 3 segundos. Empieza y termina "
        f"en límites de frase. Devuelve como máximo {n} clips, sin solapes entre ellos.\n"
        f"Los tiempos están en segundos desde el inicio del video (puedes usar los marcadores "
        f"[MM:SS] de la transcripción). "
        f"Responde SOLO con JSON válido, sin texto adicional ni bloques de código, con este "
        f"formato exacto:\n{_FORMATO_JSON}"
    )


def prompt_auto(t: Transcripcion, *, n: int, cfg: SeleccionCfg, contexto: str = "") -> str:
    ctx = f"Contexto del canal/video: {contexto.strip()}\n\n" if contexto.strip() else ""
    return (
        f"Eres un editor experto en contenido viral. Analiza la transcripción (idioma: "
        f"{t.idioma}, duración {t.duracion:.0f} s) y elige los {n} mejores momentos para "
        f"convertir en clips verticales.\n\n{ctx}{_reglas(n, cfg)}\n\n"
        f"TRANSCRIPCIÓN:\n{formatear_transcripcion(t)}\n"
    )


def prompt_buscar(t: Transcripcion, consulta: str, *, n: int, cfg: SeleccionCfg) -> str:
    return (
        f"Eres un editor de video. Encuentra en la transcripción (idioma del audio: "
        f"{t.idioma}, duración {t.duracion:.0f} s) la(s) escena(s) que coinciden con esta "
        f"descripción en lenguaje natural: \"{consulta.strip()}\".\n"
        f"La descripción puede estar en español aunque el audio esté en otro idioma: razona de "
        f"forma multilingüe y busca por significado, no solo por palabras literales. Ordena "
        f"por relevancia (puntaje = qué tanto coincide).\n\n{_reglas(n, cfg)}\n\n"
        f"TRANSCRIPCIÓN:\n{formatear_transcripcion(t)}\n"
    )


# ---- parseo -----------------------------------------------------------------------

def _a_segundos(v: Any) -> float:
    if isinstance(v, bool):
        raise ValueError("bool")
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            raise ValueError("no finito")
        return float(v)
    if isinstance(v, str):
        return parsear_tiempo(v)
    raise ValueError(f"tipo inválido: {type(v)}")


def _validar(items: list[Any]) -> list[dict]:
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            ini, fin = _a_segundos(it.get("inicio")), _a_segundos(it.get("fin"))
        except ValueError:
            continue
        if ini < 0 or fin <= ini:
            continue
        try:
            p = float(it.get("puntaje", 0.5))
            if not math.isfinite(p):
                p = 0.5
        except (TypeError, ValueError):
            p = 0.5
        out.append({
            "inicio": ini,
            "fin": fin,
            "puntaje": min(1.0, max(0.0, p)),
            "razon": str(it.get("razon") or "").strip(),
            "titulo": str(it.get("titulo") or "").strip()[:_MAX_TITULO],
        })
    return out


def _extraer(texto: str, profundidad: int = 0) -> list[Any] | None:
    """Primer objeto/array JSON válido (balanceado) que contenga clips."""
    dec = json.JSONDecoder()
    pos = 0
    while True:
        cand = [i for i in (texto.find("{", pos), texto.find("[", pos)) if i >= 0]
        if not cand:
            return None
        i = min(cand)
        try:
            obj, fin = dec.raw_decode(texto, i)
        except ValueError:
            pos = i + 1
            continue
        if isinstance(obj, dict):
            if isinstance(obj.get("result"), str) and profundidad < 3:
                r = _extraer(obj["result"], profundidad + 1)
                if r is not None:
                    return r
            elif isinstance(obj.get("clips"), list):
                return obj["clips"]
            elif "inicio" in obj and "fin" in obj:
                return [obj]
        elif isinstance(obj, list) and any(isinstance(x, dict) for x in obj):
            return obj
        pos = i + 1 if not isinstance(obj, (dict, list)) else fin


def parsear_respuesta(texto: str) -> list[dict]:
    """Extrae y valida los clips de la respuesta de Claude. ErrorClaude si no hay ninguno."""
    items = _extraer(texto or "")
    validos = _validar(items) if items else []
    if not validos:
        raise ErrorClaude("La respuesta de Claude no contiene clips utilizables.")
    return validos


# ---- ejecución --------------------------------------------------------------------

def _correr_real(cmd: list[str], stdin: str, timeout: float) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise ErrorClaude(f"claude excedió el timeout de {timeout:g} s.") from e
    except OSError as e:
        raise ErrorClaude(f"No se pudo ejecutar claude: {e}") from e
    return r.returncode, r.stdout or "", r.stderr or ""


def llamar_claude(prompt: str, cfg: ClaudeCfg, *, correr: Correr | None = None) -> str:
    """Ejecuta `claude -p` con el prompt por stdin y devuelve el texto de la respuesta."""
    ruta = resolver_ejecutable(cfg.comando)
    if ruta is None and correr is None:
        raise ErrorClaude(
            f"No se encontró '{cfg.comando}' en el PATH. Instala Claude Code "
            "(npm i -g @anthropic-ai/claude-code) e inicia sesión con `claude`."
        )
    cmd = [ruta or cfg.comando, "-p", "--output-format", "json"]
    if cfg.modelo:
        cmd += ["--model", cfg.modelo]
    ejecutor = correr or _correr_real
    try:
        codigo, salida, err = ejecutor(cmd, prompt, float(cfg.timeout_seg))
    except subprocess.TimeoutExpired as e:
        raise ErrorClaude(f"claude excedió el timeout de {cfg.timeout_seg} s.") from e
    if codigo != 0:
        raise ErrorClaude(f"claude terminó con código {codigo}: {(err or salida).strip()[:500]}")
    try:
        datos = json.loads(salida)
    except ValueError:
        return salida
    if isinstance(datos, dict):
        if datos.get("is_error"):
            raise ErrorClaude(f"claude devolvió un error: {str(datos.get('result', ''))[:500]}")
        if isinstance(datos.get("result"), str):
            return datos["result"]
    return salida


# ---- candidatos -------------------------------------------------------------------

def candidatos_desde_claude(
    items: list[dict],
    *,
    origen: str,
    t: Transcripcion,
    escenas: list[Escena],
    cfg: SeleccionCfg,
) -> list[Candidato]:
    palabras = t.palabras()
    cands: list[Candidato] = []
    for it in items:
        ini = max(0.0, float(it["inicio"]))
        fin = min(t.duracion, float(it["fin"])) if t.duracion > 0 else float(it["fin"])
        if fin <= ini:
            continue
        c = Candidato(
            id="", inicio=ini, fin=fin, puntaje=float(it.get("puntaje", 0.5)),
            razon=str(it.get("razon", "")), titulo=str(it.get("titulo", "")), origen=origen,
        )
        cands.append(
            normalizar_candidato(
                c, palabras=palabras, escenas=escenas, min_seg=cfg.min_seg,
                max_seg=cfg.max_seg, padding=cfg.padding_seg, duracion_total=t.duracion,
            )
        )
    final = sorted(quitar_solapes(cands, cfg.separacion_min_seg), key=lambda c: -c.puntaje)
    for k, c in enumerate(final, 1):
        c.id = f"c{k:02d}"
    return final


def _ejecutar(prompt: str, n: int, origen: str, t, escenas, cfg_sel, cfg_claude, correr):
    texto = llamar_claude(prompt, cfg_claude, correr=correr)
    items = parsear_respuesta(texto)
    cands = candidatos_desde_claude(items, origen=origen, t=t, escenas=escenas, cfg=cfg_sel)
    if not cands:
        raise ErrorClaude("Ningún clip de Claude resultó válido tras normalizar.")
    return cands[:n]


def seleccionar_auto(
    t: Transcripcion,
    escenas: list[Escena],
    *,
    n: int,
    cfg_sel: SeleccionCfg,
    cfg_claude: ClaudeCfg,
    contexto: str = "",
    correr: Correr | None = None,
) -> list[Candidato]:
    prompt = prompt_auto(t, n=n, cfg=cfg_sel, contexto=contexto)
    return _ejecutar(prompt, n, "claude", t, escenas, cfg_sel, cfg_claude, correr)


def buscar(
    t: Transcripcion,
    escenas: list[Escena],
    consulta: str,
    *,
    n: int,
    cfg_sel: SeleccionCfg,
    cfg_claude: ClaudeCfg,
    correr: Correr | None = None,
) -> list[Candidato]:
    prompt = prompt_buscar(t, consulta, n=n, cfg=cfg_sel)
    return _ejecutar(prompt, n, "claude", t, escenas, cfg_sel, cfg_claude, correr)
