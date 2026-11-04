"""Live probe of every model stage (needs keys in the main checkout .env): uv run pytest tests/live --live -s -q"""

import pytest

from signal_engine.gateway import run_probe

pytestmark = pytest.mark.live


def test_probe_every_stage(live_gateway):
    rows, ok = run_probe(live_gateway, list(live_gateway.cfg["stages"]))
    assert ok, rows
