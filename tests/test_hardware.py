from clipping.config import TranscripcionCfg
from clipping.hardware import (
    GPU,
    detectar_gpus,
    es_pascal,
    nvenc_disponible,
    probar_nvenc,
    recomendar_whisper,
    resolver_transcripcion,
)

G6 = "NVIDIA GeForce GTX 1060 6GB, 6144, 546.33, 6.1"
G3 = "NVIDIA GeForce GTX 1060 3GB, 3072, 546.33, 6.1"


def falso(codigo: int, salida: str = ""):
    return lambda cmd: (codigo, salida)


def test_detecta_1060_6gb():
    gpus = detectar_gpus(falso(0, G6 + "\n"))
    assert gpus == [GPU("NVIDIA GeForce GTX 1060 6GB", 6144, "546.33", "6.1")]


def test_detecta_3gb():
    assert detectar_gpus(falso(0, G3))[0].vram_mb == 3072


def test_sin_nvidia_smi():
    llamadas = []

    def ej(cmd):
        llamadas.append(cmd)
        return 127, ""

    assert detectar_gpus(ej) == []
    assert len(llamadas) == 1


def test_reintenta_sin_compute_cap():
    def ej(cmd):
        if "compute_cap" in cmd[1]:
            return 2, "Field compute_cap is not a valid field"
        return 0, "NVIDIA GeForce GTX 1060 6GB, 6144, 391.01\n"

    gpus = detectar_gpus(ej)
    assert len(gpus) == 1 and gpus[0].compute_cap is None
    assert es_pascal(gpus[0])  # por nombre


def test_salida_basura():
    assert detectar_gpus(falso(0, "basura sin comas\n\n???")) == []
    assert detectar_gpus(falso(0, "a, b, c, d")) == []
    assert detectar_gpus(falso(1, "error")) == []


def test_es_pascal():
    assert es_pascal(GPU("X", 1, "1", "6.1"))
    assert es_pascal(GPU("Tesla P100", 1, "1", None))
    assert es_pascal(GPU("NVIDIA TITAN Xp", 1, "1", None))
    assert not es_pascal(GPU("NVIDIA GeForce RTX 3060", 12288, "1", "8.6"))


def test_recomendaciones():
    r6 = recomendar_whisper(detectar_gpus(falso(0, G6)))
    assert (r6.modelo, r6.dispositivo, r6.compute_type) == ("medium", "cuda", "int8")
    r3 = recomendar_whisper(detectar_gpus(falso(0, G3)))
    assert (r3.modelo, r3.dispositivo, r3.compute_type) == ("small", "cuda", "int8")
    r0 = recomendar_whisper([])
    assert (r0.modelo, r0.dispositivo, r0.compute_type) == ("small", "cpu", "int8")
    assert r6.motivo and "float16" not in r6.compute_type


def test_resolver_auto_y_explicito():
    gpus = [GPU("GTX 1060", 6144, "1", "6.1")]
    assert resolver_transcripcion(TranscripcionCfg(), gpus).modelo == "medium"
    r = resolver_transcripcion(TranscripcionCfg(modelo="base", compute_type="int8"), gpus)
    assert (r.modelo, r.dispositivo, r.compute_type) == ("base", "cuda", "int8")


def test_resolver_cuda_sin_gpu():
    r = resolver_transcripcion(TranscripcionCfg(modelo="small", dispositivo="cuda"), [])
    assert r.dispositivo == "cpu" and "cuda" in r.motivo


def test_nvenc():
    assert nvenc_disponible("ffmpeg", falso(0, " V....D h264_nvenc NVIDIA NVENC"))
    assert not nvenc_disponible("ffmpeg", falso(0, " V....D libx264"))
    assert not nvenc_disponible("ffmpeg", falso(127))
    assert probar_nvenc("ffmpeg", falso(0))
    assert not probar_nvenc("ffmpeg", falso(1, "error"))
