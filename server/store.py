"""DuckDB cache (data-model.md). One connection behind a lock; one process.
Holds market data, filing indexes, a verdict log and provider call counts.
Never account numbers, positions or orders.
"""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
  symbol VARCHAR, date DATE, o DOUBLE, h DOUBLE, l DOUBLE, c DOUBLE, v DOUBLE,
  raw_c DOUBLE, split_factor DOUBLE, source VARCHAR, fetched_at TIMESTAMP,
  PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS coverage (
  symbol VARCHAR PRIMARY KEY, first_date DATE, last_date DATE, fetched_at TIMESTAMP,
  source VARCHAR, status VARCHAR, dropped INTEGER);
CREATE TABLE IF NOT EXISTS filings (symbol VARCHAR, cik VARCHAR, form VARCHAR, filed DATE);
CREATE TABLE IF NOT EXISTS filings_coverage (
  symbol VARCHAR PRIMARY KEY, cik VARCHAR, fetched_at TIMESTAMP, status VARCHAR);
CREATE TABLE IF NOT EXISTS checks (ts TIMESTAMP, tool VARCHAR, symbol VARCHAR, as_of DATE, verdict VARCHAR);
CREATE TABLE IF NOT EXISTS provider_calls (ts TIMESTAMP, provider VARCHAR, symbol VARCHAR, status VARCHAR);
CREATE TABLE IF NOT EXISTS market_daily (
  date DATE, symbol VARCHAR, o DOUBLE, h DOUBLE, l DOUBLE, c DOUBLE, v DOUBLE, source VARCHAR);
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS sessions (
  date DATE PRIMARY KEY, status VARCHAR, n_symbols INTEGER, dropped INTEGER, tries INTEGER);
CREATE TABLE IF NOT EXISTS splits (symbol VARCHAR, date DATE, ratio DOUBLE, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS scan_log (
  session DATE, symbol VARCHAR, logged_at TIMESTAMP, close DOUBLE, ret_1 DOUBLE, ret_5 DOUBLE,
  ret_21 DOUBLE, rel_vol_30 DOUBLE, reason VARCHAR, flags VARCHAR, backfilled BOOLEAN,
  verdict VARCHAR, reasons VARCHAR, PRIMARY KEY (session, symbol));
CREATE TABLE IF NOT EXISTS outcomes (
  symbol VARCHAR, first_logged DATE, label VARCHAR, peak_date DATE, peak DOUBLE, drawdown DOUBLE,
  decided_on DATE, PRIMARY KEY (symbol, first_logged));
CREATE TABLE IF NOT EXISTS scan_runs (ts TIMESTAMP, sessions_scanned INTEGER, hits INTEGER, status VARCHAR);
CREATE TABLE IF NOT EXISTS scanned (session DATE PRIMARY KEY);
"""

LOG_COLS = ("session", "symbol", "logged_at", "close", "ret_1", "ret_5", "ret_21", "rel_vol_30",
            "reason", "flags", "backfilled", "verdict", "reasons")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.con = duckdb.connect(self.path)
        self.lock = threading.Lock()
        with self.lock:
            self.con.execute(SCHEMA)
            # spec 005: idle-symbol eviction (databases created by spec 003 lack it)
            self.con.execute("ALTER TABLE coverage ADD COLUMN IF NOT EXISTS accessed_at TIMESTAMP")

    def _q(self, sql: str, params=()):
        with self.lock:
            return self.con.execute(sql, params).fetchall()

    # ------------------------------------------------------------ bars
    def put_bars(self, symbol: str, rows: list[dict], source: str) -> None:
        now = _now()
        data = [(symbol, r["date"], r["o"], r["h"], r["l"], r["c"], r["v"], r.get("raw_c"),
                 r.get("split_factor") or 1.0, source, now) for r in rows]
        if not data:
            return
        with self.lock:
            # one multi-row statement per chunk: DuckDB's executemany is row-at-a-time
            for i in range(0, len(data), 500):
                chunk = data[i:i + 500]
                self.con.execute("INSERT OR REPLACE INTO bars VALUES "
                                 + ",".join(["(?,?,?,?,?,?,?,?,?,?,?)"] * len(chunk)),
                                 [x for row in chunk for x in row])

    def bars(self, symbol: str, start: str, as_of: str) -> list[dict]:
        """Rows with start <= date <= as_of, ascending. The as_of filter is
        the no-lookahead guarantee for everything built on the cache."""
        rows = self._q("SELECT date, o, h, l, c, v, raw_c, split_factor, source FROM bars "
                       "WHERE symbol = ? AND date >= ? AND date <= ? ORDER BY date",
                       (symbol, start, as_of))
        return [{"date": d.isoformat(), "o": o, "h": h, "l": l, "c": c, "v": v, "raw_c": rc,
                 "split_factor": sf, "source": src} for d, o, h, l, c, v, rc, sf, src in rows]

    def bars_after(self, symbol: str, after: str, until: str) -> list[dict]:
        """Hindsight only (was_i_pumped); never fed to a verdict."""
        rows = self._q("SELECT date, o, h, l, c, v FROM bars WHERE symbol = ? AND date > ? AND date <= ? "
                       "ORDER BY date", (symbol, after, until))
        return [{"date": d.isoformat(), "o": o, "h": h, "l": l, "c": c, "v": v} for d, o, h, l, c, v in rows]

    def coverage(self, symbol: str) -> dict | None:
        r = self._q("SELECT first_date, last_date, fetched_at, source, status, dropped FROM coverage "
                    "WHERE symbol = ?", (symbol,))
        if not r:
            return None
        f, l, at, src, st, dropped = r[0]
        return {"first_date": f.isoformat() if f else None, "last_date": l.isoformat() if l else None,
                "fetched_at": at, "source": src, "status": st, "dropped": dropped}

    def set_coverage(self, symbol: str, first: str | None, last: str | None, source: str,
                     status: str = "ok", dropped: int = 0) -> None:
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO coverage VALUES (?,?,?,?,?,?,?,?)",
                             (symbol, first, last, _now(), source, status, dropped, _now()))

    def touch(self, symbol: str) -> None:
        with self.lock:
            self.con.execute("UPDATE coverage SET accessed_at = ? WHERE symbol = ?", (_now(), symbol))

    # ------------------------------------------------------------ retention (spec 005)
    def prune_bars(self, window_start: str, idle_cutoff: dt.datetime) -> dict:
        """Drop per-symbol bars older than the cache window and every symbol
        not looked up since idle_cutoff. Filings, checks and the scan log are
        never pruned."""
        with self.lock:
            c = self.con
            old = c.execute("SELECT count(*) FROM bars WHERE date < ?", (window_start,)).fetchone()[0]
            c.execute("DELETE FROM bars WHERE date < ?", (window_start,))
            idle = [s for (s,) in c.execute(
                "SELECT symbol FROM coverage WHERE coalesce(accessed_at, fetched_at) < ?", (idle_cutoff,)).fetchall()]
            if idle:
                c.execute("DELETE FROM bars WHERE symbol IN (SELECT unnest(?))", (idle,))
                c.execute("DELETE FROM coverage WHERE symbol IN (SELECT unnest(?))", (idle,))
            c.execute("UPDATE coverage SET first_date = ? WHERE status = 'ok' AND first_date < ?",
                      (window_start, window_start))
            c.execute("CHECKPOINT")
        return {"old_bars": old, "idle_symbols": len(idle)}

    def prune_market(self, keep: int) -> int:
        """Keep the last `keep` loaded sessions of whole-market bars; older
        sessions become `pruned` (never re-fetched, still counted for episode
        grouping). Returns how many sessions were pruned."""
        with self.lock:
            c = self.con
            days = [d for (d,) in c.execute("SELECT date FROM sessions WHERE status = 'loaded' "
                                            "ORDER BY date DESC").fetchall()]
            if len(days) <= keep:
                return 0
            cutoff = days[keep - 1]
            c.execute("DELETE FROM market_daily WHERE date < ?", (cutoff,))
            c.execute("UPDATE sessions SET status = 'pruned' WHERE status = 'loaded' AND date < ?", (cutoff,))
            c.execute("CHECKPOINT")
            return len(days) - keep

    def get_meta(self, key: str) -> str | None:
        r = self._q("SELECT value FROM meta WHERE key = ?", (key,))
        return r[0][0] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def compact(self) -> tuple[int, int] | None:
        """Rewrite the file without the space deleted rows left behind
        (DuckDB reuses but never returns it). Copy to a temp file, then an
        atomic rename: a crash leaves the old file intact."""
        if self.path == ":memory:":
            return None
        p = Path(self.path)
        tmp = p.with_suffix(".compact")
        with self.lock:
            before = p.stat().st_size
            self.con.execute("CHECKPOINT")
            self.con.close()
            try:
                if tmp.exists():
                    tmp.unlink()
                c = duckdb.connect()
                c.execute(f"ATTACH '{p}' AS o (READ_ONLY)")
                c.execute(f"ATTACH '{tmp}' AS n")
                c.execute("COPY FROM DATABASE o TO n")
                c.close()
                tmp.replace(p)
            finally:
                if tmp.exists():
                    tmp.unlink()
                self.con = duckdb.connect(self.path)
            return before, p.stat().st_size

    def sessions_all(self) -> list[str]:
        """Loaded and pruned sessions: every session that was ever scanned-able."""
        return [d.isoformat() for (d,) in self._q("SELECT date FROM sessions WHERE status IN ('loaded', 'pruned') "
                                                   "ORDER BY date")]

    def db_size(self) -> int | None:
        if self.path == ":memory:":
            return None
        try:
            return Path(self.path).stat().st_size
        except OSError:
            return None

    # ------------------------------------------------------------ filings
    def put_filings(self, symbol: str, cik: str | None, rows: list[dict], status: str = "ok") -> None:
        with self.lock:
            self.con.execute("DELETE FROM filings WHERE symbol = ?", (symbol,))
            for i in range(0, len(rows), 500):
                chunk = rows[i:i + 500]
                self.con.execute("INSERT INTO filings VALUES " + ",".join(["(?,?,?,?)"] * len(chunk)),
                                 [x for r in chunk for x in (symbol, cik, r["form"], r["filed"])])
            self.con.execute("INSERT OR REPLACE INTO filings_coverage VALUES (?,?,?,?)",
                             (symbol, cik, _now(), status))

    def filings(self, symbol: str, as_of: str) -> list[dict]:
        rows = self._q("SELECT form, filed FROM filings WHERE symbol = ? AND filed <= ? ORDER BY filed",
                       (symbol, as_of))
        return [{"form_type": f, "date_filed": d.isoformat()} for f, d in rows]

    def filings_coverage(self, symbol: str) -> dict | None:
        r = self._q("SELECT cik, fetched_at, status FROM filings_coverage WHERE symbol = ?", (symbol,))
        return {"cik": r[0][0], "fetched_at": r[0][1], "status": r[0][2]} if r else None

    # ------------------------------------------------------------ logs
    def log_check(self, tool: str, symbol: str, as_of: str, verdict: str) -> None:
        with self.lock:
            self.con.execute("INSERT INTO checks VALUES (?,?,?,?,?)", (_now(), tool, symbol, as_of, verdict))

    def log_call(self, provider: str, symbol: str, status: str) -> None:
        with self.lock:
            self.con.execute("INSERT INTO provider_calls VALUES (?,?,?,?)", (_now(), provider, symbol, status))

    def usage(self, provider: str) -> dict:
        now = _now()
        hour = self._q("SELECT count(*) FROM provider_calls WHERE provider = ? AND ts >= ?",
                       (provider, now - dt.timedelta(hours=1)))[0][0]
        month = self._q("SELECT count(DISTINCT symbol) FROM provider_calls WHERE provider = ? AND ts >= ?",
                        (provider, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)))[0][0]
        syms, n = self._q("SELECT count(DISTINCT symbol), count(*) FROM bars")[0]
        msess, mrows = self._q("SELECT count(DISTINCT date), count(*) FROM market_daily")[0]
        logged = self._q("SELECT count(*), min(session) FROM scan_log")[0]
        return {"calls_last_hour": hour, "unique_symbols_this_month": month,
                "symbols_cached": syms, "bars_cached": n, "market_sessions": msess, "market_rows": mrows,
                "scan_log_rows": logged[0], "scan_log_since": logged[1].isoformat() if logged[1] else None,
                "db_bytes": self.db_size()}

    # ------------------------------------------------------------ market sessions (spec 004)
    def _insert(self, table: str, rows: list[tuple], ncols: int, verb: str = "INSERT OR REPLACE") -> None:
        """Multi-row insert in chunks (DuckDB's executemany is row-at-a-time). Caller holds the lock."""
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            ph = "(" + ",".join("?" * ncols) + ")"
            self.con.execute(f"{verb} INTO {table} VALUES " + ",".join([ph] * len(chunk)),
                             [x for r in chunk for x in r])

    def put_session(self, date: str, rows: list[dict], source: str, dropped: int) -> None:
        """Replace one whole session (no primary key on market_daily: the
        index would be bigger than the data, spec 005)."""
        with self.lock:
            self.con.execute("DELETE FROM market_daily WHERE date = ?", (date,))
            self._insert("market_daily", [(date, r["symbol"], r["o"], r["h"], r["l"], r["c"], r["v"], source)
                                          for r in rows], 8, verb="INSERT")
            self.con.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)",
                             (date, "loaded", len(rows), dropped, self.session_tries(date, locked=True) + 1))

    def mark_session(self, date: str, status: str) -> None:
        with self.lock:
            tries = self.session_tries(date, locked=True) + 1
            self.con.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)", (date, status, 0, 0, tries))

    def session_tries(self, date: str, locked: bool = False) -> int:
        q = lambda: self.con.execute("SELECT tries FROM sessions WHERE date = ?", (date,)).fetchall()
        r = q() if locked else self._locked(q)
        return r[0][0] if r else 0

    def _locked(self, fn):
        with self.lock:
            return fn()

    def sessions(self, status: str | None = None) -> list[str]:
        sql = "SELECT date FROM sessions" + (" WHERE status = ?" if status else "") + " ORDER BY date"
        return [d.isoformat() for (d,) in self._q(sql, (status,) if status else ())]

    def session_status(self, date: str) -> str | None:
        r = self._q("SELECT status FROM sessions WHERE date = ?", (date,))
        return r[0][0] if r else None

    def market_symbols(self, date: str) -> list[str]:
        return [s for (s,) in self._q("SELECT symbol FROM market_daily WHERE date = ? ORDER BY symbol", (date,))]

    def market_history(self, as_of: str, sessions: int, symbols: list[str] | None = None) -> dict[str, list[dict]]:
        """Bars for the last `sessions` loaded sessions up to and including
        as_of (never after), grouped by symbol, ascending."""
        days = self._q("SELECT date FROM sessions WHERE status = 'loaded' AND date <= ? "
                       "ORDER BY date DESC LIMIT ?", (as_of, sessions))
        if not days:
            return {}
        start = min(d for (d,) in days)
        sql = ("SELECT symbol, date, o, h, l, c, v FROM market_daily WHERE date >= ? AND date <= ?"
               + (" AND symbol IN (SELECT unnest(?))" if symbols is not None else "") + " ORDER BY symbol, date")
        params = (start, as_of) + ((symbols,) if symbols is not None else ())
        out: dict[str, list[dict]] = {}
        for sym, d, o, h, l, c, v in self._q(sql, params):
            out.setdefault(sym, []).append({"date": d.isoformat(), "o": o, "h": h, "l": l, "c": c, "v": v})
        return out

    def recent_sessions(self, as_of: str, n: int) -> list[str]:
        """The last n loaded sessions up to and including as_of, ascending."""
        rows = self._q("SELECT date FROM sessions WHERE status = 'loaded' AND date <= ? ORDER BY date DESC LIMIT ?",
                       (as_of, n))
        return sorted(d.isoformat() for (d,) in rows)

    def screen_candidates(self, session: str, start5: str, start21: str, lo: float, hi: float,
                          runup5: float, runup21: float) -> list[str]:
        """Symbols whose close on `session` is in [lo, hi] and is up >= runup
        from the lowest close since start5 / start21. Same arithmetic as
        scan.screen() without split handling, so it returns a superset of
        screen()'s hits (a split only removes hits). Reads nothing after
        `session`."""
        rows = self._q(
            "SELECT symbol FROM market_daily WHERE date >= ? AND date <= ? GROUP BY symbol "
            "HAVING max(CASE WHEN date = ? THEN c END) BETWEEN ? AND ? AND ("
            " max(CASE WHEN date = ? THEN c END) >= (1 + ?) * min(CASE WHEN date >= ? THEN c END)"
            " OR max(CASE WHEN date = ? THEN c END) >= (1 + ?) * min(c))",
            (start21, session, session, lo, hi, session, runup5, start5, session, runup21))
        return sorted(s for (s,) in rows)

    def put_splits(self, rows: list[dict]) -> None:
        if rows:
            with self.lock:
                self._insert("splits", [(r["symbol"], r["date"], r["ratio"]) for r in rows], 3)

    def splits_until(self, as_of: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for sym, d in self._q("SELECT symbol, date FROM splits WHERE date <= ? ORDER BY date", (as_of,)):
            out.setdefault(sym, []).append(d.isoformat())
        return out

    # ------------------------------------------------------------ scan log: append-only
    def log_hits(self, rows: list[dict]) -> int:
        """Append; a (session, symbol) already logged is left exactly as it was."""
        if not rows:
            return 0
        with self.lock:
            before = self.con.execute("SELECT count(*) FROM scan_log").fetchone()[0]
            self._insert("scan_log", [tuple(r[c] for c in LOG_COLS) for r in rows], len(LOG_COLS),
                         verb="INSERT OR IGNORE")
            return self.con.execute("SELECT count(*) FROM scan_log").fetchone()[0] - before

    def logged_sessions(self) -> set[str]:
        return {d.isoformat() for (d,) in self._q("SELECT DISTINCT session FROM scan_log")}

    def scan_rows(self, session: str | None = None, symbol: str | None = None,
                  since: str | None = None) -> list[dict]:
        where, params = [], []
        for col, op, val in (("session", "=", session), ("symbol", "=", symbol), ("session", ">=", since)):
            if val is not None:
                where.append(f"{col} {op} ?")
                params.append(val)
        sql = ("SELECT " + ", ".join(LOG_COLS) + " FROM scan_log"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY session, symbol")
        out = []
        for r in self._q(sql, params):
            d = dict(zip(LOG_COLS, r))
            d["session"] = d["session"].isoformat()
            d["logged_at"] = d["logged_at"].isoformat(timespec="seconds")
            out.append(d)
        return out

    def mark_scanned(self, session: str) -> None:
        """Record that a session was screened even if it had no hits."""
        with self.lock:
            self.con.execute("CREATE TABLE IF NOT EXISTS scanned (session DATE PRIMARY KEY)")
            self.con.execute("INSERT OR IGNORE INTO scanned VALUES (?)", (session,))

    def scanned_sessions(self) -> set[str]:
        with self.lock:
            self.con.execute("CREATE TABLE IF NOT EXISTS scanned (session DATE PRIMARY KEY)")
            return {d.isoformat() for (d,) in self.con.execute("SELECT session FROM scanned").fetchall()}

    # ------------------------------------------------------------ outcomes
    def put_outcome(self, o: dict) -> None:
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?,?,?)",
                             (o["symbol"], o["first_logged"], o["label"], o.get("peak_date"), o.get("peak"),
                              o.get("drawdown"), o.get("decided_on")))

    def outcomes(self) -> list[dict]:
        cols = ("symbol", "first_logged", "label", "peak_date", "peak", "drawdown", "decided_on")
        out = []
        for r in self._q("SELECT " + ", ".join(cols) + " FROM outcomes ORDER BY first_logged, symbol"):
            d = dict(zip(cols, r))
            for k in ("first_logged", "peak_date", "decided_on"):
                d[k] = d[k].isoformat() if d[k] else None
            out.append(d)
        return out

    def log_run(self, sessions: int, hits: int, status: str) -> None:
        with self.lock:
            self.con.execute("INSERT INTO scan_runs VALUES (?,?,?,?)", (_now(), sessions, hits, status))

    def last_run(self) -> dict | None:
        r = self._q("SELECT ts, sessions_scanned, hits, status FROM scan_runs ORDER BY ts DESC LIMIT 1")
        return dict(zip(("ts", "sessions_scanned", "hits", "status"), r[0])) if r else None

    def close(self) -> None:
        with self.lock:
            self.con.close()
