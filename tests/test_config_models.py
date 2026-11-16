from pathlib import Path

import pytest

from clipping.config import ConfigError, cargar_config
from clipping.models import (
    Candidato,
    Palabra,
    Segmento,
    Transcripcion,
    candidatos_desde_json,
    cargar_json,
    guardar_json,
)

RAIZ = Path(__file__).resolve().parents[1]


def test_config_repo_valida():
    cfg = cargar_config(RAIZ / "config.yaml", env={})
    assert cfg.seleccion.min_seg == 15
    assert cfg.seleccion.max_seg == 60
    assert cfg.render.reencuadre in ("centro", "blur")


def test_config_inexistente_usa_defaults(tmp_path):
    cfg = cargar_config(tmp_path / "no.yaml", env={})
    assert cfg.render.ancho == 1080


def test_env_sobreescribe_y_convierte_tipos(tmp_path):
    env = {
        "CLIP__RENDER__ENCODER": "libx264",
        "CLIP__SELECCION__N": "3",
        "CLIP__SELECCION__USAR_IA": "false",
        "CLIP__SELECCION__PESOS__VOLUMEN": "0.9",
        "CLIP__TRANSCRIPCION__IDIOMA": "null",
        "OTRA": "x",
    }
    cfg = cargar_config(tmp_path / "no.yaml", env=env)
    assert cfg.render.encoder == "libx264"
    assert cfg.seleccion.n == 3
    assert cfg.seleccion.usar_ia is False
    assert cfg.seleccion.pesos.volumen == 0.9
    assert cfg.transcripcion.idioma is None


def test_yaml_parcial(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("seleccion:\n  n: 4\n  pesos:\n    escenas: 0.5\n", encoding="utf-8")
    cfg = cargar_config(p, env={})
    assert cfg.seleccion.n == 4
    assert cfg.seleccion.pesos.escenas == 0.5
    assert cfg.seleccion.pesos.volumen == 0.40


@pytest.mark.parametrize(
    "yaml_txt",
    [
        "clave_rara: 1\n",
        "seleccion:\n  min_seg: 70\n",
        "render:\n  encoder: h265\n",
        "render:\n  reencuadre: zoom\n",
        "transcripcion:\n  compute_type: float16\n",
        "seleccion: 5\n",
    ],
)
def test_config_invalida(tmp_path, yaml_txt):
    p = tmp_path / "c.yaml"
    p.write_text(yaml_txt, encoding="utf-8")
    with pytest.raises(ConfigError):
        cargar_config(p, env={})


def _transcripcion():
    return Transcripcion(
        idioma="es",
        duracion=10.0,
        segmentos=[
            Segmento(0.0, 2.0, "hola mundo", [Palabra("hola", 0.0, 0.8), Palabra("mundo", 0.9, 1.8)]),
            Segmento(3.0, 4.0, "otra", [Palabra("otra", 3.0, 3.5, 0.7)]),
        ],
    )


def test_transcripcion_roundtrip(tmp_path):
    t = _transcripcion()
    guardar_json(tmp_path / "t.json", t)
    t2 = Transcripcion.from_dict(cargar_json(tmp_path / "t.json"))
    assert t2 == t
    assert [p.texto for p in t2.palabras()] == ["hola", "mundo", "otra"]
    assert t2.texto_en(0.5, 3.3) == "mundo otra"


def test_candidatos_roundtrip_ignora_campos_extra(tmp_path):
    cs = [Candidato("c01", 10, 40, 0.8, "pico de volumen", titulo="¡Brutal!")]
    guardar_json(tmp_path / "c.json", cs)
    datos = cargar_json(tmp_path / "c.json")
    datos[0]["extra"] = "ignorar"
    cs2 = candidatos_desde_json(datos)
    assert cs2 == cs
    assert cs2[0].duracion == 30
