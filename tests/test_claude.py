import json

import pytest

from clipping.config import ClaudeCfg, SeleccionCfg
from clipping.errores import ErrorClaude
from clipping.models import Escena, Palabra, Segmento, Transcripcion
from clipping.seleccion.claude import (
    buscar,
    candidatos_desde_claude,
    formatear_transcripcion,
    llamar_claude,
    parsear_respuesta,
    prompt_auto,
    prompt_buscar,
    seleccionar_auto,
)

CLIPS = {"clips": [{"inicio": 10, "fin": 40, "puntaje": 0.9, "razon": "r", "titulo": "T"}]}


def _t(nseg=100, texto="hola mundo esto es una prueba"):
    segs = []
    for i in range(nseg):
        a = i * 3.0
        palabras = [Palabra(w, a + j * 0.4, a + j * 0.4 + 0.3) for j, w in enumerate(texto.split())]
        segs.append(Segmento(a, a + 3, texto, palabras))
    return Transcripcion("es", nseg * 3.0, segs, "small")


def test_parsear_envoltorio_json():
    env = json.dumps({"type": "result", "is_error": False, "result": json.dumps(CLIPS)})
    r = parsear_respuesta(env)
    assert r[0]["inicio"] == 10 and r[0]["fin"] == 40 and r[0]["titulo"] == "T"


def test_parsear_bloque_y_basura():
    txt = "Claro, aquí va:\n```json\n" + json.dumps(CLIPS) + "\n```\nSuerte {x}"
    assert len(parsear_respuesta(txt)) == 1


def test_parsear_envoltorio_con_bloque():
    env = json.dumps({"result": "```json\n" + json.dumps(CLIPS) + "\n```"})
    assert len(parsear_respuesta(env)) == 1


def test_parsear_tiempos_mmss():
    txt = json.dumps({"clips": [{"inicio": "01:10", "fin": "1:01:40"}]})
    r = parsear_respuesta(txt)
    assert r[0]["inicio"] == 70 and r[0]["fin"] == 3700 and r[0]["puntaje"] == 0.5


def test_parsear_descarta_invalidos():
    txt = json.dumps({"clips": [
        {"inicio": 50, "fin": 10}, {"inicio": "x", "fin": 5}, "hola", {"fin": 3},
        {"inicio": True, "fin": 9}, {"inicio": 1, "fin": 20, "puntaje": 7},
    ]})
    r = parsear_respuesta(txt)
    assert len(r) == 1 and r[0]["puntaje"] == 1.0


def test_parsear_array_y_nada():
    assert len(parsear_respuesta('[{"inicio":1,"fin":2}]')) == 1
    for malo in ("", "no hay json", '{"clips": []}', '{"clips":[{"inicio":9,"fin":1}]}'):
        with pytest.raises(ErrorClaude):
            parsear_respuesta(malo)


def test_llamar_claude_stdin_y_modelo():
    visto = {}

    def correr(cmd, stdin, timeout):
        visto.update(cmd=cmd, stdin=stdin, timeout=timeout)
        return 0, json.dumps({"is_error": False, "result": "OK"}), ""

    cfg = ClaudeCfg(modelo="sonnet", timeout_seg=42)
    assert llamar_claude("mi prompt", cfg, correr=correr) == "OK"
    assert visto["stdin"] == "mi prompt" and visto["timeout"] == 42
    assert visto["cmd"][1:4] == ["-p", "--output-format", "json"]
    assert visto["cmd"][-2:] == ["--model", "sonnet"]
    assert "mi prompt" not in visto["cmd"]


def test_llamar_claude_errores():
    with pytest.raises(ErrorClaude):
        llamar_claude("p", ClaudeCfg(), correr=lambda c, s, t: (1, "", "boom"))
    err = json.dumps({"is_error": True, "result": "límite"})
    with pytest.raises(ErrorClaude):
        llamar_claude("p", ClaudeCfg(), correr=lambda c, s, t: (0, err, ""))


def test_llamar_claude_no_instalado():
    with pytest.raises(ErrorClaude):
        llamar_claude("p", ClaudeCfg(comando="no-existe-claude-xyz"))


def test_formatear_trunca():
    t = _t(200, "palabra " * 30)
    completo = formatear_transcripcion(t, max_chars=10**9)
    corto = formatear_transcripcion(t, max_chars=3000)
    assert len(completo) > 3000 and len(corto) <= 3000
    assert corto.startswith("[00:00-") and "…" in corto
    assert "[09:" in corto  # cubre hasta el final, no solo el principio


def test_formatear_usa_texto_es():
    t = Transcripcion("en", 5, [Segmento(0, 5, "hello", [], texto_es="hola")])
    assert formatear_transcripcion(t) == "[00:00-00:05] hola"


def test_prompts():
    cfg = SeleccionCfg(min_seg=15, max_seg=60)
    p = prompt_auto(_t(5), n=7, cfg=cfg, contexto="canal de GTA 6")
    assert "7" in p and "15" in p and "60" in p and "GTA 6" in p and "TikTok" in p
    q = prompt_buscar(_t(5), "el choque del carro", n=3, cfg=cfg)
    assert "choque del carro" in q and "3" in q and "multiling" in q


def test_candidatos_y_flujo():
    t = _t(100)
    items = parsear_respuesta(json.dumps({"clips": [
        {"inicio": 10, "fin": 40, "puntaje": 0.9, "titulo": "A"},
        {"inicio": 12, "fin": 38, "puntaje": 0.5},
        {"inicio": 200, "fin": 290, "puntaje": 0.7},
    ]}))
    cfg = SeleccionCfg()
    c = candidatos_desde_claude(items, origen="claude", t=t, escenas=[Escena(0, 300)], cfg=cfg)
    assert [x.id for x in c] == ["c01", "c02"]
    assert all(x.origen == "claude" and x.fin <= t.duracion for x in c)
    assert all(cfg.min_seg <= x.duracion <= cfg.max_seg for x in c)

    resp = json.dumps({"result": json.dumps(CLIPS)})

    def fake(cmd, s, to):
        return 0, resp, ""

    r = seleccionar_auto(t, [], n=5, cfg_sel=cfg, cfg_claude=ClaudeCfg(), correr=fake)
    assert len(r) == 1
    r = buscar(t, [], "algo", n=5, cfg_sel=cfg, cfg_claude=ClaudeCfg(), correr=fake)
    assert len(r) == 1
    with pytest.raises(ErrorClaude):
        seleccionar_auto(
            t, [], n=1, cfg_sel=cfg, cfg_claude=ClaudeCfg(), correr=lambda c, s, to: (2, "", "x")
        )
