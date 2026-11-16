from types import SimpleNamespace as NS

from clipping.transcripcion import convertir_whisper, registrar_dlls_cuda


def test_convertir():
    segs = [
        NS(start=0.0, end=2.0, text=" Hola mundo ", words=[
            NS(word=" Hola", start=0.0, end=0.5, probability=0.9),
            NS(word=" mundo", start=0.6, end=1.0, probability=0.8),
            NS(word=" ", start=1.0, end=1.1, probability=0.1),
        ]),
        NS(start=2.0, end=3.0, text="sin palabras", words=None),
    ]
    vistos = []
    t = convertir_whisper(iter(segs), "es", 10.0, "small", lambda a, b: vistos.append((a, b)))
    assert t.idioma == "es" and t.duracion == 10.0 and t.modelo == "small"
    assert t.segmentos[0].texto == "Hola mundo"
    assert [p.texto for p in t.segmentos[0].palabras] == ["Hola", "mundo"]
    assert t.segmentos[0].palabras[0].prob == 0.9
    assert t.segmentos[1].palabras == []
    assert vistos == [(2.0, 10.0), (3.0, 10.0)]


def test_registrar_dlls_idempotente():
    registrar_dlls_cuda()
    registrar_dlls_cuda()
