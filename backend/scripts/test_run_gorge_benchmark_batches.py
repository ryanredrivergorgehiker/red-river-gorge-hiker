import json
from types import SimpleNamespace

import pytest
import run_gorge_benchmark_batches as driver


def setup(tmp_path, monkeypatch):
    plan = {"samples": [{"id": "a"}], "sources": {"hiking": [{}]}}
    path = tmp_path / "plan.json"; path.write_text(json.dumps(plan))
    root = tmp_path / "output"; root.mkdir()
    monkeypatch.setattr(driver, "run", lambda *a, **kw: {"receipts": [], "after": {}})
    return path, root


def test_native_failure_retried_once_then_stops(tmp_path, monkeypatch):
    plan, root = setup(tmp_path, monkeypatch)
    calls = []
    def fail(*args, **kw):
        calls.append(kw)
        return SimpleNamespace(returncode=-11)
    monkeypatch.setattr(driver.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="stopped"):
        driver.orchestrate(plan, root, tmp_path / "cache")
    assert len(calls) == 2
    assert all(c["timeout"] == 300 for c in calls)
    assert len(json.loads((root / "PROCESS-ATTEMPTS.json").read_text())) == 2


def test_validation_failure_not_retried(tmp_path, monkeypatch):
    plan, root = setup(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: calls.append(1) or SimpleNamespace(returncode=2))
    with pytest.raises(RuntimeError):
        driver.orchestrate(plan, root, tmp_path / "cache")
    assert len(calls) == 1


def test_already_committed_jobs_never_dispatched(tmp_path, monkeypatch):
    plan, root = setup(tmp_path, monkeypatch)
    (root / "receipts").mkdir(); (root / "receipts/a-hiking.json").write_text("{}")
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: pytest.fail("committed job dispatched"))
    result = driver.orchestrate(plan, root, tmp_path / "cache")
    assert result["attempts"] == []
