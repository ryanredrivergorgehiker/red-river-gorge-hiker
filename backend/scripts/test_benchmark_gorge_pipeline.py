import json
from pathlib import Path

import pytest

import benchmark_gorge_pipeline as engine
from cached_cog_source import digest


def plan():
    return {"version": engine.VERSION, "boundsWGS84": engine.AOI,
            "samples": [{"id": "sample", "lon": -83.6, "lat": 37.8}],
            "sources": {"hiking": [{"url": "unread-test-source"}]}}


def fake_renderer(cache, job, root, sources):
    path = root / "tiles" / "test.bin"
    engine.atomic(path, b"deterministic-output")
    return {"outputs": [engine.file_entry(path, root)]}


def test_resume_rehashes_outputs_without_render_or_source_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "render_rgb", fake_renderer)
    root, cache = tmp_path / "run", tmp_path / "cache"
    first = engine.run(plan(), root, cache)
    assert len(first["receipts"]) == 1
    monkeypatch.setattr(engine, "render_rgb", lambda *a: pytest.fail("resume rendered"))
    resumed = engine.run(plan(), root, cache)
    assert resumed["receipts"][0]["reused"]
    assert resumed["after"]["requests"] == 0
    (root / "tiles/test.bin").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        engine.run(plan(), root, cache)


def test_failed_job_can_resume_without_accepting_partial_output(tmp_path, monkeypatch):
    def fail(cache, job, root, sources):
        engine.atomic(root / "partial.bin", b"incomplete")
        raise ValueError("simulated interruption")
    monkeypatch.setattr(engine, "render_rgb", fail)
    root, cache = tmp_path / "run", tmp_path / "cache"
    first = engine.run(plan(), root, cache)
    assert len(first["failures"]) == 1 and not first["receipts"]
    assert not list((root / "receipts").glob("*.json"))
    monkeypatch.setattr(engine, "render_rgb", fake_renderer)
    second = engine.run(plan(), root, cache)
    assert len(second["receipts"]) == 1 and not second["failures"]
    assert len(list((root / "failures").glob("*.json"))) == 1


def test_changed_plan_and_recipe_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "render_rgb", fake_renderer)
    root, cache = tmp_path / "run", tmp_path / "cache"
    engine.run(plan(), root, cache)
    changed = plan()
    changed["samples"][0]["lat"] = 37.81
    with pytest.raises(ValueError, match="different plan"):
        engine.run(changed, root, cache)
    receipt = json.loads(next((root / "receipts").glob("*.json")).read_text())
    with pytest.raises(ValueError, match="Recipe"):
        engine.receipt_valid(root, receipt, "different-recipe")


def test_output_symlink_and_escape_refused(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    other = tmp_path / "other"
    other.write_bytes(b"x")
    link = root / "link"
    link.symlink_to(other)
    for path in ["link", "../other"]:
        receipt = {"recipeSHA256": "r", "validated": True,
                   "outputs": [{"path": path, "bytes": 1, "sha256": digest(b"x")}]}
        with pytest.raises(ValueError, match="integrity"):
            engine.receipt_valid(root, receipt, "r")


def test_xyz_pyramid_preserves_alpha_and_exact_quadtree(tmp_path):
    from PIL import Image
    image = Image.new("RGBA", (1024, 1024), (242, 104, 92, 0))
    outputs, levels = engine.pyramid(image, tmp_path, "sunrise", 17500, 25200)
    assert [x["tileCount"] for x in levels] == [1, 4, 16]
    assert len(outputs) == 21
    for output in outputs:
        with Image.open(tmp_path / output["path"]) as tile:
            assert tile.getchannel("A").getextrema() == (0, 0)
    assert (tmp_path / "tiles/sunrise/18/70003/100803.png").exists()
