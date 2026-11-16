"""Orquestación de pasos (reutilizable por el CLI y, más adelante, por una API web).

Cada paso es idempotente: si su artefacto ya existe en la carpeta del proyecto, se reutiliza.
Los imports pesados viven dentro de las funciones.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .config import Config
from .errores import DependenciaFaltante, ErrorClaude, ErrorFFmpeg
from .models import Candidato, Escena, Transcripcion, cargar_json, guardar_json
from .proyecto import Proyecto

log = logging.getLogger("clipping")
Aviso = Callable[[str], None]


def _nada(_: str) -> None:
    pass


# ---- proyecto -----------------------------------------------------------------

def abrir_o_crear(fuente: str, cfg: Config) -> tuple[Proyecto, bool]:
    """Si `fuente` es un proyecto existente (id o ruta) lo abre; si no, crea uno nuevo."""
    base = Path(cfg.proyectos_dir)
    try:
        return Proyecto.abrir(base, fuente), False
    except FileNotFoundError:
        return Proyecto.crear(base, fuente), True


def paso_fuente(p: Proyecto, cfg: Config, *, copiar: bool = False, aviso: Aviso = _nada) -> None:
    import os

    from .descarga import duracion_video, obtener_fuente

    meta = p.meta()
    if not meta.archivo:
        aviso(f"Obteniendo fuente: {meta.fuente}")
        archivo, titulo = obtener_fuente(
            meta.fuente, p.raiz, copiar=copiar, cookies=os.environ.get("YTDLP_COOKIES")
        )
        meta = replace(meta, archivo=archivo, titulo=titulo or meta.titulo)
        p.guardar_meta(meta)
    if not meta.duracion:
        meta = replace(meta, duracion=duracion_video(p.video))
        p.guardar_meta(meta)


def paso_transcripcion(p: Proyecto, cfg: Config, *, aviso: Aviso = _nada) -> Transcripcion:
    t = p.transcripcion()
    if t is not None:
        return t
    from .hardware import detectar_gpus, resolver_transcripcion
    from .transcripcion import registrar_dlls_cuda, transcribir

    rec = resolver_transcripcion(cfg.transcripcion, detectar_gpus())
    aviso(f"Transcribiendo con {rec.modelo} ({rec.dispositivo}/{rec.compute_type}). {rec.motivo}")
    if rec.dispositivo == "cuda":
        registrar_dlls_cuda()

    ultimo = [-1]

    def progreso(actual: float, total: float) -> None:
        pct = int(100 * actual / total) if total else 0
        if pct >= ultimo[0] + 10:
            ultimo[0] = pct
            aviso(f"  transcripción {pct}%")

    t = transcribir(p.video, rec, cfg.transcripcion, progreso)
    p.guardar_transcripcion(t)
    return t


PASO_RMS = 0.5


def paso_audio(p: Proyecto, cfg: Config, *, aviso: Aviso = _nada) -> list[float]:
    if p.audio_json.is_file():
        return cargar_json(p.audio_json)["rms"]
    from .deteccion.audio import serie_rms

    aviso("Analizando volumen…")
    rms = serie_rms(p.video, paso=PASO_RMS)
    guardar_json(p.audio_json, {"paso": PASO_RMS, "rms": rms})
    return rms


def paso_escenas(p: Proyecto, cfg: Config, *, aviso: Aviso = _nada) -> list[Escena]:
    if p.escenas_json.is_file():
        return p.escenas()
    try:
        from .deteccion.escenas import detectar_escenas

        aviso("Detectando cambios de escena…")
        escenas = detectar_escenas(p.video)
    except DependenciaFaltante as e:
        aviso(f"[!!] {e} — se continúa sin escenas.")
        return []
    p.guardar_escenas(escenas)
    return escenas


def analizar(
    p: Proyecto, cfg: Config, *, copiar: bool = False, aviso: Aviso = _nada
) -> tuple[Transcripcion, list[float], list[Escena]]:
    paso_fuente(p, cfg, copiar=copiar, aviso=aviso)
    t = paso_transcripcion(p, cfg, aviso=aviso)
    rms = paso_audio(p, cfg, aviso=aviso)
    escenas = paso_escenas(p, cfg, aviso=aviso)
    return t, rms, escenas


# ---- selección ----------------------------------------------------------------

def _con_titulos(cands: list[Candidato], t: Transcripcion) -> list[Candidato]:
    from .seleccion.titulos import titulo_simple

    return [
        c if c.titulo else replace(c, titulo=titulo_simple(t.texto_en(c.inicio, c.fin)))
        for c in cands
    ]


def seleccionar_auto(
    p: Proyecto,
    cfg: Config,
    t: Transcripcion,
    rms: list[float],
    escenas: list[Escena],
    *,
    n: int,
    usar_ia: bool,
    contexto: str = "",
    aviso: Aviso = _nada,
) -> list[Candidato]:
    from .seleccion import heuristica

    duracion = p.meta().duracion or t.duracion
    if usar_ia:
        from .seleccion import claude

        try:
            aviso("Eligiendo momentos con Claude…")
            cands = claude.seleccionar_auto(
                t, escenas, n=n, cfg_sel=cfg.seleccion, cfg_claude=cfg.claude, contexto=contexto
            )
            if cands:
                return _con_titulos(cands, t)
            aviso("[!!] Claude no devolvió candidatos; se usa la heurística.")
        except ErrorClaude as e:
            aviso(f"[!!] Claude no disponible ({e}); se usa la heurística.")
    cands = heuristica.seleccionar(
        duracion,
        rms=rms,
        paso_rms=PASO_RMS,
        palabras=t.palabras(),
        escenas=escenas,
        cfg=cfg.seleccion,
        n=n,
    )
    return _con_titulos(cands, t)


def buscar(
    p: Proyecto,
    cfg: Config,
    t: Transcripcion,
    escenas: list[Escena],
    consulta: str,
    *,
    n: int,
    usar_ia: bool,
    aviso: Aviso = _nada,
) -> list[Candidato]:
    from .seleccion.buscar import buscar_por_texto

    if usar_ia:
        from .seleccion import claude

        try:
            aviso("Buscando la escena con Claude…")
            cands = claude.buscar(
                t, escenas, consulta, n=n, cfg_sel=cfg.seleccion, cfg_claude=cfg.claude
            )
            if cands:
                return _con_titulos(cands, t)
        except ErrorClaude as e:
            aviso(f"[!!] Claude no disponible ({e}); búsqueda por palabras clave.")
    return _con_titulos(buscar_por_texto(t, consulta, n=n, cfg=cfg.seleccion, escenas=escenas), t)


# ---- render -------------------------------------------------------------------

def _slug(texto: str, largo: int = 40) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:largo].strip("-")


def _correr_ffmpeg(cmd: list[str], cwd: Path) -> None:
    from .hardware import resolver_ejecutable

    exe = resolver_ejecutable(cmd[0])
    if exe is None:
        raise ErrorFFmpeg("ffmpeg no encontrado: ejecuta .\\setup.ps1")
    r = subprocess.run(
        [exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if r.returncode != 0:
        cola = "\n".join(r.stderr.strip().splitlines()[-15:])
        raise ErrorFFmpeg(f"ffmpeg falló (código {r.returncode}):\n{cola}")


def render(
    p: Proyecto,
    cfg: Config,
    *,
    solo: list[str] | None = None,
    reencuadre: str | None = None,
    dry_run: bool = False,
    aviso: Aviso = _nada,
) -> list[Path]:
    """Renderiza los candidatos aprobados (o los ids de `solo`). Devuelve rutas de clips."""
    from .hardware import nvenc_disponible, probar_nvenc
    from .render.ffmpeg import comando_a_texto, construir_comando_clip, elegir_encoder
    from .render.subtitulos import escribir_ass, generar_ass

    cands = p.candidatos()
    if solo:
        ids = set(solo)
        faltan = ids - {c.id for c in cands}
        if faltan:
            raise ValueError(f"Ids inexistentes en candidatos.json: {', '.join(sorted(faltan))}")
        cands = [c for c in cands if c.id in ids]
    else:
        cands = [c for c in cands if c.aprobado]
    if not cands:
        aviso("No hay candidatos aprobados para renderizar.")
        return []

    t = p.transcripcion()
    palabras = t.palabras() if t else []
    rcfg = replace(cfg.render, reencuadre=reencuadre) if reencuadre else cfg.render

    if dry_run:
        encoder = elegir_encoder(rcfg.encoder, rcfg.encoder == "h264_nvenc")
    else:
        hay_nvenc = rcfg.encoder != "libx264" and nvenc_disponible() and probar_nvenc()
        encoder = elegir_encoder(rcfg.encoder, hay_nvenc)
    aviso(f"Encoder: {encoder} · reencuadre: {rcfg.reencuadre}")

    p.clips_dir.mkdir(parents=True, exist_ok=True)
    p.subs_dir.mkdir(parents=True, exist_ok=True)
    video = p.video.resolve()
    salidas: list[Path] = []
    for c in cands:
        ass_nombre = f"{c.id}.ass"
        escribir_ass(
            p.subs_dir / ass_nombre,
            generar_ass(
                palabras,
                inicio_clip=c.inicio,
                fin_clip=c.fin,
                cfg=cfg.subtitulos,
                ancho=rcfg.ancho,
                alto=rcfg.alto,
            ),
        )
        nombre = f"{c.id}-{_slug(c.titulo)}" if _slug(c.titulo) else c.id
        salida = (p.clips_dir / f"{nombre}.mp4").resolve()

        def cmd_para(enc: str) -> list[str]:
            # El .ass se pasa relativo y ffmpeg corre con cwd=subs/: evita escapar "C:\…" en el filtro.
            return construir_comando_clip(
                entrada=video, salida=salida, inicio=c.inicio, fin=c.fin,
                ass=Path(ass_nombre), cfg=rcfg, encoder=enc,
            )

        cmd = cmd_para(encoder)
        if dry_run:
            aviso(f"{c.id}: {comando_a_texto(cmd)}")
        else:
            aviso(f"Renderizando {c.id} ({c.duracion:.1f} s): {c.titulo or c.razon}")
            try:
                _correr_ffmpeg(cmd, p.subs_dir)
            except ErrorFFmpeg as e:
                if encoder != "h264_nvenc":
                    raise
                aviso(f"[!!] NVENC falló, reintentando con libx264. ({e})")
                encoder = "libx264"
                _correr_ffmpeg(cmd_para(encoder), p.subs_dir)
            guardar_json(
                salida.with_suffix(".json"),
                {"id": c.id, "titulo": c.titulo, "razon": c.razon, "inicio": c.inicio,
                 "fin": c.fin, "puntaje": c.puntaje, "origen": c.origen},
            )
        salidas.append(salida)
    return salidas
