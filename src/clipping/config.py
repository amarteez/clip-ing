"""Carga de configuración: defaults < config.yaml < variables de entorno (.env).

Variables de entorno: CLIP__SECCION__CLAVE=valor (doble guion bajo, case-insensitive).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(ValueError):
    pass


@dataclass
class TranscripcionCfg:
    modelo: str = "auto"
    dispositivo: str = "auto"
    compute_type: str = "auto"
    idioma: str | None = None
    traducir_a_es: bool = True
    beam_size: int = 5
    vad: bool = True


@dataclass
class PesosCfg:
    volumen: float = 0.40
    palabras: float = 0.35
    escenas: float = 0.25


@dataclass
class SeleccionCfg:
    n: int = 10
    min_seg: float = 15
    max_seg: float = 60
    objetivo_seg: float = 30
    padding_seg: float = 0.3
    separacion_min_seg: float = 5
    usar_ia: bool = True
    pesos: PesosCfg = field(default_factory=PesosCfg)


@dataclass
class ClaudeCfg:
    comando: str = "claude"
    timeout_seg: int = 300
    modelo: str | None = None


@dataclass
class RenderCfg:
    ancho: int = 1080
    alto: int = 1920
    fps: int = 30
    encoder: str = "auto"
    reencuadre: str = "blur"
    crf: int = 20
    cq: int = 23
    preset_x264: str = "veryfast"
    preset_nvenc: str = "p5"
    audio_bitrate: str = "160k"
    blur_sigma: int = 30


@dataclass
class SubtitulosCfg:
    fuente: str = "Arial Black"
    tamano: int = 92
    color: str = "&H00FFFFFF"
    color_resaltado: str = "&H0000E5FF"
    color_contorno: str = "&H00000000"
    contorno: int = 6
    sombra: int = 2
    palabras_por_linea: int = 3
    mayusculas: bool = True
    margen_v: int = 520


@dataclass
class Config:
    proyectos_dir: str = "proyectos"
    transcripcion: TranscripcionCfg = field(default_factory=TranscripcionCfg)
    seleccion: SeleccionCfg = field(default_factory=SeleccionCfg)
    claude: ClaudeCfg = field(default_factory=ClaudeCfg)
    render: RenderCfg = field(default_factory=RenderCfg)
    subtitulos: SubtitulosCfg = field(default_factory=SubtitulosCfg)


# ---- construcción ---------------------------------------------------------------

def _coerce(valor: Any, tipo_actual: Any) -> Any:
    """Convierte strings de entorno al tipo del valor por defecto."""
    if not isinstance(valor, str):
        return valor
    if valor.lower() in ("null", "none", ""):
        return None
    if isinstance(tipo_actual, bool):
        if valor.lower() in ("1", "true", "si", "sí", "yes", "on"):
            return True
        if valor.lower() in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"Booleano inválido: {valor!r}")
    if isinstance(tipo_actual, int):
        return int(valor)
    if isinstance(tipo_actual, float):
        return float(valor)
    return valor


def _aplicar(obj: Any, datos: Mapping[str, Any], ruta: str = "") -> None:
    nombres = {f.name: f for f in fields(obj)}
    for clave, valor in datos.items():
        if clave not in nombres:
            raise ConfigError(f"Clave desconocida en config: {ruta}{clave}")
        actual = getattr(obj, clave)
        if hasattr(actual, "__dataclass_fields__"):
            if not isinstance(valor, Mapping):
                raise ConfigError(f"{ruta}{clave} debe ser una sección")
            _aplicar(actual, valor, f"{ruta}{clave}.")
        else:
            try:
                setattr(obj, clave, _coerce(valor, actual))
            except ValueError as e:
                raise ConfigError(f"Valor inválido para {ruta}{clave}: {valor!r}") from e


def _desde_entorno(env: Mapping[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in env.items():
        if not k.upper().startswith("CLIP__"):
            continue
        partes = [p.lower() for p in k[6:].split("__") if p]
        if not partes:
            continue
        nodo = out
        for p in partes[:-1]:
            nodo = nodo.setdefault(p, {})
        nodo[partes[-1]] = v
    return out


def validar(cfg: Config) -> None:
    s = cfg.seleccion
    if not (0 < s.min_seg <= s.objetivo_seg <= s.max_seg):
        raise ConfigError("Debe cumplirse 0 < min_seg <= objetivo_seg <= max_seg")
    if s.n < 1:
        raise ConfigError("seleccion.n debe ser >= 1")
    if s.padding_seg < 0 or s.separacion_min_seg < 0:
        raise ConfigError("padding/separación no pueden ser negativos")
    pesos = [s.pesos.volumen, s.pesos.palabras, s.pesos.escenas]
    if any(p < 0 for p in pesos) or sum(pesos) <= 0:
        raise ConfigError("Los pesos deben ser >= 0 y sumar > 0")
    r = cfg.render
    if r.encoder not in ("auto", "h264_nvenc", "libx264"):
        raise ConfigError(f"render.encoder inválido: {r.encoder}")
    if r.reencuadre not in ("centro", "blur"):
        raise ConfigError(f"render.reencuadre inválido: {r.reencuadre}")
    if r.ancho % 2 or r.alto % 2:
        raise ConfigError("ancho/alto deben ser pares")
    t = cfg.transcripcion
    if t.dispositivo not in ("auto", "cuda", "cpu"):
        raise ConfigError(f"transcripcion.dispositivo inválido: {t.dispositivo}")
    if t.compute_type == "float16":
        raise ConfigError("float16 no está soportado en GTX 1060 (Pascal); usa int8 o auto")
    if cfg.subtitulos.palabras_por_linea < 1:
        raise ConfigError("subtitulos.palabras_por_linea debe ser >= 1")


def cargar_config(
    ruta: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    cargar_dotenv: bool = True,
) -> Config:
    """Carga la configuración. `env` permite inyectar entorno en tests."""
    if env is None:
        if cargar_dotenv:
            try:
                from dotenv import load_dotenv

                load_dotenv(override=False)
            except ImportError:
                pass
        env = os.environ
    if ruta is None:
        ruta = env.get("CLIP_CONFIG", "config.yaml")
    cfg = Config()
    ruta = Path(ruta)
    if ruta.exists():
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        if not isinstance(datos, Mapping):
            raise ConfigError(f"{ruta} debe contener un mapa YAML")
        _aplicar(cfg, datos)
    _aplicar(cfg, _desde_entorno(env))
    validar(cfg)
    return cfg


def config_por_defecto() -> Config:
    return copy.deepcopy(Config())
