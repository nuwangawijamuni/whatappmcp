"""Single-host pilot storage. SQLite/WAL; exact IDs and parameterized SQL."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


def record_id(phone_id: str, message_id: str) -> str:
    return hashlib.sha256(f"{phone_id}\0{message_id}".encode()).hexdigest()


class Store:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "knowledge.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records(
                  id TEXT PRIMARY KEY, phone_id TEXT NOT NULL, title TEXT NOT NULL,
                  body TEXT NOT NULL, metadata TEXT NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                  id UNINDEXED, title, body, tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS events(
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                  attempts INTEGER NOT NULL DEFAULT 0, available_at INTEGER NOT NULL DEFAULT 0,
                  locked_until INTEGER NOT NULL DEFAULT 0, last_error TEXT
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def upsert(self, id, phone_id, title, body, metadata):
        with self.connect() as db:
            db.execute("""INSERT INTO records VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body,
                metadata=excluded.metadata, updated_at=excluded.updated_at""",
                (id, phone_id, title, body, json.dumps(metadata, ensure_ascii=False), int(time.time())))
            db.execute("DELETE FROM records_fts WHERE id=?", (id,))
            db.execute("INSERT INTO records_fts(id,title,body) VALUES(?,?,?)", (id, title, body))

    def search(self, query: str, phone_ids: set[str], limit=15):
        # Treat user input as words, never as an FTS expression or SQL expression.
        terms = list(dict.fromkeys(re.findall(r"\w+", query[:1000], flags=re.UNICODE)))[:20]
        if not terms or not phone_ids:
            return []
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        slots = ",".join("?" for _ in phone_ids)
        with self.connect() as db:
            rows = db.execute(f"""SELECT r.* FROM records_fts
                JOIN records r ON r.id=records_fts.id
                WHERE records_fts MATCH ? AND r.phone_id IN ({slots})
                ORDER BY bm25(records_fts) LIMIT ?""", (match, *sorted(phone_ids), limit)).fetchall()
        return [dict(r) for r in rows]

    def fetch(self, id: str, phone_ids: set[str]):
        if not phone_ids:
            return None
        slots = ",".join("?" for _ in phone_ids)
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM records WHERE id=? AND phone_id IN ({slots})",
                             (id, *sorted(phone_ids))).fetchone()
        return dict(row) if row else None

    def enqueue(self, raw: bytes):
        event_id = hashlib.sha256(raw).hexdigest()
        payload = raw.decode("utf-8")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO events(id,payload) VALUES(?,?)", (event_id, payload))
        return event_id

    def claim(self):
        now = int(time.time())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM events WHERE
              (status='pending' AND available_at<=?) OR
              (status='working' AND locked_until<?)
              ORDER BY rowid LIMIT 1""", (now, now)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE events SET status='working', attempts=attempts+1, locked_until=? WHERE id=?",
                       (now + 1800, row["id"]))
            out = dict(row)
            out["attempts"] += 1
        return out

    def finish(self, event, error=None, status="done"):
        with self.connect() as db:
            if error:
                status = "failed" if event["attempts"] >= 6 else "pending"
                # Never persist exception messages containing tokens or signed download URLs.
                db.execute("""UPDATE events SET status=?,last_error=?,available_at=?,locked_until=0
                    WHERE id=?""", (status, type(error).__name__, int(time.time()) + min(3600, 30 * 2**event["attempts"]), event["id"]))
            else:
                db.execute("UPDATE events SET status=?,last_error=NULL,locked_until=0 WHERE id=?", (status, event["id"]))

    def stats(self):
        with self.connect() as db:
            return {
                "records": db.execute("SELECT count(*) FROM records").fetchone()[0],
                "events": {r[0]: r[1] for r in db.execute("SELECT status,count(*) FROM events GROUP BY status")},
            }
