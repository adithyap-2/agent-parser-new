#!/usr/bin/env python
"""Rebuild every gold page from the source PDF, then validate.

Gold is generated, not hand-edited: the per-page builders take character
content from the PDF text layer and apply hand-authored structure. Regenerating
from scratch is therefore always safe, and is the only supported way to change
gold — edit the builder, not the JSON.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = ["p04", "p13", "p22", "p27", "p30"]


def run(script, *args):
    r = subprocess.run([sys.executable, str(HERE / script), *args],
                       cwd=HERE, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f"FAILED: {script}")
    return r


for p in PAGES:
    print(f"== {p}")
    run(f"build_{p}.py")

print("\n== validate")
run("validate_gold.py")
