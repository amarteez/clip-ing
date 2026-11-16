from pathlib import Path

import pytest

from clipping.config import RenderCfg
from clipping.render.ffmpeg import (
    comando_a_texto,
    construir_comando_clip,
    elegir_encoder,
    ruta_filtro_ass,
)
from clipping.render.reencuadre import construir_filtro, filtro_blur, filtro_centro


def test_filtro_centro():
    f = filtro_centro(1080, 1920)
    assert f == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"


def test_filtro_blur():
    f = filtro_blur(1080, 1920, 30)
    assert f.startswith("[0:v]split=2[bg][fg];") and f.endswith("[v0]")
    # desenfoque a 1/4 de resolución (sigma/4) y reescalado al tamaño final
    assert "crop=270:480,gblur=sigma=7.5,scale=1080:1920" in f
    assert "eq=brightness=-0.08" in f
    assert "scale=1080:-2" in f and "overlay=(W-w)/2:(H-h)/2" in f


def test_construir_filtro():
    c = construir_filtro("centro", 1080, 1920, 30)
    assert c.startswith("[0:v]") and c.endswith("[v0]")
    assert construir_filtro("blur", 1080, 1920, 30).endswith("[v0]")
    with pytest.raises(ValueError):
        construir_filtro("zoom", 1080, 1920, 30)


def test_ruta_ass_windows():
    r = ruta_filtro_ass(Path(r"C:\Users\x\clip 1\sub.ass"))
    assert r == "subtitles='C\\:/Users/x/clip 1/sub.ass'"
    assert "\\'" in ruta_filtro_ass(Path("/tmp/it's.ass"))


def test_elegir_encoder():
    assert elegir_encoder("auto", True) == "h264_nvenc"
    assert elegir_encoder("auto", False) == "libx264"
    assert elegir_encoder("h264_nvenc", False) == "libx264"
    assert elegir_encoder("h264_nvenc", True) == "h264_nvenc"
    assert elegir_encoder("libx264", True) == "libx264"


def _cmd(encoder, ass=Path("s.ass")):
    return construir_comando_clip(
        entrada=Path("in.mp4"), salida=Path("out.mp4"), inicio=12.3456,
        fin=42.0, ass=ass, cfg=RenderCfg(), encoder=encoder,
    )


def test_comando_x264():
    c = _cmd("libx264")
    assert c[0] == "ffmpeg" and c[-1] == "out.mp4"
    assert c.index("-ss") < c.index("-i")
    assert c[c.index("-ss") + 1] == "12.346"
    assert c[c.index("-t") + 1] == "29.654"
    assert "libx264" in c and c[c.index("-crf") + 1] == "20"
    assert "h264_nvenc" not in c
    fc = c[c.index("-filter_complex") + 1]
    assert "[v0]subtitles=" in fc and fc.endswith("fps=30[v]")
    assert "[v]" in c and "0:a?" in c and "+faststart" in c


def test_comando_nvenc():
    c = _cmd("h264_nvenc")
    assert "h264_nvenc" in c and c[c.index("-cq") + 1] == "23"
    assert c[c.index("-preset") + 1] == "p5"
    assert "-tune" not in c and "-crf" not in c


def test_comando_sin_ass():
    c = _cmd("libx264", ass=None)
    fc = c[c.index("-filter_complex") + 1]
    assert "subtitles" not in fc and fc.endswith(";[v0]fps=30[v]")


def test_comando_a_texto():
    t = comando_a_texto(["ffmpeg", "-i", "a b.mp4", "x"])
    assert t == "ffmpeg -i 'a b.mp4' x"
