"""
Layer 1 - Pre-trade veto for ramp-and-dump exposure.

Two independent gates, combined into one verdict:

  A. STRUCTURAL  - the FINRA Reg Notice 22-25 fingerprint. Slow-moving,
                   per-issuer. Answers "is this the KIND of security these
                   schemes use?"
  B. PUMP STATE  - Nam & Skillicorn (arXiv:2301.11403) 2-sigma price+volume
                   anomaly test, with a latch. Answers "is it happening NOW?"

Design notes
------------
* The paper's rolling 5-day baseline self-contaminates: the pump inflates its
  own threshold and the detector goes dark mid-event. We keep the sensitive
  trigger but LATCH it, so a fired flag persists.
* Tuned for RECALL, not precision. The paper's best model ran ~53% precision.
  That is fine here: a false positive costs one skipped penny-stock trade, a
  false negative can cost someone their savings. Never invert this trade-off.
* This module decides NOT to trade. It never decides to trade.
"""

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Sequence

# --------------------------------------------------------------------------
# A. Structural gate
# --------------------------------------------------------------------------

@dataclass
class Issuer:
    """Populate from brokerage MCP: get_equity_fundamentals + get_sec_filing_index."""
    symbol: str
    public_float: float | None          # shares; prefer IPO prospectus over vendor float
    market_cap: float | None            # USD
    form_types: Sequence[str]           # distinct SEC form types on file
    months_since_first_filing: float | None
    net_income: float | None            # USD, most recent annual
    days_since_last_filing: int | None


FOREIGN_FORMS = {"6-K", "20-F", "F-1", "F-3", "40-F"}
DOMESTIC_FORMS = {"10-K", "10-Q", "8-K"}


def structural_score(iss: Issuer) -> tuple[int, list[str]]:
    """Return (0-6 score, list of triggered red flags)."""
    hits: list[str] = []

    if iss.public_float is not None and iss.public_float < 20_000_000:
        hits.append(f"float {iss.public_float:,.0f} < 20M (FINRA 22-25 threshold)")

    if iss.market_cap is not None and iss.market_cap < 100_000_000:
        hits.append(f"market cap ${iss.market_cap:,.0f} < $100M")

    forms = set(iss.form_types)
    if forms & FOREIGN_FORMS and not (forms & DOMESTIC_FORMS):
        hits.append("foreign private issuer - files 6-K/20-F, no 10-K/8-K")

    if iss.months_since_first_filing is not None and iss.months_since_first_filing < 18:
        hits.append(f"listed {iss.months_since_first_filing:.0f} months ago")

    if iss.net_income is not None and iss.net_income < 0:
        hits.append("unprofitable")

    if iss.days_since_last_filing is not None and iss.days_since_last_filing > 30:
        hits.append(f"no SEC disclosure in {iss.days_since_last_filing} days")

    return len(hits), hits


# --------------------------------------------------------------------------
# B. Pump-state gate
# --------------------------------------------------------------------------

@dataclass
class Bar:
    date: str
    o: float
    h: float
    l: float
    c: float
    v: float

    @property
    def dap(self) -> float:
        """Daily average price, per the paper: (O+H+L+C)/4."""
        return (self.o + self.h + self.l + self.c) / 4.0


@dataclass
class PumpConfig:
    window: int = 5        # estimation window (paper's value)
    k: float = 2.0         # sigma multiple (paper's value)
    latch_sessions: int = 10
    release_ratio: float = 1.15  # unlatch once DAP falls back near baseline


@dataclass
class PumpState:
    flagged: bool = False
    trigger_date: str | None = None
    sessions_latched: int = 0
    history: list[dict] = field(default_factory=list)


def pump_state(bars: Sequence[Bar], cfg: PumpConfig = PumpConfig()) -> PumpState:
    """Walk the series forward; return the state as of the final bar."""
    st = PumpState()
    for i in range(cfg.window, len(bars)):
        win = bars[i - cfg.window:i]
        daps = [b.dap for b in win]
        vols = [b.v for b in win]
        thr_p = mean(daps) + cfg.k * pstdev(daps)
        thr_v = mean(vols) + cfg.k * pstdev(vols)
        cur = bars[i]
        fires = cur.dap > thr_p and cur.v > thr_v

        if fires and not st.flagged:
            st.flagged, st.trigger_date, st.sessions_latched = True, cur.date, 0
            st.baseline = mean(daps)
        elif st.flagged:
            st.sessions_latched += 1
            cooled = cur.dap < getattr(st, "baseline", 0) * cfg.release_ratio
            if fires:
                st.sessions_latched = 0          # re-arm on fresh evidence
            elif st.sessions_latched >= cfg.latch_sessions or cooled:
                st.flagged = False

        st.history.append({"date": cur.date, "dap": cur.dap,
                           "fires": fires, "latched": st.flagged})
    return st


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

STRUCTURAL_BLOCK_THRESHOLD = 4   # of 6; L1.5 tunes this first


def layer1_verdict(iss: Issuer, bars: Sequence[Bar], cfg: PumpConfig = PumpConfig(),
                   block_threshold: int = STRUCTURAL_BLOCK_THRESHOLD) -> dict:
    score, hits = structural_score(iss)
    ps = pump_state(bars, cfg)

    if score >= block_threshold and ps.flagged:
        verdict, reason = "BLOCK", "ramp-and-dump profile with an active pump signal"
    elif score >= block_threshold:
        verdict, reason = "WARN", "structural profile matches; no active pump"
    elif ps.flagged:
        verdict, reason = "WARN", "active pump signal on an otherwise ordinary issuer"
    else:
        verdict, reason = "PASS", "no Layer 1 trigger"

    return {"symbol": iss.symbol, "verdict": verdict, "reason": reason,
            "structural_score": f"{score}/6", "red_flags": hits,
            "pump_flagged": ps.flagged, "pump_trigger_date": ps.trigger_date}


# --------------------------------------------------------------------------
# Regression test: RYDE, September 2024
# --------------------------------------------------------------------------
# Bars are synthetic (scripts/make_synthetic.py), anchored to the publicly
# reported levels; the issuer facts below are from public SEC filings.

RYDE_BARS = [Bar(*r) for r in [
    ("2024-08-19", 8.530, 8.805, 8.415, 8.700, 49000),
    ("2024-08-20", 8.611, 8.705, 8.372, 8.674, 56281),
    ("2024-08-21", 8.782, 8.976, 8.523, 8.670, 51764),
    ("2024-08-22", 8.788, 8.953, 8.534, 8.650, 44999),
    ("2024-08-23", 8.726, 8.961, 8.326, 8.416, 34586),
    ("2024-08-26", 8.423, 8.594, 8.247, 8.400, 41999),
    ("2024-08-27", 8.413, 8.593, 7.652, 7.813, 64135),
    ("2024-08-28", 7.799, 7.963, 7.358, 7.400, 62999),
    ("2024-08-29", 7.411, 7.556, 6.868, 7.000, 26999),
    ("2024-08-30", 6.956, 7.239, 6.935, 7.200, 530000),
    ("2024-09-03", 7.119, 7.743, 7.015, 7.700, 1099999),
    ("2024-09-04", 7.300, 9.500, 7.300, 9.100, 2000000),
    ("2024-09-05", 9.200, 12.800, 8.600, 12.000, 1299999),
    ("2024-09-06", 12.000, 17.440, 11.700, 17.330, 669999),
    ("2024-09-09", 16.000, 20.300, 13.500, 20.000, 5599999),
    ("2024-09-10", 19.900, 21.900, 18.500, 20.000, 6699999),
    ("2024-09-11", 21.540, 22.490, 13.110, 13.110, 8599999),
]]

RYDE = Issuer(
    symbol="RYDE",
    public_float=3_000_000,          # IPO: 3.0M Class A shares @ $4.00
    market_cap=60_000_000,
    form_types=["6-K"],              # no 10-K / 10-Q / 8-K on file
    months_since_first_filing=6,     # IPO 2024-03-06
    net_income=-18_600_000,
    days_since_last_filing=82,       # last 6-K 2024-06-21
)

if __name__ == "__main__":
    ps = pump_state(RYDE_BARS)
    print("Daily pump state\n" + "-" * 46)
    for h in ps.history:
        state = "LATCHED" if h["latched"] else "-"
        trig = "FIRE" if h["fires"] else "    "
        print(f"{h['date']}  DAP {h['dap']:6.2f}  {trig}  {state}")

    print("\nVerdict as of 2024-09-06")
    print("-" * 46)
    cutoff = [b for b in RYDE_BARS if b.date <= "2024-09-06"]
    v = layer1_verdict(RYDE, cutoff)
    for k, val in v.items():
        if k == "red_flags":
            for f in val:
                print(f"    - {f}")
        else:
            print(f"  {k}: {val}")
