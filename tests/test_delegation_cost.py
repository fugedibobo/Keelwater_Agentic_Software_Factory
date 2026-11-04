"""The cost scenario printed in docs/delegation.md section 9 must equal what the script prints."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_doc_block_matches_script_output():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "delegation_cost.py")],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    doc = (ROOT / "docs" / "delegation.md").read_text(encoding="utf-8")
    assert out.strip() in doc, "docs/delegation.md section 9 output block differs from the script's output"
