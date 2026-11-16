from pathlib import Path

from clipping.config import SubtitulosCfg
from clipping.models import Palabra
from clipping.render.subtitulos import (
    agrupar_palabras,
    color_override,
    escapar_ass,
    escribir_ass,
    generar_ass,
    tiempo_ass,
)


def P(t, a, b):
    return Palabra(t, a, b)


def test_agrupar_maximo():
    ps = [P(str(i), i * 0.3, i * 0.3 + 0.25) for i in range(7)]
    g = agrupar_palabras(ps, 3)
    assert [len(x) for x in g] == [3, 3, 1]


def test_agrupar_hueco():
    ps = [P("a", 0, 0.3), P("b", 0.35, 0.6), P("c", 2.0, 2.3)]
    g = agrupar_palabras(ps, 5)
    assert [[p.texto for p in x] for x in g] == [["a", "b"], ["c"]]


def test_agrupar_puntuacion():
    for punt in ".?!,":
        ps = [P("hola" + punt, 0, 0.3), P("mundo", 0.3, 0.6)]
        assert len(agrupar_palabras(ps, 5)) == 2
    assert len(agrupar_palabras([P("a", 0, 0.3), P("b", 0.3, 0.6)], 5)) == 1


def test_agrupar_max_dur():
    ps = [P("a", 0, 1.0), P("b", 1.0, 2.0), P("c", 2.0, 3.0)]
    g = agrupar_palabras(ps, 5, max_dur=2.5)
    assert [len(x) for x in g] == [2, 1]


def test_agrupar_vacio():
    assert agrupar_palabras([], 3) == []


def test_tiempo_ass():
    assert tiempo_ass(0) == "0:00:00.00"
    assert tiempo_ass(-3) == "0:00:00.00"
    assert tiempo_ass(1.234) == "0:00:01.23"
    assert tiempo_ass(1.236) == "0:00:01.24"
    assert tiempo_ass(1.005) == "0:00:01.01"
    assert tiempo_ass(59.999) == "0:01:00.00"
    assert tiempo_ass(3725.5) == "1:02:05.50"


def test_escapar():
    assert escapar_ass("a\\b{c}\nd") == "a\\\\b\\{c\\} d"


def test_color_override():
    assert color_override("&H0000E5FF") == "&H00E5FF&"
    assert color_override("&H00FFFFFF") == "&HFFFFFF&"


CFG = SubtitulosCfg()


def _ass(palabras, ini=10.0, fin=20.0, cfg=CFG):
    return generar_ass(palabras, inicio_clip=ini, fin_clip=fin, cfg=cfg)


def _dialogos(s):
    return [x for x in s.splitlines() if x.startswith("Dialogue:")]


def test_ass_estructura():
    s = _ass([P("hola", 10.0, 10.5), P("mundo", 10.5, 11.0)])
    for sec in ("[Script Info]", "[V4+ Styles]", "[Events]"):
        assert sec in s
    assert "PlayResX: 1080" in s and "PlayResY: 1920" in s
    assert "ScaledBorderAndShadow: yes" in s and "WrapStyle: 2" in s
    assert "Style: Viral,Arial Black,92,&H00FFFFFF" in s
    assert ",-1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1" in s


def test_un_dialogue_por_palabra_y_resalte():
    s = _ass([P("hola", 10.0, 10.5), P("mundo", 10.5, 11.0), P("ya", 11.0, 11.4)])
    d = _dialogos(s)
    assert len(d) == 3
    assert d[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,Viral")
    assert d[1].startswith("Dialogue: 0,0:00:00.50,0:00:01.00,Viral")
    assert d[2].startswith("Dialogue: 0,0:00:01.00,0:00:01.40,Viral")
    assert "{\\fad(60,0)}" in d[0] and "{\\fad(60,0)}" not in d[1]
    assert "{\\c&H00E5FF&\\fscx115\\fscy115}HOLA{\\r} MUNDO YA" in d[0]
    assert "HOLA {\\c&H00E5FF&\\fscx115\\fscy115}MUNDO{\\r} YA" in d[1]


def test_fuera_de_rango_descartadas():
    s = _ass([P("antes", 5, 6), P("dentro", 12, 12.5), P("despues", 25, 26)])
    d = _dialogos(s)
    assert len(d) == 1
    assert "DENTRO" in d[0] and "ANTES" not in s and "DESPUES" not in s
    assert "0:00:02.00,0:00:02.50" in d[0]


def test_recorte_a_duracion():
    s = _ass([P("fin", 19.5, 21.0)])
    assert "0:00:09.50,0:00:10.00" in _dialogos(s)[0]


def test_mayusculas_tildes():
    s = _ass([P("canción", 10, 10.5), P("año", 10.5, 11)])
    assert "CANCIÓN" in s and "AÑO" in s
    s2 = _ass([P("canción", 10, 10.5)], cfg=SubtitulosCfg(mayusculas=False))
    assert "canción" in s2


def test_sin_huecos_en_grupo():
    s = _ass([P("a", 10.0, 10.3), P("b", 10.4, 10.6)])
    d = _dialogos(s)
    assert "0:00:00.00,0:00:00.40" in d[0]
    assert "0:00:00.40,0:00:00.60" in d[1]


def test_escribir_bom(tmp_path: Path):
    r = tmp_path / "x" / "a.ass"
    escribir_ass(r, "hola ñ")
    assert r.read_bytes().startswith(b"\xef\xbb\xbf")
    assert r.read_text(encoding="utf-8-sig") == "hola ñ"
