"""In-process scheduler for the Layer 2 refresh (spec 004, research R5).
Weekdays at fixed US/Eastern times. The refresh is idempotent, so a run the
laptop slept through is simply caught up by the next one."""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Callable, Sequence

from server.data import ET

log = logging.getLogger("pd-defence.schedule")


def next_run(now: dt.datetime, times: Sequence[str]) -> dt.datetime:
    """The first weekday slot strictly after `now` (ET-aware)."""
    now = now.astimezone(ET)
    slots = sorted(dt.time(int(t[:2]), int(t[3:])) for t in times)
    day = now.date()
    for _ in range(8):
        if day.weekday() < 5:
            for t in slots:
                cand = dt.datetime.combine(day, t, ET)
                if cand > now:
                    return cand
        day += dt.timedelta(days=1)
    raise ValueError("no schedule slots")


def run_forever(job: Callable[[], object], times: Sequence[str],
                now: Callable[[], dt.datetime] = lambda: dt.datetime.now(ET),
                sleep: Callable[[float], None] = time.sleep, once: bool = False) -> None:
    while True:
        at = next_run(now(), times)
        log.info("next refresh %s", at.isoformat())
        # sleep in short steps so a laptop waking from sleep runs the job promptly
        while now() < at:
            sleep(min(60.0, max(1.0, (at - now()).total_seconds())))
        try:
            job()
        except Exception:                      # a failed run must not stop the schedule
            log.exception("refresh failed")
        if once:
            return


def start_thread(job: Callable[[], object], times: Sequence[str]) -> threading.Thread:
    t = threading.Thread(target=run_forever, args=(job, times), name="pd-scan-schedule", daemon=True)
    t.start()
    return t
