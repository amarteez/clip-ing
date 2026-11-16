"""CLI `clip`. Capa delgada sobre clipping.pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from .config import ConfigError, cargar_config
from .errores import DependenciaFaltante, ErrorFFmpeg
from .models import Candidato

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="clip-ing: clips verticales 9:16 con subtítulos a partir de un video o link.",
)


def _aviso(msg: str) -> None:
    typer.echo(msg)


def _cfg():
    try:
        return cargar_config()
    except ConfigError as e:
        typer.secho(f"Error de configuración: {e}", fg="red", err=True)
        raise typer.Exit(2)


def _tabla(cands: list[Candidato]) -> str:
    from .seleccion.tiempos import formatear_tiempo

    filas = []
    for c in cands:
        filas.append(
            f"{c.id}  {formatear_tiempo(c.inicio)[:-4]} → {formatear_tiempo(c.fin)[:-4]}"
            f"  ({c.duracion:4.1f} s)  {c.puntaje:.2f}  [{c.origen}]\n"
            f"      {c.titulo or '(sin título)'}\n      {c.razon}"
        )
    return "\n".join(filas)


def _fallo(e: Exception) -> None:
    typer.secho(str(e), fg="red", err=True)
    raise typer.Exit(1)


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Más detalle en logs.")):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")


@app.command()
def doctor(
    sin_prueba_nvenc: bool = typer.Option(
        False, "--sin-prueba-nvenc", help="No codificar el video de prueba con NVENC."
    ),
):
    """Revisa Python, ffmpeg, GPU/VRAM, CUDA, dependencias y disco; recomienda configuración."""
    from .doctor import ejecutar_doctor, formatear_reporte

    cfg = _cfg()
    chequeos, rec = ejecutar_doctor(
        cfg, probar_encoder=not sin_prueba_nvenc, disco_ruta=str(Path(cfg.proyectos_dir).resolve().anchor or ".")
    )
    typer.echo(formatear_reporte(chequeos, rec))
    if any(c.estado == "error" for c in chequeos):
        raise typer.Exit(1)


@app.command()
def auto(
    fuente: str = typer.Argument(..., help="Ruta a un video, URL (YouTube/Twitch/Kick) o id de proyecto."),
    n: int = typer.Option(10, "--n", min=1, help="Cantidad de clips."),
    sin_ia: bool = typer.Option(False, "--sin-ia", help="Solo heurística (sin claude -p)."),
    contexto: str = typer.Option("", "--contexto", help='Ej.: "canal de GTA 6: carros y meets".'),
    copiar: bool = typer.Option(False, "--copiar", help="Copiar el archivo local dentro del proyecto."),
    render_al_final: bool = typer.Option(False, "--render", help="Renderizar al terminar."),
):
    """Encuentra los N mejores momentos y guarda candidatos.json."""
    from . import pipeline

    cfg = _cfg()
    try:
        p, nuevo = pipeline.abrir_o_crear(fuente, cfg)
        typer.echo(f"Proyecto {'nuevo' if nuevo else 'existente'}: {p.raiz}")
        t, rms, escenas = pipeline.analizar(p, cfg, copiar=copiar, aviso=_aviso)
        cands = pipeline.seleccionar_auto(
            p, cfg, t, rms, escenas, n=n,
            usar_ia=cfg.seleccion.usar_ia and not sin_ia, contexto=contexto, aviso=_aviso,
        )
        p.guardar_candidatos(cands)
    except (FileNotFoundError, DependenciaFaltante, ErrorFFmpeg) as e:
        _fallo(e)
    typer.echo(f"\n{len(cands)} candidatos → {p.candidatos_json}\n")
    typer.echo(_tabla(cands))
    if render_al_final:
        _render(p, cfg)
    else:
        typer.echo(f"\nEdita candidatos.json si quieres y luego: clip render {p.id}")


@app.command()
def buscar(
    fuente: str = typer.Argument(..., help="Video, URL o id de proyecto."),
    descripcion: str = typer.Argument(..., help='Escena a encontrar, p. ej. "cuando choca el Infernus".'),
    n: int = typer.Option(3, "--n", min=1),
    sin_ia: bool = typer.Option(False, "--sin-ia", help="Solo coincidencia de palabras."),
):
    """Encuentra la escena descrita en lenguaje natural y la agrega a candidatos.json."""
    from . import pipeline

    cfg = _cfg()
    try:
        p, _ = pipeline.abrir_o_crear(fuente, cfg)
        t, _rms, escenas = pipeline.analizar(p, cfg, aviso=_aviso)
        encontrados = pipeline.buscar(
            p, cfg, t, escenas, descripcion, n=n,
            usar_ia=cfg.seleccion.usar_ia and not sin_ia, aviso=_aviso,
        )
    except (FileNotFoundError, DependenciaFaltante, ErrorFFmpeg) as e:
        _fallo(e)
    if not encontrados:
        typer.echo("No se encontró nada que coincida.")
        raise typer.Exit(1)
    # Se agregan como b01, b02… sin pisar los existentes.
    existentes = [c for c in p.candidatos() if not c.id.startswith("b")]
    from dataclasses import replace

    nuevos = [replace(c, id=f"b{i:02d}") for i, c in enumerate(encontrados, start=1)]
    p.guardar_candidatos(existentes + nuevos)
    typer.echo(_tabla(nuevos))
    typer.echo(f"\nRenderiza con: clip render {p.id} --solo {','.join(c.id for c in nuevos)}")


def _render(p, cfg, solo=None, reencuadre=None, dry_run=False) -> None:
    from . import pipeline

    try:
        salidas = pipeline.render(
            p, cfg, solo=solo, reencuadre=reencuadre, dry_run=dry_run, aviso=_aviso
        )
    except (ValueError, ErrorFFmpeg) as e:
        _fallo(e)
    if not dry_run and salidas:
        typer.echo(f"\n{len(salidas)} clips en {p.clips_dir}")


@app.command()
def render(
    proyecto: str = typer.Argument(..., help="Id o ruta del proyecto."),
    solo: Optional[str] = typer.Option(None, "--solo", help="Ids separados por coma (c01,c03)."),
    reencuadre: Optional[str] = typer.Option(None, "--reencuadre", help="centro | blur"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Genera .ass e imprime comandos sin ejecutar."),
):
    """Renderiza los candidatos aprobados a clips 9:16 con subtítulos."""
    from .proyecto import Proyecto

    cfg = _cfg()
    if reencuadre not in (None, "centro", "blur"):
        _fallo(ValueError("--reencuadre debe ser 'centro' o 'blur'"))
    try:
        p = Proyecto.abrir(Path(cfg.proyectos_dir), proyecto)
    except FileNotFoundError as e:
        _fallo(e)
    ids = [s.strip() for s in solo.split(",") if s.strip()] if solo else None
    _render(p, cfg, solo=ids, reencuadre=reencuadre, dry_run=dry_run)


@app.command()
def revisar(proyecto: str = typer.Argument(..., help="Id o ruta del proyecto.")):
    """Revisión de candidatos (fase 3: vista HTML). Por ahora indica cómo editar el JSON."""
    from .proyecto import Proyecto

    cfg = _cfg()
    try:
        p = Proyecto.abrir(Path(cfg.proyectos_dir), proyecto)
    except FileNotFoundError as e:
        _fallo(e)
    typer.echo(_tabla(p.candidatos()))
    typer.echo(
        f"\nEdita {p.candidatos_json}:\n"
        '  - ajusta "inicio"/"fin" (segundos) y "titulo"\n'
        '  - "aprobado": false para excluir un clip\n'
        f"Luego: clip render {p.id}\n(La vista HTML llega en la fase 3.)"
    )


@app.command()
def proyectos():
    """Lista los proyectos."""
    from .proyecto import Proyecto

    cfg = _cfg()
    ps = Proyecto.listar(Path(cfg.proyectos_dir))
    if not ps:
        typer.echo("No hay proyectos todavía.")
        return
    for p in ps:
        m = p.meta()
        typer.echo(f"{p.id}  {len(p.candidatos()):3d} candidatos  {m.titulo or m.fuente}")


if __name__ == "__main__":
    app()
