"""scripts/readme_sections.py: the committed README matches its generators, and the cost arithmetic is right."""
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("readme_sections", ROOT / "scripts" / "readme_sections.py")
rs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rs)


def test_check_passes_on_committed_readme():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "readme_sections.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cost_per_run_on_a_tiny_cache(tmp_path):
    stages = {"extract": {"model": "m/a", "price": {"in": 1.0, "out": 2.0}},
              "embed": {"model": "m/e", "price": {"in": 0.5, "out": 0.0}}}
    cache = tmp_path / "cache"
    for stage in ("extract", "embed"):
        (cache / stage).mkdir(parents=True)

    def put(key, model, tin, tout):
        (cache / f"{key}.json").write_text(json.dumps(
            {"request": {"model": model}, "response": {"usage": {"tokens_in": tin, "tokens_out": tout}}}), encoding="utf-8")
    put("extract/k1", "m/a", 1_000_000, 500_000)     # 1.0 + 1.0 = 2.0
    put("extract/k2", "other/fallback", 2_000_000, 0)  # not priced by model: stage price 1.0/M in -> 2.0
    put("embed/k3", "m/e", 4_000_000, 0)               # 2.0
    report = tmp_path / "run.json"
    report.write_text(json.dumps({"manifest": {"cache_keys": ["extract/k1", "extract/k2", "embed/k3"]}}), encoding="utf-8")
    assert abs(rs.cost_per_run(report, cache, stages) - 6.0) < 1e-9


def test_cost_fails_loudly_without_a_price(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "k.json").write_text(json.dumps({"request": {"model": "m/z"}, "response": {"usage": {}}}), encoding="utf-8")
    report = tmp_path / "run.json"
    report.write_text(json.dumps({"manifest": {"cache_keys": ["x/k"]}}), encoding="utf-8")
    try:
        rs.cost_per_run(report, tmp_path, {"x": {"model": "m/y"}})
    except SystemExit as e:
        assert "no price" in str(e)
    else:
        raise AssertionError("expected SystemExit")


def test_earlier_comparison_renders(monkeypatch):
    monkeypatch.setattr(rs, "EARLIER", dict(rs.CURRENT))
    text = rs.results_region()
    assert rs.EARLIER_LABEL in text and "| Seed 42: Signal recall | 0.95 | 0.95 | 0.90 |" in text
