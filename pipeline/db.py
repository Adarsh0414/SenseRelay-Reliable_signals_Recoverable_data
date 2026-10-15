"""SQLite persistence, uniqueness, loss ledger, watermarks, and peak checkpoints.

The device database is the source of truth for every sample that the collector
has accepted. Connections use WAL + synchronous=FULL. Data is bulk committed in
small, explicit transactions; successful commits are the durability boundary.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable, Sequence

SAMPLE_RATE = 400
CHANNELS = {1: 3, 2: 2}


def _now() -> float:
    return time.time()


def canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


class Database:
    def __init__(self, path: str):
        self.path = str(Path(path).expanduser())
        Path(self.path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, isolation_level="DEFERRED")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    ended INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS samples (
                    session_id TEXT NOT NULL,
                    sensor INTEGER NOT NULL CHECK(sensor IN (1,2)),
                    sample_index INTEGER NOT NULL CHECK(sample_index >= 0),
                    values_json TEXT NOT NULL,
                    received_at REAL NOT NULL,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(session_id, sensor, sample_index),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_samples_upload ON samples(uploaded, received_at);
                CREATE INDEX IF NOT EXISTS idx_samples_window ON samples(session_id, sensor, sample_index);
                CREATE TABLE IF NOT EXISTS losses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sensor INTEGER NOT NULL CHECK(sensor IN (1,2)),
                    from_index INTEGER NOT NULL CHECK(from_index >= 0),
                    to_index INTEGER,
                    reason TEXT NOT NULL,
                    recorded_at REAL NOT NULL,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    CHECK(to_index IS NULL OR to_index >= from_index),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_losses_range ON losses(session_id, sensor, from_index, to_index);
                CREATE INDEX IF NOT EXISTS idx_losses_upload ON losses(uploaded, recorded_at);
                CREATE TABLE IF NOT EXISTS watermarks (
                    session_id TEXT NOT NULL,
                    sensor INTEGER NOT NULL CHECK(sensor IN (1,2)),
                    next_index INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(session_id, sensor),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS peak_state (
                    session_id TEXT PRIMARY KEY,
                    next_candidate INTEGER NOT NULL DEFAULT 800,
                    last_peak_index INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS peaks (
                    session_id TEXT NOT NULL,
                    sample_index INTEGER NOT NULL,
                    PRIMARY KEY(session_id, sample_index),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS window_modes (
                    session_id TEXT NOT NULL,
                    window_index INTEGER NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('online','offline')),
                    prior_peak_index INTEGER,
                    assigned_at REAL NOT NULL,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(session_id, window_index),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_window_modes_upload ON window_modes(uploaded, assigned_at);
                CREATE TABLE IF NOT EXISTS results (
                    session_id TEXT NOT NULL,
                    window_index INTEGER NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('online','offline')),
                    result_json TEXT NOT NULL,
                    calculated_at REAL NOT NULL,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(session_id, window_index, mode),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_results_upload ON results(uploaded, calculated_at);
                CREATE TABLE IF NOT EXISTS integrity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    sensor INTEGER,
                    sample_index INTEGER,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def ensure_session(self, session_id: str) -> None:
        now = _now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, created_at, last_seen_at) VALUES(?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
                (session_id, now, now),
            )

    def session_exists(self, session_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)).fetchone() is not None

    def delete_session(self, session_id: str) -> bool:
        """Delete one explicitly requested session and all rows owned by it.

        This is used only by the local synthetic-demo reset action; callers must
        restrict the identifier to the fixed demo session rather than user input.
        """
        with self.connect() as conn:
            exists = conn.execute("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)).fetchone() is not None
            for table in ("peaks", "peak_state", "watermarks", "window_modes", "results", "losses", "samples"):
                conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM integrity_events WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            return exists

    def is_session_ended(self, session_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT ended FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return bool(row[0]) if row else False

    def mark_session_ended(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET ended=1, last_seen_at=? WHERE session_id=?", (_now(), session_id))

    def get_sessions(self) -> list[str]:
        with self.connect() as conn:
            return [r[0] for r in conn.execute("SELECT session_id FROM sessions ORDER BY created_at")]

    def get_watermark(self, session_id: str, sensor: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT next_index FROM watermarks WHERE session_id=? AND sensor=?", (session_id, sensor)
            ).fetchone()
            return int(row[0]) if row else 0

    def get_watermarks(self, session_id: str) -> dict[int, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT sensor,next_index FROM watermarks WHERE session_id=?", (session_id,)).fetchall()
            out = {int(r["sensor"]): int(r["next_index"]) for r in rows}
        return {1: out.get(1, 0), 2: out.get(2, 0)}

    def _ensure_session_conn(self, conn: sqlite3.Connection, session_id: str) -> None:
        now = _now()
        conn.execute(
            "INSERT INTO sessions(session_id, created_at, last_seen_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (session_id, now, now),
        )

    def _add_event_conn(
        self, conn: sqlite3.Connection, event_type: str, detail: str,
        session_id: str | None = None, sensor: int | None = None, sample_index: int | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO integrity_events(session_id,sensor,sample_index,event_type,detail,created_at) VALUES(?,?,?,?,?,?)",
            (session_id, sensor, sample_index, event_type, detail[:2000], _now()),
        )

    def add_event(
        self, event_type: str, detail: str, session_id: str | None = None,
        sensor: int | None = None, sample_index: int | None = None,
    ) -> None:
        with self.connect() as conn:
            self._add_event_conn(conn, event_type, detail, session_id, sensor, sample_index)

    def _resolve_loss_index_conn(self, conn: sqlite3.Connection, session_id: str, sensor: int, idx: int) -> None:
        rows = conn.execute(
            "SELECT id,from_index,to_index,reason,recorded_at,uploaded FROM losses "
            "WHERE session_id=? AND sensor=? AND from_index<=? AND (to_index IS NULL OR to_index>=?)",
            (session_id, sensor, idx, idx),
        ).fetchall()
        for row in rows:
            start, end = int(row["from_index"]), row["to_index"]
            reason = str(row["reason"])
            if start == idx and end == idx:
                conn.execute("DELETE FROM losses WHERE id=?", (row["id"],))
            elif start == idx:
                conn.execute("UPDATE losses SET from_index=? WHERE id=?", (idx + 1, row["id"]))
            elif end == idx:
                conn.execute("UPDATE losses SET to_index=? WHERE id=?", (idx - 1, row["id"]))
            else:
                conn.execute("UPDATE losses SET to_index=? WHERE id=?", (idx - 1, row["id"]))
                conn.execute(
                    "INSERT INTO losses(session_id,sensor,from_index,to_index,reason,recorded_at,uploaded) VALUES(?,?,?,?,?,?,?)",
                    (session_id, sensor, idx + 1, end, reason, row["recorded_at"], row["uploaded"]),
                )

    def _advance_watermark_conn(self, conn: sqlite3.Connection, session_id: str, sensor: int) -> int:
        row = conn.execute(
            "SELECT next_index FROM watermarks WHERE session_id=? AND sensor=?", (session_id, sensor)
        ).fetchone()
        cursor = int(row[0]) if row else 0
        sample_rows = conn.execute(
            "SELECT sample_index FROM samples WHERE session_id=? AND sensor=? AND sample_index>=? ORDER BY sample_index",
            (session_id, sensor, cursor),
        ).fetchall()
        loss_rows = conn.execute(
            "SELECT from_index,to_index FROM losses WHERE session_id=? AND sensor=? AND to_index IS NOT NULL AND to_index>=?",
            (session_id, sensor, cursor),
        ).fetchall()
        spans: list[tuple[int, int]] = [(int(r[0]), int(r[0])) for r in sample_rows]
        spans.extend((int(r[0]), int(r[1])) for r in loss_rows)
        spans.sort(key=lambda pair: (pair[0], pair[1]))
        next_index = cursor
        for lo, hi in spans:
            if hi < next_index:
                continue
            if lo > next_index:
                break
            next_index = max(next_index, hi + 1)
        conn.execute(
            "INSERT INTO watermarks(session_id,sensor,next_index,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(session_id,sensor) DO UPDATE SET next_index=excluded.next_index,updated_at=excluded.updated_at",
            (session_id, sensor, next_index, _now()),
        )
        return next_index

    def add_samples(self, samples: Sequence[dict[str, Any]], uploaded: bool = False) -> dict[str, int]:
        """Insert samples idempotently. Different values at an existing key are logged, never overwritten."""
        inserted = duplicates = conflicts = 0
        touched: set[tuple[str, int]] = set()
        loss_presence: dict[tuple[str, int], bool] = {}
        known_sessions: set[str] = set()
        with self.connect() as conn:
            for item in samples:
                session_id, sensor, idx = str(item["session_id"]), int(item["sensor"]), int(item["index"])
                vals = [int(v) for v in item["values"]]
                if sensor not in CHANNELS or len(vals) != CHANNELS[sensor]:
                    self._add_event_conn(conn, "invalid_sample_shape", f"Expected {CHANNELS.get(sensor)} channels; got {len(vals)}", session_id, sensor, idx)
                    continue
                if any(v < -8_388_608 or v > 8_388_607 for v in vals):
                    self._add_event_conn(conn, "out_of_range_value", "Value outside signed 24-bit range", session_id, sensor, idx)
                    continue
                if session_id not in known_sessions:
                    self._ensure_session_conn(conn, session_id)
                    known_sessions.add(session_id)
                group = (session_id, sensor)
                if group not in loss_presence:
                    loss_presence[group] = conn.execute(
                        "SELECT 1 FROM losses WHERE session_id=? AND sensor=? LIMIT 1", group
                    ).fetchone() is not None
                packed = canonical_json(vals)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO samples(session_id,sensor,sample_index,values_json,received_at,uploaded) VALUES(?,?,?,?,?,?)",
                    (session_id, sensor, idx, packed, _now(), int(uploaded)),
                )
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    prior = conn.execute(
                        "SELECT values_json FROM samples WHERE session_id=? AND sensor=? AND sample_index=?",
                        (session_id, sensor, idx),
                    ).fetchone()
                    if prior and prior["values_json"] != packed:
                        conflicts += 1
                        self._add_event_conn(
                            conn, "duplicate_value_conflict",
                            f"Existing={prior['values_json']}; incoming={packed}; original sample retained",
                            session_id, sensor, idx,
                        )
                    else:
                        duplicates += 1
                    if uploaded:
                        conn.execute("UPDATE samples SET uploaded=1 WHERE session_id=? AND sensor=? AND sample_index=?", (session_id, sensor, idx))
                if loss_presence[group]:
                    self._resolve_loss_index_conn(conn, session_id, sensor, idx)
                touched.add(group)
            for session_id in known_sessions:
                conn.execute("UPDATE sessions SET last_seen_at=? WHERE session_id=?", (_now(), session_id))
            for session_id, sensor in touched:
                self._advance_watermark_conn(conn, session_id, sensor)
        return {"inserted": inserted, "duplicates": duplicates, "conflicts": conflicts}

    def add_losses(self, losses: Sequence[dict[str, Any]], uploaded: bool = False) -> int:
        """Record known losses without overlapping stored samples or earlier loss records.

        When repeated mock reads report expanding buffer-overflow ranges, preserve the
        first recorded explanation for already-accounted indexes and insert only the
        still-unaccounted portions of the newer range.
        """
        inserted = 0
        touched: set[tuple[str, int]] = set()
        known_sessions: set[str] = set()
        with self.connect() as conn:
            for item in losses:
                session_id = str(item["session_id"])
                sensor = int(item["sensor"])
                start = int(item["from_index"])
                end = item.get("to_index")
                end = None if end is None else int(end)
                reason = str(item.get("reason") or "unspecified_loss")[:500]
                if sensor not in (1, 2) or start < 0 or (end is not None and end < start):
                    self._add_event_conn(conn, "invalid_loss_record", canonical_json(item), session_id, sensor, start)
                    continue
                if session_id not in known_sessions:
                    self._ensure_session_conn(conn, session_id)
                    known_sessions.add(session_id)

                # Build blocker intervals from rows already persisted and from previously
                # recorded loss ranges. The incoming interval is reduced by their union.
                if end is None:
                    sample_rows = conn.execute(
                        "SELECT sample_index FROM samples WHERE session_id=? AND sensor=? AND sample_index>=? ORDER BY sample_index",
                        (session_id, sensor, start),
                    ).fetchall()
                else:
                    sample_rows = conn.execute(
                        "SELECT sample_index FROM samples WHERE session_id=? AND sensor=? AND sample_index BETWEEN ? AND ? ORDER BY sample_index",
                        (session_id, sensor, start, end),
                    ).fetchall()
                existing_losses = conn.execute(
                    "SELECT from_index,to_index FROM losses WHERE session_id=? AND sensor=? "
                    "AND (to_index IS NULL OR to_index>=?) AND (? IS NULL OR from_index<=?)",
                    (session_id, sensor, start, end, end),
                ).fetchall()
                blockers: list[tuple[int, int | None]] = [(int(r[0]), int(r[0])) for r in sample_rows]
                blockers.extend((int(r[0]), None if r[1] is None else int(r[1])) for r in existing_losses)
                blockers.sort(key=lambda span: span[0])

                merged: list[tuple[int, int | None]] = []
                for block_start, block_end in blockers:
                    if not merged:
                        merged.append((block_start, block_end))
                        continue
                    prev_start, prev_end = merged[-1]
                    touches = prev_end is None or block_start <= prev_end + 1
                    if touches:
                        merged[-1] = (prev_start, None if prev_end is None or block_end is None else max(prev_end, block_end))
                    else:
                        merged.append((block_start, block_end))

                segments: list[tuple[int, int | None]] = []
                cursor = start
                consumed_to_infinity = False
                for block_start, block_end in merged:
                    if block_end is not None and block_end < cursor:
                        continue
                    if end is not None and cursor > end:
                        consumed_to_infinity = True
                        break
                    clipped_start = max(cursor, block_start)
                    if clipped_start > cursor:
                        segments.append((cursor, clipped_start - 1))
                    if block_end is None:
                        consumed_to_infinity = True
                        break
                    cursor = max(cursor, block_end + 1)
                    if end is not None and cursor > end:
                        consumed_to_infinity = True
                        break
                if not consumed_to_infinity and (end is None or cursor <= end):
                    segments.append((cursor, end))

                for seg_start, seg_end in segments:
                    conn.execute(
                        "INSERT INTO losses(session_id,sensor,from_index,to_index,reason,recorded_at,uploaded) VALUES(?,?,?,?,?,?,?)",
                        (session_id, sensor, seg_start, seg_end, reason, _now(), int(uploaded)),
                    )
                    inserted += 1
                    touched.add((session_id, sensor))
            for session_id in known_sessions:
                conn.execute("UPDATE sessions SET last_seen_at=? WHERE session_id=?", (_now(), session_id))
            for session_id, sensor in touched:
                self._advance_watermark_conn(conn, session_id, sensor)
        return inserted

    def reconcile_watermarks(self, session_id: str) -> None:
        with self.connect() as conn:
            for sensor in (1, 2):
                self._advance_watermark_conn(conn, session_id, sensor)

    def get_samples(self, session_id: str, sensor: int, start: int, end: int) -> dict[int, list[int]]:
        if end < start:
            return {}
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT sample_index,values_json FROM samples WHERE session_id=? AND sensor=? AND sample_index BETWEEN ? AND ? ORDER BY sample_index",
                (session_id, sensor, start, end),
            ).fetchall()
        return {int(r["sample_index"]): json.loads(r["values_json"]) for r in rows}

    def get_peak_indices(self, session_id: str, start: int, end: int) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT sample_index FROM peaks WHERE session_id=? AND sample_index BETWEEN ? AND ? ORDER BY sample_index",
                (session_id, start, end),
            ).fetchall()
        return [int(r[0]) for r in rows]

    def get_prior_peak(self, session_id: str, before_index: int) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(sample_index) FROM peaks WHERE session_id=? AND sample_index<?",
                (session_id, before_index),
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def advance_peak_detector(self, session_id: str) -> int:
        """Incrementally detect peaks in O(new samples) time with a sliding 800-sample maximum."""
        self.reconcile_watermarks(session_id)
        with self.connect() as conn:
            wm_row = conn.execute(
                "SELECT next_index FROM watermarks WHERE session_id=? AND sensor=1", (session_id,)
            ).fetchone()
            watermark = int(wm_row[0]) if wm_row else 0
            conn.execute(
                "INSERT OR IGNORE INTO peak_state(session_id,next_candidate,last_peak_index) VALUES(?,800,NULL)",
                (session_id,),
            )
            state = conn.execute("SELECT next_candidate,last_peak_index FROM peak_state WHERE session_id=?", (session_id,)).fetchone()
            next_candidate = int(state["next_candidate"])
            last_peak = int(state["last_peak_index"]) if state["last_peak_index"] is not None else None
            candidate_limit = watermark - 2
            if next_candidate > candidate_limit:
                return 0
            context_start = next_candidate - 800
            query_end = candidate_limit + 1
            rows = conn.execute(
                "SELECT sample_index,values_json FROM samples WHERE session_id=? AND sensor=1 AND sample_index BETWEEN ? AND ?",
                (session_id, context_start, query_end),
            ).fetchall()
            values: list[int | None] = [None] * (query_end - context_start + 1)
            for row in rows:
                vals = json.loads(row["values_json"])
                values[int(row["sample_index"]) - context_start] = int(vals[1])
            # The initial 800 values are the history before next_candidate.
            maxq: deque[tuple[int, int]] = deque()
            missing = 0
            for idx in range(context_start, next_candidate):
                value = values[idx - context_start]
                if value is None:
                    missing += 1
                else:
                    while maxq and maxq[-1][1] <= value:
                        maxq.pop()
                    maxq.append((idx, value))
            new_peaks = 0
            for idx in range(next_candidate, candidate_limit + 1):
                current = values[idx - context_start]
                previous = values[idx - 1 - context_start]
                following = values[idx + 1 - context_start]
                if (
                    missing == 0 and current is not None and previous is not None and following is not None
                    and maxq and current > previous and current > following and current > (maxq[0][1] / 2)
                    and (last_peak is None or idx - last_peak >= 100)
                ):
                    conn.execute("INSERT OR IGNORE INTO peaks(session_id,sample_index) VALUES(?,?)", (session_id, idx))
                    last_peak = idx
                    new_peaks += 1
                outgoing_idx = idx - 800
                outgoing = values[outgoing_idx - context_start]
                if outgoing is None:
                    missing -= 1
                if maxq and maxq[0][0] == outgoing_idx:
                    maxq.popleft()
                if current is None:
                    missing += 1
                else:
                    while maxq and maxq[-1][1] <= current:
                        maxq.pop()
                    maxq.append((idx, current))
            conn.execute(
                "UPDATE peak_state SET next_candidate=?,last_peak_index=? WHERE session_id=?",
                (candidate_limit + 1, last_peak, session_id),
            )
            return new_peaks

    def assign_ready_windows(self, session_id: str, mode: str) -> int:
        """Persist a mode for each locally closed window before any upload is attempted."""
        watermarks = self.get_watermarks(session_id)
        if self.is_session_ended(session_id):
            # At a known end-of-session there will be no sample after the final sample.
            # Complete one-second windows still need stats/results; peak detection will
            # naturally reject the last sample because its following neighbor is absent.
            ready_count = min(watermarks[1] // SAMPLE_RATE, watermarks[2] // SAMPLE_RATE)
        else:
            ready_count = min(watermarks[2] // SAMPLE_RATE, max(0, (watermarks[1] - 1) // SAMPLE_RATE))
        if ready_count <= 0:
            return 0
        self.advance_peak_detector(session_id)
        inserted = 0
        with self.connect() as conn:
            existing = {
                int(r[0]) for r in conn.execute(
                    "SELECT window_index FROM window_modes WHERE session_id=? AND window_index<?",
                    (session_id, ready_count),
                )
            }
            for window in range(ready_count):
                if window in existing:
                    continue
                heart_start = SAMPLE_RATE * (window - 4)
                candidate_start = max(800, heart_start - 100)
                prior_peak = None
                if window >= 4:
                    p = conn.execute(
                        "SELECT MAX(sample_index) FROM peaks WHERE session_id=? AND sample_index<?",
                        (session_id, candidate_start),
                    ).fetchone()
                    prior_peak = int(p[0]) if p and p[0] is not None else None
                conn.execute(
                    "INSERT OR IGNORE INTO window_modes(session_id,window_index,mode,prior_peak_index,assigned_at) VALUES(?,?,?,?,?)",
                    (session_id, window, mode, prior_peak, _now()),
                )
                inserted += 1
        return inserted

    def pending_mode_windows(self, recent_limit: int = 500, backlog_limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            recent = conn.execute(
                "SELECT * FROM window_modes WHERE uploaded=0 ORDER BY assigned_at DESC LIMIT ?", (recent_limit,)
            ).fetchall()
            oldest = conn.execute(
                "SELECT * FROM window_modes WHERE uploaded=0 ORDER BY assigned_at ASC LIMIT ?", (backlog_limit,)
            ).fetchall()
        unique: dict[tuple[str, int], sqlite3.Row] = {}
        for r in [*recent, *oldest]:
            unique[(str(r["session_id"]), int(r["window_index"]))] = r
        return [
            {"session_id": r["session_id"], "window_index": int(r["window_index"]), "mode": r["mode"],
             "prior_peak_index": r["prior_peak_index"], "assigned_at": float(r["assigned_at"])}
            for r in unique.values()
        ]

    def pending_offline_results(self, recent_limit: int = 500, backlog_limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            recent = conn.execute(
                "SELECT * FROM results WHERE uploaded=0 AND mode='offline' ORDER BY calculated_at DESC LIMIT ?", (recent_limit,)
            ).fetchall()
            oldest = conn.execute(
                "SELECT * FROM results WHERE uploaded=0 AND mode='offline' ORDER BY calculated_at ASC LIMIT ?", (backlog_limit,)
            ).fetchall()
        unique: dict[tuple[str, int, str], sqlite3.Row] = {}
        for r in [*recent, *oldest]:
            unique[(str(r["session_id"]), int(r["window_index"]), str(r["mode"]))] = r
        return [
            {"session_id": r["session_id"], "window_index": int(r["window_index"]), "mode": r["mode"],
             "result": json.loads(r["result_json"])} for r in unique.values()
        ]

    def pending_samples(self, live_limit: int = 8000, backlog_limit: int = 4000, recent_seconds: float = 15.0) -> list[dict[str, Any]]:
        cutoff = _now() - recent_seconds
        with self.connect() as conn:
            live = conn.execute(
                "SELECT * FROM samples WHERE uploaded=0 AND received_at>=? ORDER BY received_at DESC LIMIT ?",
                (cutoff, live_limit),
            ).fetchall()
            backlog = conn.execute(
                "SELECT * FROM samples WHERE uploaded=0 AND received_at<? ORDER BY received_at ASC,session_id,sensor,sample_index LIMIT ?",
                (cutoff, backlog_limit),
            ).fetchall()
        unique: dict[tuple[str, int, int], sqlite3.Row] = {}
        for r in [*live, *backlog]:
            unique[(str(r["session_id"]), int(r["sensor"]), int(r["sample_index"]))] = r
        return [
            {"session_id": r["session_id"], "sensor": int(r["sensor"]), "index": int(r["sample_index"]),
             "values": json.loads(r["values_json"])} for r in unique.values()
        ]

    def pending_losses(self, recent_limit: int = 1000, backlog_limit: int = 1000) -> list[dict[str, Any]]:
        with self.connect() as conn:
            recent = conn.execute("SELECT * FROM losses WHERE uploaded=0 ORDER BY recorded_at DESC LIMIT ?", (recent_limit,)).fetchall()
            oldest = conn.execute("SELECT * FROM losses WHERE uploaded=0 ORDER BY recorded_at ASC LIMIT ?", (backlog_limit,)).fetchall()
        unique = {int(r["id"]): r for r in [*recent, *oldest]}
        return [
            {"id": int(r["id"]), "session_id": r["session_id"], "sensor": int(r["sensor"]),
             "from_index": int(r["from_index"]), "to_index": None if r["to_index"] is None else int(r["to_index"]),
             "reason": r["reason"]} for r in unique.values()
        ]

    def mark_uploaded(self, samples: Sequence[dict[str, Any]] = (), losses: Sequence[dict[str, Any]] = (),
                      window_modes: Sequence[dict[str, Any]] = (), offline_results: Sequence[dict[str, Any]] = ()) -> None:
        with self.connect() as conn:
            for s in samples:
                conn.execute("UPDATE samples SET uploaded=1 WHERE session_id=? AND sensor=? AND sample_index=?", (s["session_id"], s["sensor"], s["index"]))
            for loss in losses:
                if "id" in loss:
                    conn.execute("UPDATE losses SET uploaded=1 WHERE id=?", (loss["id"],))
                else:
                    conn.execute("UPDATE losses SET uploaded=1 WHERE session_id=? AND sensor=? AND from_index=? AND to_index IS ? AND reason=?",
                                 (loss["session_id"], loss["sensor"], loss["from_index"], loss.get("to_index"), loss["reason"]))
            for row in window_modes:
                conn.execute("UPDATE window_modes SET uploaded=1 WHERE session_id=? AND window_index=?", (row["session_id"], row["window_index"]))
            for row in offline_results:
                conn.execute("UPDATE results SET uploaded=1 WHERE session_id=? AND window_index=? AND mode='offline'", (row["session_id"], row["window_index"]))

    def insert_window_modes(self, rows: Sequence[dict[str, Any]], uploaded: bool = False) -> None:
        known_sessions: set[str] = set()
        with self.connect() as conn:
            for row in rows:
                session_id = str(row["session_id"])
                if session_id not in known_sessions:
                    self._ensure_session_conn(conn, session_id)
                    known_sessions.add(session_id)
                conn.execute(
                    "INSERT INTO window_modes(session_id,window_index,mode,prior_peak_index,assigned_at,uploaded) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(session_id,window_index) DO UPDATE SET "
                    "mode=CASE WHEN excluded.mode='offline' AND window_modes.mode='online' "
                    "AND NOT EXISTS (SELECT 1 FROM results r WHERE r.session_id=excluded.session_id "
                    "AND r.window_index=excluded.window_index AND r.mode='online') THEN 'offline' ELSE window_modes.mode END, "
                    "prior_peak_index=COALESCE(window_modes.prior_peak_index,excluded.prior_peak_index), "
                    "uploaded=MAX(window_modes.uploaded,excluded.uploaded)",
                    (row["session_id"], int(row["window_index"]), row["mode"], row.get("prior_peak_index"), float(row.get("assigned_at", _now())), int(uploaded)),
                )

    def insert_result(self, session_id: str, window_index: int, mode: str, result: dict[str, Any], uploaded: bool = False) -> None:
        with self.connect() as conn:
            self._ensure_session_conn(conn, session_id)
            packed = canonical_json(result)
            old = conn.execute("SELECT result_json FROM results WHERE session_id=? AND window_index=? AND mode=?", (session_id, window_index, mode)).fetchone()
            if old is not None and old["result_json"] != packed:
                self._add_event_conn(conn, "result_recalculation_conflict", f"Window {window_index} mode {mode}: retained existing result", session_id, None, window_index)
            conn.execute(
                "INSERT INTO results(session_id,window_index,mode,result_json,calculated_at,uploaded) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(session_id,window_index,mode) DO UPDATE SET uploaded=MAX(results.uploaded,excluded.uploaded)",
                (session_id, window_index, mode, packed, _now(), int(uploaded)),
            )

    def insert_offline_results(self, rows: Sequence[dict[str, Any]], uploaded: bool = False) -> None:
        for row in rows:
            if row.get("mode") != "offline":
                continue
            session_id, window_index = str(row["session_id"]), int(row["window_index"])
            # If an ambiguous HTTP timeout nevertheless delivered a valid online result, prefer that result.
            with self.connect() as conn:
                online_exists = conn.execute(
                    "SELECT 1 FROM results WHERE session_id=? AND window_index=? AND mode='online'",
                    (session_id, window_index),
                ).fetchone() is not None
            if not online_exists:
                self.insert_result(session_id, window_index, "offline", row["result"], uploaded=uploaded)

    def reclassify_unuploaded_online_to_offline(self, session_id: str | None = None) -> int:
        """On a failed cloud request, locally finalize unacknowledged online windows offline.

        A request can time out after the server committed it. The cloud resolves that ambiguity
        deterministically: it retains an online result if one exists, otherwise accepts the offline
        result/checkpoint on retry.
        """
        with self.connect() as conn:
            if session_id is None:
                cur = conn.execute(
                    "UPDATE window_modes SET mode='offline' WHERE uploaded=0 AND mode='online'"
                )
            else:
                cur = conn.execute(
                    "UPDATE window_modes SET mode='offline' WHERE uploaded=0 AND mode='online' AND session_id=?",
                    (session_id,),
                )
            return int(cur.rowcount)

    def results_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT result_json FROM results WHERE session_id=? ORDER BY window_index,mode", (session_id,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def unprocessed_online_modes(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT wm.* FROM window_modes wm LEFT JOIN results r ON r.session_id=wm.session_id AND r.window_index=wm.window_index AND r.mode='online' "
                "WHERE wm.session_id=? AND wm.mode='online' AND r.session_id IS NULL ORDER BY wm.window_index",
                (session_id,),
            ).fetchall()
        return [{"session_id": r["session_id"], "window_index": int(r["window_index"]), "mode": r["mode"],
                 "prior_peak_index": r["prior_peak_index"]} for r in rows]

    def unprocessed_offline_modes(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT wm.* FROM window_modes wm LEFT JOIN results r ON r.session_id=wm.session_id AND r.window_index=wm.window_index AND r.mode='offline' "
                "WHERE wm.session_id=? AND wm.mode='offline' AND r.session_id IS NULL ORDER BY wm.window_index",
                (session_id,),
            ).fetchall()
        return [{"session_id": r["session_id"], "window_index": int(r["window_index"]), "mode": r["mode"],
                 "prior_peak_index": r["prior_peak_index"]} for r in rows]

    def range_is_covered(self, session_id: str, sensor: int, start: int, end: int) -> bool:
        """True only if every index in [start,end] is either stored or explicitly recorded lost."""
        if end < start:
            return True
        with self.connect() as conn:
            sample_rows = conn.execute(
                "SELECT sample_index FROM samples WHERE session_id=? AND sensor=? AND sample_index BETWEEN ? AND ? ORDER BY sample_index",
                (session_id, sensor, start, end),
            ).fetchall()
            loss_rows = conn.execute(
                "SELECT from_index,to_index FROM losses WHERE session_id=? AND sensor=? AND to_index IS NOT NULL "
                "AND from_index<=? AND to_index>=?",
                (session_id, sensor, end, start),
            ).fetchall()
        spans = [(int(r[0]), int(r[0])) for r in sample_rows]
        spans += [(max(start, int(r[0])), min(end, int(r[1]))) for r in loss_rows]
        spans.sort()
        cursor = start
        for lo, hi in spans:
            if hi < cursor:
                continue
            if lo > cursor:
                return False
            cursor = max(cursor, hi + 1)
            if cursor > end:
                return True
        return cursor > end

    def get_loss_ranges(self, session_id: str, sensor: int, start: int, end: int) -> list[tuple[int, int]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT from_index,to_index FROM losses WHERE session_id=? AND sensor=? AND to_index IS NOT NULL "
                "AND from_index<=? AND to_index>=?",
                (session_id, sensor, end, start),
            ).fetchall()
        return [(max(start, int(r[0])), min(end, int(r[1]))) for r in rows]

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT state_value FROM runtime_state WHERE state_key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runtime_state(state_key,state_value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=excluded.updated_at",
                (key, value, _now()),
            )

    def status(self, current_mode: str, cloud_samples: int | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            saved = int(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
            backlog = int(conn.execute("SELECT COUNT(*) FROM samples WHERE uploaded=0").fetchone()[0])
            sessions = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        return {"mode": current_mode, "samples_saved": saved, "samples_in_cloud": cloud_samples, "backlog": backlog, "sessions": sessions}

    def sample_count(self, session_id: str | None = None) -> int:
        with self.connect() as conn:
            if session_id is None:
                return int(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
            return int(conn.execute("SELECT COUNT(*) FROM samples WHERE session_id=?", (session_id,)).fetchone()[0])

    def loss_count(self, session_id: str | None = None) -> int:
        with self.connect() as conn:
            if session_id is None:
                return int(conn.execute("SELECT COUNT(*) FROM losses").fetchone()[0])
            return int(conn.execute("SELECT COUNT(*) FROM losses WHERE session_id=?", (session_id,)).fetchone()[0])

    def export_samples(self, session_id: str, from_cloud: bool = False) -> Iterable[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT sensor,sample_index,values_json FROM samples WHERE session_id=? ORDER BY sensor,sample_index", (session_id,)
            ).fetchall()
        for row in rows:
            yield {"sensor": int(row["sensor"]), "index": int(row["sample_index"]), "values": json.loads(row["values_json"])}
        with self.connect() as conn:
            losses = conn.execute(
                "SELECT sensor,from_index,to_index,reason FROM losses WHERE session_id=? ORDER BY sensor,from_index", (session_id,)
            ).fetchall()
        for row in losses:
            yield {"sensor": int(row["sensor"]), "from_index": int(row["from_index"]),
                   "to_index": None if row["to_index"] is None else int(row["to_index"]), "reason": row["reason"]}

    def cloud_sample_count(self, session_id: str | None = None) -> int:
        return self.sample_count(session_id)

    def mark_all_for_session_uploaded(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE samples SET uploaded=1 WHERE session_id=?", (session_id,))
