from clipping.config import Config
from clipping.doctor import ejecutar_doctor, formatear_reporte


def nada(cmd):
    return 127, ""


def completo(cmd):
    if cmd[0] == "nvidia-smi":
        return 0, "NVIDIA GeForce GTX 1060 6GB, 6144, 546.33, 6.1\n"
    if "-encoders" in cmd:
        return 0, " V....D h264_nvenc"
    if "-version" in cmd or "--version" in cmd:
        return 0, f"{cmd[0]} version 7.0.1 Copyright"
    return 0, ""


def disco(_):
    return (100 * 1024**3, 0, 200 * 1024**3)


def test_doctor_sin_nada_no_crashea():
    ch, rec = ejecutar_doctor(Config(), ejecutar=nada)
    estados = {c.nombre: c.estado for c in ch}
    assert estados["ffmpeg"] == "error"
    assert estados["GPU NVIDIA"] == "aviso"
    assert rec.dispositivo == "cpu"
    rep = formatear_reporte(ch, rec)
    assert "[XX]" in rep and "winget install Gyan.FFmpeg" in rep
    assert "Configuración recomendada" in rep and "modelo: small" in rep
    assert "libx264" in rep


def test_doctor_completo():
    ch, rec = ejecutar_doctor(Config(), ejecutar=completo, uso_disco=disco)
    d = {c.nombre: c for c in ch}
    assert d["ffmpeg"].estado == "ok" and "7.0.1" in d["ffmpeg"].detalle
    assert "sin float16" in d["GPU NVIDIA"].detalle
    assert d["NVENC"].estado == "ok"
    assert d["Espacio en disco"].estado == "ok"
    assert rec.modelo == "medium"
    rep = formatear_reporte(ch, rec)
    assert "encoder: h264_nvenc" in rep and "compute_type: int8" in rep


def test_python_y_disco():
    ch, _ = ejecutar_doctor(Config(), ejecutar=nada, version_python=(3, 12, 1),
                            uso_disco=lambda _: (0, 0, 30 * 1024**3))
    d = {c.nombre: c for c in ch}
    assert d["Python"].estado == "aviso" and "3.11" in d["Python"].detalle
    assert d["Espacio en disco"].estado == "aviso"
    ch, _ = ejecutar_doctor(Config(), ejecutar=nada, version_python=(3, 10, 0),
                            uso_disco=lambda _: (0, 0, 5 * 1024**3))
    d = {c.nombre: c for c in ch}
    assert d["Python"].estado == "error" and d["Espacio en disco"].estado == "error"


def test_nvenc_prueba_falla():
    def ej(cmd):
        if "-f" in cmd and "lavfi" in cmd:
            return 1, "fallo"
        return completo(cmd)

    ch, _ = ejecutar_doctor(Config(), ejecutar=ej, uso_disco=disco)
    d = {c.nombre: c for c in ch}
    assert d["NVENC"].estado == "aviso"
    ch, _ = ejecutar_doctor(Config(), ejecutar=ej, uso_disco=disco, probar_encoder=False)
    assert {c.nombre: c for c in ch}["NVENC"].estado == "ok"
