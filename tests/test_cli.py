"""Tests del CLI con un proyecto sintético ya analizado (no requiere ffmpeg ni whisper)."""

import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from clipping.cli import app
from clipping.models import Escena, Palabra, Segmento, Transcripcion, guardar_json
from clipping.proyecto import Proyecto

runner = CliRunner()
DUR = 300.0


@pytest.fixture
def proyecto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLIP__PROYECTOS_DIR", str(tmp_path / "proyectos"))
    monkeypatch.setenv("CLIP__SELECCION__USAR_IA", "false")
    p = Proyecto.crear(tmp_path / "proyectos", "C:/videos/Meet de carros GTA.mp4")
    p.guardar_meta(replace(p.meta(), archivo=str(tmp_path / "fuente.mp4"), duracion=DUR))

    palabras, segs = [], []
    textos = ["mira", "ese", "carro", "está", "brutal", "vamos", "al", "meet", "ahora"]
    t = 0.0
    while t < DUR - 1:
        ws = []
        for k in range(6):
            w = Palabra(textos[int(t + k) % len(textos)], t, t + 0.3)
            ws.append(w)
            t += 0.4
        if 120 <= t <= 135:
            ws.append(Palabra("infernus", t, t + 0.3))
            t += 0.4
        segs.append(Segmento(ws[0].inicio, ws[-1].fin, " ".join(w.texto for w in ws), ws))
        t += 1.0
    p.guardar_transcripcion(Transcripcion("es", DUR, segs, "small"))
    rms = [-40.0] * int(DUR / 0.5)
    for i in range(200, 220):  # pico en 100–110 s
        rms[i] = -5.0
    guardar_json(p.audio_json, {"paso": 0.5, "rms": rms})
    p.guardar_escenas([Escena(0, 60), Escena(60, 180), Escena(180, DUR)])
    return p


def test_auto_heuristico_y_render_dry_run(proyecto):
    r = runner.invoke(app, ["auto", proyecto.id, "--n", "3", "--sin-ia"])
    assert r.exit_code == 0, r.output
    cands = json.loads(proyecto.candidatos_json.read_text(encoding="utf-8"))
    assert 1 <= len(cands) <= 3
    for c in cands:
        assert 15 <= c["fin"] - c["inicio"] <= 60
        assert c["titulo"]
    assert any(c["inicio"] <= 105 <= c["fin"] for c in cands)

    r = runner.invoke(app, ["render", proyecto.id, "--dry-run", "--reencuadre", "centro"])
    assert r.exit_code == 0, r.output
    assert "libx264" in r.output and "subtitles=" in r.output
    ass = (proyecto.subs_dir / "c01.ass").read_text(encoding="utf-8-sig")
    assert "[Events]" in ass and "Dialogue:" in ass


def test_buscar_sin_ia_agrega_b01(proyecto):
    r = runner.invoke(app, ["buscar", proyecto.id, "el infernus", "--n", "1", "--sin-ia"])
    assert r.exit_code == 0, r.output
    cands = json.loads(proyecto.candidatos_json.read_text(encoding="utf-8"))
    b = [c for c in cands if c["id"] == "b01"]
    assert b and b[0]["inicio"] <= 128 <= b[0]["fin"]


def test_render_solo_id_inexistente(proyecto):
    runner.invoke(app, ["auto", proyecto.id, "--n", "1", "--sin-ia"])
    r = runner.invoke(app, ["render", proyecto.id, "--solo", "c99", "--dry-run"])
    assert r.exit_code == 1
    assert "c99" in r.output


def test_revisar_y_proyectos(proyecto):
    runner.invoke(app, ["auto", proyecto.id, "--n", "2", "--sin-ia"])
    r = runner.invoke(app, ["revisar", proyecto.id])
    assert r.exit_code == 0 and "aprobado" in r.output
    r = runner.invoke(app, ["proyectos"])
    assert r.exit_code == 0 and proyecto.id in r.output


def test_proyecto_inexistente(proyecto):
    r = runner.invoke(app, ["render", "no-existe"])
    assert r.exit_code == 1


def test_reencuadre_invalido(proyecto):
    r = runner.invoke(app, ["render", proyecto.id, "--reencuadre", "zoom"])
    assert r.exit_code == 1
