from clipping.config import SeleccionCfg
from clipping.models import Escena, Palabra
from clipping.seleccion.heuristica import (
    normalizar,
    seleccionar,
    serie_densidad_palabras,
    serie_escenas,
)

DUR = 300.0


def _palabras(hasta: float = DUR, paso: float = 0.4) -> list[Palabra]:
    n = int(hasta / paso) - 1
    return [Palabra("w", i * paso, i * paso + 0.3) for i in range(n)]


def _rms() -> list[float]:
    return [0.9 if 100 <= t < 110 else 0.1 for t in range(300)]


def _sel(**kw):
    base = dict(
        rms=_rms(), paso_rms=1.0, palabras=_palabras(), escenas=[Escena(0, 300)], cfg=SeleccionCfg()
    )
    base.update(kw)
    return seleccionar(DUR, **base)


def test_series():
    d = serie_densidad_palabras([Palabra("a", 0.1, 0.3), Palabra("b", 0.5, 0.7)], 3)
    assert d == [2.0, 0.0, 0.0]
    e = serie_escenas([Escena(0, 5), Escena(5, 9), Escena(9, 12)], 12)
    assert len(e) == 12 and e[5] == 1.0 and e[9] == 1.0 and e[0] == 0.0 and sum(e) == 2


def test_normalizar():
    assert normalizar([2, 4, 6]) == [0.0, 0.5, 1.0]
    assert normalizar([3, 3]) == [0.0, 0.0]
    assert normalizar([]) == []


def test_pico_en_top():
    r = _sel()
    top = r[0]
    assert top.inicio <= 100 and top.fin >= 110
    assert top.origen == "heuristica" and top.titulo == ""
    assert "volumen" in top.razon.lower()


def test_formato_candidatos():
    r = _sel()
    assert [c.id for c in r] == [f"c{i:02d}" for i in range(1, len(r) + 1)]
    ps = [c.puntaje for c in r]
    assert ps == sorted(ps, reverse=True)
    for c in r:
        assert 0 <= c.puntaje <= 1 and c.puntaje == round(c.puntaje, 3)
        assert 15 - 1e-6 <= c.duracion <= 60 + 1e-6
        assert 0 <= c.inicio < c.fin <= DUR
    ordenados = sorted(r, key=lambda c: c.inicio)
    for a, b in zip(ordenados, ordenados[1:]):
        assert b.inicio >= a.fin + 5 - 1e-6


def test_n_respetado():
    assert len(_sel(n=3)) <= 3
    assert len(_sel(n=1)) == 1
    assert len(_sel()) <= SeleccionCfg().n


def test_rms_con_paso_distinto():
    rms = [0.9 if 100 <= i * 0.5 < 110 else 0.1 for i in range(600)]  # 600 muestras = 300 s
    r = _sel(rms=rms, paso_rms=0.5)
    assert r[0].inicio <= 100 and r[0].fin >= 110


def test_video_corto():
    r = seleccionar(
        10.0, rms=[0.1] * 10, paso_rms=1.0, palabras=_palabras(10), escenas=[], cfg=SeleccionCfg()
    )
    assert len(r) == 1 and (r[0].inicio, r[0].fin) == (0, 10.0)


def test_sin_datos():
    cfg = SeleccionCfg()
    assert seleccionar(300, rms=None, paso_rms=1, palabras=[], escenas=[], cfg=cfg) == []
    assert seleccionar(0, rms=[1.0], paso_rms=1, palabras=[], escenas=[], cfg=cfg) == []


def test_solo_palabras_y_constantes():
    r = _sel(rms=None)
    assert all(0 <= c.puntaje <= 1 for c in r)
    r = _sel(rms=[0.5] * 300, palabras=[], escenas=[])
    assert isinstance(r, list)


def test_determinismo():
    assert _sel() == _sel()
