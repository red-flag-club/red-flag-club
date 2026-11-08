"""
Layer 3 - position monitor and exit. Damage limitation, not prediction.

Applies only to positions Layer 1 rated BLOCK or WARN. It never recommends
entering or adding to a position; every output here is a sell or a flag.

What it cannot do (PLAN.md): an overnight gap fills every stop at the gapped
open (RYDE closed 2024-09-11 at $13.11 and opened 09-12 at $5.50), and a
halted stock cannot be sold at all. Nothing below changes either fact.

  L3.1 time_stop_date / liquidate   hard exit N sessions after entry
  L3.2 ladder                       sell-limit levels to rest at entry
  L3.4 abandoned                    a dead sell order nobody replaced
  L3.3 intraday break               NOT BUILT: intraday history before mid-2025
                                    is gap-filled, so it is forward-test only

Pure functions. This module computes levels and dates; it places no orders.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

TIME_STOP_SESSIONS = 2          # Sabherwal et al.: dumps typically within four days
LADDER = ((0.25, 1 / 3), (0.50, 1 / 3))   # +25% sell 1/3, +50% sell 1/3, rest -> time stop
ABANDONED_DAYS = 30


class LookaheadError(ValueError):
    """Raised when an input dated after the as-of date would be used."""


# --------------------------------------------------------------------------
# L3.1 time stop
# --------------------------------------------------------------------------

def time_stop_date(entry_date: str, sessions: Sequence[str],
                   n: int = TIME_STOP_SESSIONS) -> str | None:
    """The trading session `n` sessions after the FIRST entry. Later buys into
    the same name do not reset the clock: adding to a position is exactly the
    behaviour the stop exists to cut off. None if the calendar ends first."""
    days = sorted(sessions)
    if entry_date not in days:
        raise ValueError(f"{entry_date} is not a trading session in the calendar")
    k = days.index(entry_date) + n
    return days[k] if k < len(days) else None


@dataclass(frozen=True)
class Fill:
    date: str
    price: float
    shares: int
    proceeds: float


def liquidate(bars: Sequence, date: str, shares: int, at: str = "open") -> Fill:
    """Sell `shares` at the open (the L3.1 rule) or close of `date`. `bars` need
    .date/.o/.c. Assumes the stock trades that session; a halt makes this
    unachievable, and the open after a gap is the fill, not the stop level."""
    if at not in ("open", "close"):
        raise ValueError("at must be 'open' or 'close'")
    bar = next((b for b in bars if b.date == date), None)
    if bar is None:
        raise ValueError(f"no bar for {date}")
    px = bar.o if at == "open" else bar.c
    return Fill(date, px, shares, round(px * shares, 2))


# --------------------------------------------------------------------------
# L3.2 scale-out ladder
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Rung:
    limit_price: float
    shares: int
    note: str


def ladder(entry_price: float, shares: int) -> list[Rung]:
    """Sell limits to rest as GTC orders at entry, so they need no monitoring.
    The remainder is left to the time stop. Sells only."""
    if entry_price <= 0 or shares <= 0:
        raise ValueError("entry_price and shares must be positive")
    rungs, left = [], shares
    for gain, frac in LADDER:
        q = min(left, int(shares * frac))
        if q:
            rungs.append(Rung(round(entry_price * (1 + gain), 4), q, f"+{gain:.0%} sell {frac:.0%}"))
            left -= q
    if left:
        rungs.append(Rung(0.0, left, "remainder: time stop"))
    return rungs


# --------------------------------------------------------------------------
# L3.4 abandoned position
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Order:
    placed: str             # date placed
    side: str               # "buy" | "sell"
    state: str              # "filled" | "cancelled" | "expired" | "open"
    closed: str | None = None   # date it filled / was cancelled / expired


def abandoned(orders: Sequence[Order], as_of: str, days: int = ABANDONED_DAYS) -> dict | None:
    """ABANDONED if, as of `as_of`, the most recent order on an open position
    is a sell that was cancelled or expired unfilled at least `days` ago with
    nothing placed since. It does not say to sell; it says a decision is being
    made by default.

    Orders placed after `as_of` are ignored, and a cancellation or expiry dated
    after `as_of` is treated as still open (not yet known)."""
    visible = [o for o in orders if o.placed <= as_of]
    if not visible:
        return None
    last = max(visible, key=lambda o: o.placed)
    if last.side != "sell" or last.state not in ("cancelled", "expired"):
        return None
    if last.closed is None or last.closed > as_of:
        return None
    age = (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(last.closed)).days
    if age < days:
        return None
    return {"flag": "ABANDONED", "since": last.closed, "days": age,
            "reason": f"sell order {last.state} unfilled {age} days ago; no replacement"}
