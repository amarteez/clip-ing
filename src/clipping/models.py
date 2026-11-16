"""Modelos de datos compartidos. Todos los tiempos en segundos (float) relativos a la fuente."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Palabra:
    texto: str
    inicio: float
    fin: float
    prob: float = 1.0


@dataclass
class Segmento:
    inicio: float
    fin: float
    texto: str
    palabras: list[Palabra] = field(default_factory=list)
    texto_es: str | None = None  # traducción al español si el audio era de otro idioma

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Segmento:
        d = dict(d)
        d["palabras"] = [Palabra(**p) for p in d.get("palabras", [])]
        return cls(**d)


@dataclass
class Transcripcion:
    idioma: str
    duracion: float
    segmentos: list[Segmento] = field(default_factory=list)
    modelo: str = ""

    def palabras(self) -> list[Palabra]:
        return [p for s in self.segmentos for p in s.palabras]

    def palabras_en(self, inicio: float, fin: float) -> list[Palabra]:
        """Palabras cuyo centro cae en [inicio, fin)."""
        return [p for p in self.palabras() if inicio <= (p.inicio + p.fin) / 2 < fin]

    def texto_en(self, inicio: float, fin: float) -> str:
        return " ".join(p.texto.strip() for p in self.palabras_en(inicio, fin)).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Transcripcion:
        return cls(
            idioma=d["idioma"],
            duracion=d["duracion"],
            segmentos=[Segmento.from_dict(s) for s in d.get("segmentos", [])],
            modelo=d.get("modelo", ""),
        )


@dataclass
class Escena:
    inicio: float
    fin: float


@dataclass
class Candidato:
    id: str
    inicio: float
    fin: float
    puntaje: float
    razon: str
    titulo: str = ""
    origen: str = "heuristica"  # heuristica | claude | buscar | manual
    aprobado: bool = True

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


@dataclass
class Meta:
    id: str
    fuente: str  # url o ruta original
    archivo: str = ""  # nombre del archivo de video dentro del proyecto
    duracion: float = 0.0
    titulo: str = ""
    creado: str = ""  # ISO 8601


# ---- JSON helpers -------------------------------------------------------------

def guardar_json(ruta: Path, datos: Any) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(datos, "__dataclass_fields__"):
        datos = asdict(datos)
    elif isinstance(datos, list):
        datos = [asdict(x) if hasattr(x, "__dataclass_fields__") else x for x in datos]
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


def cargar_json(ruta: Path) -> Any:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def candidatos_desde_json(datos: list[dict[str, Any]]) -> list[Candidato]:
    campos = Candidato.__dataclass_fields__
    return [Candidato(**{k: v for k, v in d.items() if k in campos}) for d in datos]
