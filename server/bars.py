"""Bar hygiene for provider data (hard rule 5, research R2).

Providers hand over normalised rows: {date, o, h, l, c, v} plus optional
raw_c, split_factor and interpolated. Only bars that provably carry no
information are dropped. Flat bars are kept (a flat last bar is the
ghost-quote veto) and one-bar spikes are flagged, never dropped (hard rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.event_sets import ISOLATED_SPIKE_RATIO, SPIKE_VOLUME_LOOKBACK

import check_ticker as K
from layer1 import Bar

LookaheadError = K.LookaheadError


@dataclass(frozen=True)
class BarStats:
    total: int
    kept: int
    dropped_interpolated: int
    dropped_nonpositive: int
    dropped_duplicate: int

    @property
    def dropped(self) -> int:
        return self.total - self.kept


def clean_bars(rows: Sequence[dict], as_of: str | None = None) -> tuple[list[dict], BarStats]:
    """Drop interpolated, non-positive and duplicate-date rows; ascending by
    date. A later row for the same date wins (a refetch revises adjustments).
    Raises LookaheadError on a row dated after `as_of` when one is given."""
    interp = nonpos = 0
    by_date: dict[str, dict] = {}
    for r in rows:
        d = str(r["date"])[:10]
        if as_of is not None and d > as_of:
            raise LookaheadError(f"bar dated {d} is after as-of date {as_of}")
        if r.get("interpolated"):
            interp += 1
            continue
        try:
            o, h, l, c = (float(r[k]) for k in ("o", "h", "l", "c"))
        except (TypeError, ValueError, KeyError):
            nonpos += 1
            continue
        if min(o, h, l, c) <= 0:
            nonpos += 1
            continue
        by_date[d] = {**r, "date": d, "o": o, "h": h, "l": l, "c": c, "v": float(r.get("v") or 0)}
    kept = [by_date[d] for d in sorted(by_date)]
    dup = len(rows) - interp - nonpos - len(kept)
    stats = BarStats(len(rows), len(kept), interp, nonpos, dup)
    assert stats.kept == stats.total - interp - nonpos - dup
    return kept, stats


def to_bars(rows: Sequence[dict]) -> list[Bar]:
    return [Bar(r["date"], r["o"], r["h"], r["l"], r["c"], r["v"]) for r in rows]


def suspect_bad_prints(bars: Sequence) -> list[str]:
    """Dates of one-bar spikes on below-median volume (the REED 2023-01-25
    rule from src/event_sets.py). Reported, never dropped: real one-day pumps
    (JAGX, MI) spike too, on heavy volume."""
    out = []
    for i in range(1, len(bars) - 1):
        c = bars[i].c
        if c >= ISOLATED_SPIKE_RATIO * bars[i - 1].c and c >= ISOLATED_SPIKE_RATIO * bars[i + 1].c:
            prior = sorted(b.v for b in bars[max(0, i - SPIKE_VOLUME_LOOKBACK): i])
            if bars[i].v == 0 or not prior or bars[i].v < prior[len(prior) // 2]:
                out.append(bars[i].date)
    return out
