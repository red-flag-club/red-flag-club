"""
L1.2 - The collapse-event label.

PLAN.md L1.2: don't try to assemble a set of legally confirmed
manipulations (enforcement actions are sparse, lag by years, and most real
cases are never charged). Label the thing that actually needs avoiding:

    COLLAPSE EVENT := price rises >= 100% over <= 10 sessions,
                      then falls >= 70% from that peak within 20 sessions

This makes the positive set mechanically derivable from price alone - no
manual labelling, no judgment about intent.

`find_runs` finds every qualifying >=100%/<=10-session run in a bar series
and reports, for each one, whether it went on to collapse. That single
function is what L1.3 needs for both sets:

    positives := [r for r in runs if r.collapsed]
    controls  := [r for r in runs if not r.collapsed]

Price field
-----------
The definition talks about "price," not any specific OHLC field. This
uses closing price for both the run-up and the drawdown, since that is
the conventional close-to-close return convention and keeps the label
independent of Layer 1's DAP-based pump detector (Nam & Skillicorn) -
the label should not be defined in terms of the detector being validated
against it.

Bars are expected pre-filtered
-------------------------------
This module does no filtering of its own. Per CLAUDE.md hard rule 5,
`interpolated` gap-fill bars carry no information and must be dropped by
the caller (the data loader) before bars ever reach this function; this
function trusts that every bar it's given is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

RAMP_MIN_RETURN = 1.00     # >= 100% rise
RAMP_MAX_SESSIONS = 10      # over <= 10 sessions
COLLAPSE_MIN_DRAWDOWN = 0.70  # >= 70% fall from peak
COLLAPSE_MAX_SESSIONS = 20    # within <= 20 sessions of the peak


class PricedBar(Protocol):
    """Structural type: anything with a date and a close satisfies this,
    including layer1.Bar, without this module importing layer1."""
    date: str
    c: float


@dataclass(frozen=True)
class Run:
    """One qualifying >=100%/<=10-session run, labelled by its outcome."""
    symbol: str
    ramp_start_date: str
    ramp_start_price: float
    peak_date: str
    peak_price: float
    run_up_pct: float
    trough_date: str | None
    trough_price: float | None
    drawdown_pct: float | None
    collapsed: bool


def find_runs(symbol: str, bars: Sequence[PricedBar]) -> list[Run]:
    """Scan `bars` (ascending by date, no gaps assumed beyond what the
    caller already filtered) for every qualifying run, each labelled
    `collapsed` per the COLLAPSE EVENT definition above.

    Overlap handling: once a run is found, the scan resumes after its
    peak (or after its trough, if one was searched for) rather than at
    ramp_start + 1, so one underlying event is not reported many times
    from adjacent ramp-start candidates.
    """
    runs: list[Run] = []
    n = len(bars)
    i = 0

    while i < n - 1:
        start = bars[i]
        target = start.c * (1.0 + RAMP_MIN_RETURN)

        window_end = min(i + RAMP_MAX_SESSIONS + 1, n)
        window = bars[i:window_end]

        if not any(b.c >= target for b in window):
            i += 1
            continue

        peak_offset = max(range(len(window)), key=lambda k: window[k].c)
        peak_idx = i + peak_offset
        peak = bars[peak_idx]

        if peak.c < target:
            # The window's max close doesn't itself clear the 100% bar
            # (possible if the qualifying close comes before the window's
            # true max) - the qualifying close is a lower bound on the
            # true peak, so peak.c >= target always holds via `any()`
            # above finding a bar >= target and peak being the max of the
            # same window. Kept as an explicit guard, not a reachable path.
            i += 1
            continue

        run_up_pct = peak.c / start.c - 1.0

        trough_window_end = min(peak_idx + COLLAPSE_MAX_SESSIONS + 1, n)
        trough_window = bars[peak_idx + 1:trough_window_end]

        if trough_window:
            trough_offset = min(range(len(trough_window)), key=lambda k: trough_window[k].c)
            trough = trough_window[trough_offset]
            drawdown_pct = 1.0 - trough.c / peak.c
            collapsed = drawdown_pct >= COLLAPSE_MIN_DRAWDOWN
        else:
            trough = None
            drawdown_pct = None
            collapsed = False

        runs.append(Run(
            symbol=symbol,
            ramp_start_date=start.date,
            ramp_start_price=start.c,
            peak_date=peak.date,
            peak_price=peak.c,
            run_up_pct=run_up_pct,
            trough_date=trough.date if trough else None,
            trough_price=trough.c if trough else None,
            drawdown_pct=drawdown_pct,
            collapsed=collapsed,
        ))

        # Resume scanning after the event's own window so the same ramp
        # isn't re-detected from the next session as a new ramp_start.
        i = (peak_idx + 1 + trough_offset + 1) if trough_window else (peak_idx + 1)

    return runs
