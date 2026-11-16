from datetime import datetime

import pytest

from clipping.models import Candidato, Escena, Palabra, Segmento, Transcripcion
from clipping.proyecto import Proyecto, slug_id

T0 = datetime(2025, 3, 4, 5, 6, 7)


def test_slug_archivo_con_acentos():
    assert slug_id(r"C:\Videos\Canción Ñandú: Épico!.mp4", T0) == "20250304-050607-cancion-nandu-epico"


def test_slug_youtube():
    assert slug_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", T0) == "20250304-050607-dqw4w9wgxcq"
    assert slug_id("https://youtu.be/AbC_123", T0) == "20250304-050607-abc-123"


def test_slug_largo_y_vacio():
    s = slug_id("a" * 100 + ".mp4", T0)
    assert len(s.split("-", 2)[2]) == 40
    assert slug_id("???.mp4", T0).endswith("-video")


def test_crear_abrir_roundtrip(tmp_path):
    p = Proyecto.crear(tmp_path, "mi video.mp4", T0)
    assert p.clips_dir.is_dir() and p.subs_dir.is_dir()
    m = p.meta()
    assert m.id == p.id == "20250304-050607-mi-video" and m.fuente == "mi video.mp4"
    m.archivo = "fuente.mp4"
    p.guardar_meta(m)
    assert p.video == p.raiz / "fuente.mp4"

    assert p.transcripcion() is None and p.escenas() == [] and p.candidatos() == []
    t = Transcripcion("es", 10.0, [Segmento(0, 1, "hola", [Palabra("hola", 0, 1, 0.9)])], "small")
    p.guardar_transcripcion(t)
    assert p.transcripcion() == t
    p.guardar_escenas([Escena(0, 5), Escena(5, 10)])
    assert p.escenas() == [Escena(0, 5), Escena(5, 10)]
    c = [Candidato("c1", 1, 20, 0.8, "r", titulo="t")]
    p.guardar_candidatos(c)
    assert p.candidatos() == c

    assert Proyecto.abrir(tmp_path, p.id).raiz == p.raiz
    assert Proyecto.abrir(tmp_path / "otra", str(p.raiz)).raiz == p.raiz


def test_abrir_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError, match="nada"):
        Proyecto.abrir(tmp_path, "nada")


def test_listar_orden_desc(tmp_path):
    a = Proyecto.crear(tmp_path, "a.mp4", datetime(2025, 1, 1))
    b = Proyecto.crear(tmp_path, "b.mp4", datetime(2025, 2, 1))
    (tmp_path / "carpeta_suelta").mkdir()
    assert [p.id for p in Proyecto.listar(tmp_path)] == [b.id, a.id]
    assert Proyecto.listar(tmp_path / "no_existe") == []
