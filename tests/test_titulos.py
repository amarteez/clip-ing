from clipping.seleccion.titulos import titulo_simple


def test_basico():
    assert titulo_simple("") == "" and titulo_simple("   ") == ""
    assert titulo_simple("mira este carro increíble. Luego otra") == "Mira este carro increíble"


def test_salta_frase_corta():
    assert titulo_simple("Ok. Esto es lo mejor que he visto.") == "Esto es lo mejor que he visto"


def test_recorta_en_palabra():
    t = titulo_simple("palabra " * 30, 60)
    assert len(t) <= 60 and t.endswith("…") and "palabr…" not in t
