"""Carpeta de proyecto: rutas y persistencia de los artefactos de cada fuente."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .models import (
    Candidato,
    Escena,
    Meta,
    Transcripcion,
    candidatos_desde_json,
    cargar_json,
    guardar_json,
)


def _base_nombre(fuente: str) -> str:
    if re.match(r"^https?://", fuente, re.IGNORECASE):
        u = urlparse(fuente)
        v = parse_qs(u.query).get("v")
        if v:
            return v[0]
        partes = [p for p in u.path.split("/") if p]
        return partes[-1] if partes else u.netloc
    nombre = re.split(r"[\\/]", fuente.rstrip("\\/"))[-1]
    return nombre.rsplit(".", 1)[0] if "." in nombre else nombre


def slug_id(fuente: str, ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now()
    base = unicodedata.normalize("NFKD", _base_nombre(fuente))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40].strip("-") or "video"
    return f"{ahora:%Y%m%d-%H%M%S}-{slug}"


class Proyecto:
    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)

    @property
    def id(self) -> str:
        return self.raiz.name

    @property
    def meta_json(self) -> Path:
        return self.raiz / "meta.json"

    @property
    def transcripcion_json(self) -> Path:
        return self.raiz / "transcripcion.json"

    @property
    def escenas_json(self) -> Path:
        return self.raiz / "escenas.json"

    @property
    def audio_json(self) -> Path:
        return self.raiz / "audio.json"

    @property
    def candidatos_json(self) -> Path:
        return self.raiz / "candidatos.json"

    @property
    def clips_dir(self) -> Path:
        return self.raiz / "clips"

    @property
    def subs_dir(self) -> Path:
        return self.raiz / "subs"

    @property
    def video(self) -> Path:
        return self.raiz / self.meta().archivo

    @classmethod
    def crear(cls, base: Path, fuente: str, ahora: datetime | None = None) -> Proyecto:
        ahora = ahora or datetime.now()
        pid = slug_id(fuente, ahora)
        p = cls(Path(base) / pid)
        p.raiz.mkdir(parents=True, exist_ok=True)
        p.clips_dir.mkdir(exist_ok=True)
        p.subs_dir.mkdir(exist_ok=True)
        p.guardar_meta(Meta(id=pid, fuente=fuente, creado=ahora.isoformat(timespec="seconds")))
        return p

    @classmethod
    def abrir(cls, base: Path, id_o_ruta: str | Path) -> Proyecto:
        for c in (Path(base) / str(id_o_ruta), Path(id_o_ruta)):
            if (c / "meta.json").is_file():
                return cls(c)
        raise FileNotFoundError(
            f"No se encontró el proyecto '{id_o_ruta}' (buscado en {Path(base)} y como ruta)."
        )

    def meta(self) -> Meta:
        d = cargar_json(self.meta_json)
        campos = Meta.__dataclass_fields__
        return Meta(**{k: v for k, v in d.items() if k in campos})

    def guardar_meta(self, meta: Meta) -> None:
        guardar_json(self.meta_json, asdict(meta))

    def transcripcion(self) -> Transcripcion | None:
        if not self.transcripcion_json.is_file():
            return None
        return Transcripcion.from_dict(cargar_json(self.transcripcion_json))

    def guardar_transcripcion(self, t: Transcripcion) -> None:
        guardar_json(self.transcripcion_json, t.to_dict())

    def escenas(self) -> list[Escena]:
        if not self.escenas_json.is_file():
            return []
        return [Escena(**d) for d in cargar_json(self.escenas_json)]

    def guardar_escenas(self, escenas: list[Escena]) -> None:
        guardar_json(self.escenas_json, escenas)

    def candidatos(self) -> list[Candidato]:
        if not self.candidatos_json.is_file():
            return []
        return candidatos_desde_json(cargar_json(self.candidatos_json))

    def guardar_candidatos(self, candidatos: list[Candidato]) -> None:
        guardar_json(self.candidatos_json, candidatos)

    @staticmethod
    def listar(base: Path) -> list[Proyecto]:
        base = Path(base)
        if not base.is_dir():
            return []
        ps = [Proyecto(d) for d in base.iterdir() if (d / "meta.json").is_file()]
        return sorted(ps, key=lambda p: p.id, reverse=True)
