import os, json, sqlite3
from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("SQLITE_DB_PATH")
if not DB_PATH:
    raise RuntimeError("SQLITE_DB_PATH is not set")

def getUser(telegram_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "SELECT telegram_id, state, data FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        # data в БД хранится как JSON-строка; здесь всегда возвращаем dict
        raw = row[2] or "{}"
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            data = {}
        return {"telegram_id": row[0], "state": row[1] or "", "data": data}

def ensureUserExists(telegram_id: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO users (telegram_id, state, data) VALUES (?, '', '{}')",
            (telegram_id,),
        )
        con.commit()

def setUserState(telegram_id: int, state: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE users SET state = ? WHERE telegram_id = ?", (state, telegram_id))
        con.commit()

def setUserData(telegram_id: int, data: dict) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE users SET data = ? WHERE telegram_id = ?",
            (json.dumps(data, ensure_ascii=False), telegram_id),
        )
        con.commit()

def persistUpdates(updates) -> None:
    if isinstance(updates, dict):
        updates = [updates]
    rows = [(json.dumps(u, ensure_ascii=False),) for u in updates]
    with sqlite3.connect(DB_PATH) as con:
        con.executemany("INSERT INTO telegram_updates (payload) VALUES (?)", rows)
        con.commit()

def recreateDatabase(drop_existing: bool = True) -> None:
    import pathlib
    db_path = pathlib.Path(DB_PATH).expanduser()

    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    if drop_existing and db_path.exists():
        db_path.unlink()

    import sqlite3
    with sqlite3.connect(str(db_path)) as con:
        cur = con.cursor()

        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")

        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                state       TEXT NOT NULL DEFAULT '',
                data        TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS telegram_updates (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_state ON users(state);
            """
        )

        con.commit()