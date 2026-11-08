"""
L1.3 - Event sets: positives (collapse events) and controls from daily bars.

Builds on the L1.2 label in `collapse_events.find_runs`, unchanged, and adds
the three things a set builder needs that a labeller does not:

  1. Bar hygiene. Drops `interpolated` gap-fill bars (CLAUDE.md hard rule 5)
     AND bars with any non-positive OHLC. The second case is real: RYDE
     returns all-zero bars on 2024-02-29..03-04, before its first trade,
     with no `interpolated` flag. A zero close crashes `find_runs` and would
     make any later price look like an infinite run-up.
  2. Censoring. `find_runs` labels a run `collapsed=False` when the data
     simply ends before its 20-session collapse window does. Such a run is
     *pending* here, never a control: counting an unresolved, possibly
     collapsing event as a control would teach L1.5 that pumps are benign.
  3. No lookahead. Every entry point takes `as_of` and raises
     `LookaheadError` on any bar dated after it, rather than filtering it
     away silently (CLAUDE.md hard rule 2).

Each event carries the OHLCV window from PRE_WINDOW_SESSIONS before the ramp
start to the end of the collapse window, so L1.4 can replay Layer 1 session
by session without re-fetching.

This module decides nothing about trading. It labels history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.collapse_events import COLLAPSE_MAX_SESSIONS, find_runs

PRE_WINDOW_SESSIONS = 60

# A peak close at least this many times BOTH neighbouring closes is flagged
# as a probable bad print (REED 2023-01-25 closes at $1,123.50 between $27.69
# and $22.47 on 196 shares). Flagged, never dropped: a real one-day spike
# must stay visible, or recall is quietly weakened (CLAUDE.md hard rule 4).
ISOLATED_SPIKE_RATIO = 3.0

# Isolated spikes are not all bad data: JAGX 2026-09-22, MI 2026-10-05 and
# AZTR 2024-07-23 are one-day pump-and-dumps on 10M-170M shares. What marks a
# bad print is a spike on volume below the stock's own recent median (REED
# traded 196 shares on its $1,123.50 day). `suspect_bad_print` is that
# narrower flag; it is reported separately and still never drops an event.
SPIKE_VOLUME_LOOKBACK = 20

# A ghost quote is not a pump. ELOX after its 2024 delisting flips between
# $0.0011 and $0.000011 on bars where open == high == low == close, and each
# flip reads as a 99x "run" that "collapses". DCX, COPR and MSLE show the same
# pattern. `stale_quote` marks an event where at least this share of bars from
# ramp start to the window end are flat. It does not depend on price level, so
# split-adjusted prices are unaffected. Like the bad-print flag, it is
# reported separately and never drops or relabels an event.
STALE_QUOTE_FLAT_SHARE = 0.5

LABEL_POSITIVE = "positive"
LABEL_CONTROL = "control"
LABEL_PENDING = "pending"


class LookaheadError(RuntimeError):
    """Refused to use a bar dated after the as-of date."""


@dataclass(frozen=True)
class DailyBar:
    """Same field names as layer1.Bar, so events replay through Layer 1
    directly. Defined here so this module does not import layer1."""
    date: str
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass(frozen=True)
class BarStats:
    total: int
    kept: int
    dropped_interpolated: int
    dropped_nonpositive: int


def clean_bars(raw: Sequence[dict], as_of: str) -> tuple[list[DailyBar], BarStats]:
    """Parse `get_equity_historicals` bars, drop the ones that carry no
    information, and return them ascending by date with drop counts.

    Raises LookaheadError if any bar is dated after `as_of`, and ValueError
    on duplicate dates (which would silently double-count a session).
    """
    kept: list[DailyBar] = []
    interpolated = nonpositive = 0

    for r in raw:
        date = r["begins_at"][:10]
        if date > as_of:
            raise LookaheadError(f"bar dated {date} is after as-of date {as_of}")
        if r.get("interpolated"):
            interpolated += 1
            continue
        bar = DailyBar(
            date=date,
            o=float(r["open_price"]),
            h=float(r["high_price"]),
            l=float(r["low_price"]),
            c=float(r["close_price"]),
            v=float(r.get("volume") or 0),
        )
        if min(bar.o, bar.h, bar.l, bar.c) <= 0:
            nonpositive += 1
            continue
        kept.append(bar)

    kept.sort(key=lambda b: b.date)
    for prev, cur in zip(kept, kept[1:]):
        if prev.date == cur.date:
            raise ValueError(f"duplicate bar for {cur.date}")

    stats = BarStats(
        total=len(raw),
        kept=len(kept),
        dropped_interpolated=interpolated,
        dropped_nonpositive=nonpositive,
    )
    assert stats.kept == stats.total - interpolated - nonpositive
    return kept, stats


def label_events(
    symbol: str,
    bars: Sequence[DailyBar],
    as_of: str,
    *,
    origin: str,
    batch: str,
) -> list[dict]:
    """Every qualifying run in `bars`, labelled positive / control / pending.

    `bars` must already be clean and ascending (see `clean_bars`). A run is
    positive if it has collapsed (>= 70% drawdown within 20 sessions of the
    peak), pending if it has not collapsed and fewer than 20 sessions follow
    the peak in the data, and control otherwise.
    """
    for b in bars:
        if b.date > as_of:
            raise LookaheadError(f"bar dated {b.date} is after as-of date {as_of}")

    index = {b.date: i for i, b in enumerate(bars)}
    events = []

    for run in find_runs(symbol, bars):
        start_idx = index[run.ramp_start_date]
        peak_idx = index[run.peak_date]
        sessions_after_peak = min(len(bars) - 1 - peak_idx, COLLAPSE_MAX_SESSIONS)

        if run.collapsed:
            label = LABEL_POSITIVE
        elif sessions_after_peak < COLLAPSE_MAX_SESSIONS:
            label = LABEL_PENDING
        else:
            label = LABEL_CONTROL

        window = bars[max(0, start_idx - PRE_WINDOW_SESSIONS): peak_idx + COLLAPSE_MAX_SESSIONS + 1]
        run_bars = bars[start_idx: peak_idx + COLLAPSE_MAX_SESSIONS + 1]

        events.append({
            "symbol": symbol,
            "origin": origin,
            "batch": batch,
            "as_of": as_of,
            "label": label,
            "ramp_start_date": run.ramp_start_date,
            "ramp_start_price": run.ramp_start_price,
            "peak_date": run.peak_date,
            "peak_price": run.peak_price,
            "run_up_pct": round(run.run_up_pct, 6),
            "trough_date": run.trough_date,
            "trough_price": run.trough_price,
            "drawdown_pct": None if run.drawdown_pct is None else round(run.drawdown_pct, 6),
            "sessions_after_peak": sessions_after_peak,
            "isolated_spike_peak": _isolated_spike(bars, peak_idx),
            "suspect_bad_print": _isolated_spike(bars, peak_idx) and _below_median_volume(bars, peak_idx),
            "zero_volume_bars": sum(1 for b in run_bars if b.v == 0),
            "flat_bar_share": round(_flat_share(run_bars), 4),
            "stale_quote": _flat_share(run_bars) >= STALE_QUOTE_FLAT_SHARE,
            "bars": [[b.date, b.o, b.h, b.l, b.c, b.v] for b in window],
        })

    return events


def _isolated_spike(bars: Sequence[DailyBar], i: int) -> bool:
    """True if bar i's close is >= ISOLATED_SPIKE_RATIO x both neighbours."""
    if i == 0 or i == len(bars) - 1:
        return False
    c = bars[i].c
    return c >= ISOLATED_SPIKE_RATIO * bars[i - 1].c and c >= ISOLATED_SPIKE_RATIO * bars[i + 1].c


def _flat_share(bars: Sequence[DailyBar]) -> float:
    """Share of bars with open == high == low == close (no intrabar movement)."""
    if not bars:
        return 0.0
    return sum(1 for b in bars if b.o == b.h == b.l == b.c) / len(bars)


def _below_median_volume(bars: Sequence[DailyBar], i: int) -> bool:
    """True if bar i traded nothing, or less than the median of the bars before it."""
    prior = sorted(b.v for b in bars[max(0, i - SPIKE_VOLUME_LOOKBACK): i])
    if bars[i].v == 0 or not prior:
        return True
    return bars[i].v < prior[len(prior) // 2]
