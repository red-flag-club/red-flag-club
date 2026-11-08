"""
L1.4 walk-forward harness.

Replays Layer 1 session by session over a stored L1.3 event. At each session T
the verdict is computed from bars dated <= T and an Issuer built only from
filings and financials available on T. Pure functions; no IO.

Point-in-time structural inputs, and what this data can and cannot tell us:

  input                    source                               when unknown
  -----------------------  -----------------------------------  ----------------------------
  public float < 20M       none (small-cap filings 404, R8)     always
  market cap < $100M       none (no point-in-time share count)  always
  foreign filer            filing index, forms dated <= T       no filing on record by T
  listed < 18 months       first real (non-interpolated) bar    data starts too late to tell
  unprofitable             annual net income, period end +      no annual result public by T
                           ANNUAL_REPORT_LAG_DAYS <= T
  no filing in > 30 days   filing index, last filing <= T       none on record, or older than
                                                                INDEX_HOLE_DAYS (coverage hole)

An unknown input is never silently a pass (CLAUDE.md hard rule 4). Each
session is scored twice: `lo` counts unknowns as clear, `hi` counts them as red
flags. The true score lies between them; `hi` is the primary result.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from statistics import median
from typing import Sequence

from src.event_sets import LookaheadError
from src.layer1 import (
    DOMESTIC_FORMS,
    FOREIGN_FORMS,
    STRUCTURAL_BLOCK_THRESHOLD,
    Bar,
    Issuer,
    PumpConfig,
    layer1_verdict,
)

# 10-K is due 90 days after year end for non-accelerated filers, 20-F four
# months. A result counts as public only once this many days have passed, so a
# timely filer never leaks; a late filer can leak by its delay.
ANNUAL_REPORT_LAG_DAYS = 120

# The filing index has holes: JAGX shows no 10-K/10-Q at all from 2022 to
# 2026-09 although it filed every quarter. A last filing older than this is
# treated as a coverage hole (unknown), not as a year of silence.
INDEX_HOLE_DAYS = 365

# Daily bars start here. A first real bar on or before DATA_START_SLACK means
# the stock was already listed when the data begins, so its age is a lower bound.
DATA_START = "2022-01-03"
DATA_START_SLACK = "2022-01-10"
LISTING_MONTHS = 18

DISCLOSURE_FORMS = FOREIGN_FORMS | DOMESTIC_FORMS | {"10-K/A", "10-Q/A", "20-F/A"}


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


# --------------------------------------------------------------------------
# point-in-time issuer
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PointInTime:
    """Each structural input as True (red flag), False (clear) or None (unknown)."""
    as_of: str
    small_float: bool | None
    small_cap: bool | None
    foreign: bool | None
    recent_listing: bool | None
    unprofitable: bool | None
    stale_disclosure: bool | None
    days_since_last_filing: int | None

    def unknown(self) -> list[str]:
        return [k for k in ("small_float", "small_cap", "foreign", "recent_listing",
                            "unprofitable", "stale_disclosure") if getattr(self, k) is None]


def point_in_time(as_of: str, filings: Sequence[Sequence[str]],
                  annuals: Sequence[Sequence], first_bar: str | None) -> PointInTime:
    """Structural inputs as of `as_of`. `filings` is [[date, form], ...] and
    `annuals` is [[period_end, net_income], ...]; either may include later
    rows, which are ignored. The result must not change if later rows are added
    (tested)."""
    if first_bar is not None and first_bar > as_of:
        raise LookaheadError(f"first bar {first_bar} is after as-of date {as_of}")

    seen = [(d, f) for d, f in filings if d <= as_of and f in DISCLOSURE_FORMS]
    forms = {f for _, f in seen}
    if not forms:
        foreign = None
    else:
        foreign = bool(forms & FOREIGN_FORMS) and not (forms & DOMESTIC_FORMS)

    days_since = _days(max(d for d, _ in seen), as_of) if seen else None
    if days_since is None or days_since > INDEX_HOLE_DAYS:
        stale = None
    else:
        stale = days_since > 30

    public = [(p, ni) for p, ni in annuals
              if _days(p, as_of) >= ANNUAL_REPORT_LAG_DAYS and ni is not None]
    unprofitable = (max(public)[1] < 0) if public else None

    if first_bar is None:
        recent = None
    else:
        months = _days(first_bar, as_of) / 30.44
        if first_bar <= DATA_START_SLACK:
            recent = False if months >= LISTING_MONTHS else None
        else:
            recent = months < LISTING_MONTHS

    return PointInTime(as_of, None, None, foreign, recent, unprofitable, stale,
                       None if stale is None else days_since)


def issuers(symbol: str, pit: PointInTime) -> tuple[Issuer, Issuer]:
    """(lo, hi) Issuers for layer1.structural_score: unknowns clear in `lo`,
    red in `hi`. Values are chosen only to land on the right side of each
    layer1 threshold; they are not estimates."""
    def pick(flag: bool | None, red, clear, unknown_red: bool):
        if flag is None:
            return red if unknown_red else clear
        return red if flag else clear

    def build(unknown_red: bool) -> Issuer:
        return Issuer(
            symbol=symbol,
            public_float=pick(pit.small_float, 0.0, None, unknown_red),
            market_cap=pick(pit.small_cap, 0.0, None, unknown_red),
            form_types=pick(pit.foreign, ["6-K"], ["10-K"], unknown_red),
            months_since_first_filing=pick(pit.recent_listing, 0.0, None, unknown_red),
            net_income=pick(pit.unprofitable, -1.0, None, unknown_red),
            days_since_last_filing=pick(pit.stale_disclosure, 10_000, None, unknown_red),
        )

    return build(False), build(True)


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Replay:
    key: str
    label: str
    sessions: int               # sessions evaluated, ramp start .. peak
    first_block_lo: int | None  # sessions before the peak (0 = on the peak day)
    first_block_hi: int | None
    first_pump: int | None
    block_sessions_lo: int
    block_sessions_hi: int
    unknown_at_peak: tuple[str, ...]


def replay(event: dict, filings: Sequence, annuals: Sequence, first_bar: str | None,
           cfg: PumpConfig = PumpConfig(),
           block_threshold: int = STRUCTURAL_BLOCK_THRESHOLD) -> Replay | None:
    """Walk an event from ramp start to peak. At each session T, Layer 1 sees
    only bars dated <= T and structural inputs as of T. Returns None if the
    peak has fewer than cfg.window bars before it (the detector cannot run)."""
    bars = [Bar(*b) for b in event["bars"]]
    dates = [b.date for b in bars]
    peak = dates.index(event["peak_date"])
    start = dates.index(event["ramp_start_date"])
    if peak < cfg.window:
        return None

    first = {"lo": None, "hi": None, "pump": None}
    count = {"lo": 0, "hi": 0}
    pit = None
    for i in range(max(start, cfg.window), peak + 1):
        t = dates[i]
        visible = bars[: i + 1]
        if visible[-1].date != t or any(b.date > t for b in visible):
            raise LookaheadError(f"bar after {t} passed to layer1_verdict")
        pit = point_in_time(t, filings, annuals, first_bar)
        lo, hi = issuers(event["symbol"], pit)
        v_lo = layer1_verdict(lo, visible, cfg, block_threshold)
        v_hi = layer1_verdict(hi, visible, cfg, block_threshold)
        if v_hi["pump_flagged"] and first["pump"] is None:
            first["pump"] = peak - i
        for name, v in (("lo", v_lo), ("hi", v_hi)):
            if v["verdict"] == "BLOCK":
                count[name] += 1
                if first[name] is None:
                    first[name] = peak - i

    return Replay(
        key=f"{event['symbol']}|{event['ramp_start_date']}|{event['peak_date']}",
        label=event["label"], sessions=peak - max(start, cfg.window) + 1,
        first_block_lo=first["lo"], first_block_hi=first["hi"], first_pump=first["pump"],
        block_sessions_lo=count["lo"], block_sessions_hi=count["hi"],
        unknown_at_peak=tuple(pit.unknown()) if pit else (),
    )


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def metrics(positives: Sequence[Replay], controls: Sequence[Replay], bound: str,
            control_weight: float = 1.0) -> dict:
    """PLAN.md L1.4 metrics for one bound ('lo', 'hi' or 'pump').

    recall      positives with BLOCK on or before the peak / N positives
    lead        median sessions from first BLOCK to peak, over detected positives
    fp_rate     controls with BLOCK on or before the peak / N controls
    latch_prec  BLOCK sessions in positives / all BLOCK sessions, with control
                sessions weighted by control_weight (population / sample)
    """
    def first(r: Replay):
        return {"lo": r.first_block_lo, "hi": r.first_block_hi, "pump": r.first_pump}[bound]

    def nblock(r: Replay):
        return {"lo": r.block_sessions_lo, "hi": r.block_sessions_hi, "pump": 0}[bound]

    hit = [first(r) for r in positives if first(r) is not None]
    fp = [r for r in controls if first(r) is not None]
    pos_s = sum(nblock(r) for r in positives)
    ctl_s = sum(nblock(r) for r in controls) * control_weight
    return {
        "bound": bound,
        "n_positives": len(positives),
        "recall": round(len(hit) / len(positives), 3) if positives else None,
        "recall_lead_ge_2": round(sum(x >= 2 for x in hit) / len(positives), 3) if positives else None,
        "median_lead": median(hit) if hit else None,
        "n_controls": len(controls),
        "fp_rate": round(len(fp) / len(controls), 3) if controls else None,
        "latch_precision": (round(pos_s / (pos_s + ctl_s), 3) if bound != "pump" and pos_s + ctl_s
                            else None),
    }
