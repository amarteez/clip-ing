import math

from clipping.deteccion.audio import rms_dbfs


def test_silencio():
    assert rms_dbfs([0] * 100) == -90.0
    assert rms_dbfs([]) == -90.0


def test_onda_completa():
    onda = [int(32767 * math.sin(2 * math.pi * i / 100)) for i in range(1000)]
    assert abs(rms_dbfs(onda) - (-3.0)) < 0.1


def test_cuadrada_cero_db():
    assert abs(rms_dbfs([32767, -32767] * 50)) < 0.01
