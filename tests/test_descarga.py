from pathlib import Path

import pytest

from clipping.descarga import duracion_video, es_url, obtener_fuente
from clipping.errores import ErrorFFmpeg


def test_es_url():
    assert es_url("https://youtu.be/x") and es_url("HTTP://a.b")
    assert not es_url("C:\\videos\\a.mp4") and not es_url("a.mp4")


def test_local_sin_copiar(tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    archivo, titulo = obtener_fuente(str(v), tmp_path / "p")
    assert Path(archivo).is_absolute() and Path(archivo) == v.resolve()
    assert titulo == "v" and not (tmp_path / "p").exists()


def test_local_copiar(tmp_path):
    v = tmp_path / "v.mkv"
    v.write_bytes(b"abc")
    archivo, _ = obtener_fuente(str(v), tmp_path / "p", copiar=True)
    assert archivo == "fuente.mkv"
    assert (tmp_path / "p" / archivo).read_bytes() == b"abc"


def test_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        obtener_fuente(str(tmp_path / "no.mp4"), tmp_path)


def test_duracion():
    visto = {}

    def ej(cmd):
        visto["cmd"] = cmd
        return 0, "123.456\n"

    assert duracion_video(Path("a.mp4"), ejecutar=ej) == 123.456
    assert visto["cmd"][0] == "ffprobe"
    with pytest.raises(ErrorFFmpeg):
        duracion_video(Path("a.mp4"), ejecutar=lambda c: (1, "err"))
    with pytest.raises(ErrorFFmpeg):
        duracion_video(Path("a.mp4"), ejecutar=lambda c: (0, "N/A"))
