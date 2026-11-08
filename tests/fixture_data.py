"""Which price fixtures the tests read (spec 008).

The private repo has fixtures cut from real brokerage payloads; they are never
published. Everywhere else (the public repo, a contributor's clone) the
synthetic ones from scripts/make_synthetic.py stand in. Tests assert what must
hold on both; the real-only numbers live in tests/private/.
"""

import os
import pathlib

HERE = pathlib.Path(__file__).parent
_REAL = HERE / "fixtures" / "l13"
_SYN = HERE / "fixtures" / "synthetic"

REAL = (_REAL / "historicals_ryde_reto_xrpn.json").exists() and os.environ.get("PD_FIXTURES") != "synthetic"
HISTORICALS = _REAL / "historicals_ryde_reto_xrpn.json" if REAL else _SYN / "historicals.json"
SCAN_BAND = _REAL / "preview_scan_band.json" if REAL else _SYN / "preview_scan_band.json"
FIRST_BAND_SYMBOL = "CVR" if REAL else "AAAA"
