import pytest

from clipping.models import Candidato, Escena, Palabra
from clipping.seleccion.tiempos import (
    ajustar_duracion,
    aplicar_padding,
    formatear_tiempo,
    normalizar_candidato,
    parsear_tiempo,
    quitar_solapes,
    snap_a_escenas,
    snap_a_palabras,
)


def _palabras(n: int = 200, paso: float = 0.4, dur: float = 0.3) -> list[Palabra]:
    return [Palabra("w", i * paso, i * paso + dur) for i in range(n)]


def test_snap_palabras_inicio_dentro_de_palabra():
    p = [Palabra("a", 10.0, 10.5), Palabra("b", 10.6, 11.0)]
    i, _ = snap_a_palabras(10.3, 20.0, p)
    assert i == 10.0


def test_snap_palabras_fin_dentro_de_palabra():
    p = [Palabra("a", 10.0, 10.5), Palabra("b", 10.6, 11.0)]
    _, f = snap_a_palabras(0.0, 10.8, p)
    assert f == 11.0


def test_snap_palabras_cercana_y_sin_palabras_cerca():
    p = [Palabra("a", 10.0, 10.5)]
    assert snap_a_palabras(11.0, 12.0, p)[0] == 10.0
    assert snap_a_palabras(50.0, 60.0, p) == (50.0, 60.0)
    assert snap_a_palabras(5.0, 6.0, []) == (5.0, 6.0)


def test_snap_palabras_no_invierte():
    p = [Palabra("a", 10.0, 10.5)]
    i, f = snap_a_palabras(10.2, 10.3, p)
    assert f > i


def test_snap_escenas():
    esc = [Escena(0, 20), Escena(20, 50), Escena(50, 90)]
    assert snap_a_escenas(20.6, 49.5, esc) == (20.0, 50.0)
    assert snap_a_escenas(22.0, 52.0, esc) == (22.0, 52.0)
    assert snap_a_escenas(0.5, 80.0, esc) == (0.5, 80.0)  # corte en 0 se ignora


def test_ajustar_duracion_expande_simetrico():
    assert ajustar_duracion(100, 110, 20, 60, 300) == (95, 115)


def test_ajustar_duracion_bordes():
    assert ajustar_duracion(1, 6, 20, 60, 300) == (0, 20)
    assert ajustar_duracion(295, 299, 20, 60, 300) == (280, 300)


def test_ajustar_duracion_recorta_y_video_corto():
    assert ajustar_duracion(10, 100, 15, 60, 300) == (10, 70)
    assert ajustar_duracion(1, 5, 15, 60, 10) == (0, 10)


def test_padding():
    assert aplicar_padding(0.1, 299.9, 0.3, 300) == (0.0, 300.0)
    assert aplicar_padding(10, 20, 0.5, 300) == (9.5, 20.5)


def _c(id, i, f, p):
    return Candidato(id=id, inicio=i, fin=f, puntaje=p, razon="")


def test_quitar_solapes():
    cs = [_c("a", 0, 30, 0.5), _c("b", 20, 50, 0.9), _c("c", 52, 80, 0.4), _c("d", 90, 120, 0.7)]
    r = quitar_solapes(cs, 5)
    assert [c.id for c in r] == ["b", "d"]  # c queda a 2 s de b
    assert [c.id for c in quitar_solapes(cs, 0)] == ["b", "d", "c"]


def test_normalizar_candidato_garantias():
    pal = _palabras()
    esc = [Escena(0, 100), Escena(100, 300)]
    for i, f in [(0, 5), (99.3, 112), (290, 300), (50, 200), (150, 150.5)]:
        c = _c("x", i, f, 0.5)
        n = normalizar_candidato(
            c, palabras=pal, escenas=esc, min_seg=15, max_seg=60, padding=0.3, duracion_total=300
        )
        assert 15 - 1e-6 <= n.fin - n.inicio <= 60 + 1e-6
        assert 0 <= n.inicio < n.fin <= 300
        assert n.inicio == round(n.inicio, 3) and n.fin == round(n.fin, 3)
        assert n.id == "x"
    assert c.inicio == 150  # original intacto


def test_normalizar_candidato_video_corto():
    c = _c("x", 1, 3, 0.5)
    n = normalizar_candidato(
        c, palabras=[], escenas=[], min_seg=15, max_seg=60, padding=0.3, duracion_total=10
    )
    assert (n.inicio, n.fin) == (0, 10)


def test_formatear_parsear():
    assert formatear_tiempo(3723.5) == "01:02:03.500"
    assert formatear_tiempo(0) == "00:00:00.000"
    assert parsear_tiempo("45") == 45
    assert parsear_tiempo("1:30") == 90
    assert parsear_tiempo("01:02:03.5") == 3723.5
    assert parsear_tiempo(formatear_tiempo(98.765)) == pytest.approx(98.765)


@pytest.mark.parametrize("mal", ["", "abc", "1:2:3:4", "-5", "1:-2", "1.5:20", "1:", ":30"])
def test_parsear_invalido(mal):
    with pytest.raises(ValueError):
        parsear_tiempo(mal)
