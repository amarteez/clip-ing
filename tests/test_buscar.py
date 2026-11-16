from clipping.config import SeleccionCfg
from clipping.models import Palabra, Segmento, Transcripcion
from clipping.seleccion.buscar import buscar_por_texto, normalizar_texto


def _t():
    palabras = []
    frase = "hoy vamos a ver el choque del carro rojo en la autopista".split()
    for i in range(300):
        palabras.append(Palabra("blah", i * 0.5, i * 0.5 + 0.3))
    for j, w in enumerate(frase):
        palabras.append(Palabra(w, 150 + j * 0.5, 150 + j * 0.5 + 0.3))
    for i in range(100):
        palabras.append(Palabra("nada", 160 + i * 0.5, 160 + i * 0.5 + 0.3))
    return Transcripcion("es", 220, [Segmento(0, 220, "x", palabras)], "small")


def test_normalizar():
    assert normalizar_texto("¡Canción, ÉPICA!") == "cancion epica"


def test_busca_coincidencia():
    r = buscar_por_texto(_t(), "el choque del Carro", n=3, cfg=SeleccionCfg(), escenas=[])
    assert r and r[0].origen == "buscar" and r[0].id == "c01"
    assert r[0].inicio <= 155 <= r[0].fin
    assert r[0].razon.startswith("Coincide:") and "choque" in r[0].razon
    assert r[0].puntaje > 0.9
    assert all(a.fin <= b.inicio or b.fin <= a.inicio for a in r for b in r if a is not b)


def test_sin_coincidencia_o_solo_stopwords():
    assert buscar_por_texto(_t(), "dragón", n=3, cfg=SeleccionCfg(), escenas=[]) == []
    assert buscar_por_texto(_t(), "el de la", n=3, cfg=SeleccionCfg(), escenas=[]) == []


def test_busca_en_texto_es():
    seg = Segmento(0, 100, "x", [Palabra("w", i, i + 0.5) for i in range(100)])
    seg.texto_es = "aquí aparece el helicóptero"
    t = Transcripcion("en", 100, [seg])
    assert buscar_por_texto(t, "helicoptero", n=2, cfg=SeleccionCfg(), escenas=[])
