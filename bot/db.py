"""SQLite-сховище: профілі, прийоми їжі, вода, вага, досягнення."""

import json
import os
import sqlite3
from datetime import date, datetime, timedelta

from bot.config import DB_PATH, TIMEZONE

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    name        TEXT,
    sex         TEXT,
    age         INTEGER,
    height_cm   REAL,
    weight_kg   REAL,
    activity    TEXT,
    goal        TEXT,
    target_kcal REAL,
    protein_g   REAL,
    fat_g       REAL,
    carbs_g     REAL,
    water_ml    INTEGER DEFAULT 2000,
    reminders   INTEGER DEFAULT 1,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS meals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    day          TEXT NOT NULL,
    ts           TEXT NOT NULL,
    meal_type    TEXT,
    title        TEXT,
    items_json   TEXT,
    kcal         REAL,
    protein_g    REAL,
    fat_g        REAL,
    carbs_g      REAL,
    health_score INTEGER
);
CREATE INDEX IF NOT EXISTS idx_meals_user_day ON meals(user_id, day);
CREATE TABLE IF NOT EXISTS water (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    ml      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS weights (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    kg      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER NOT NULL,
    code    TEXT NOT NULL,
    ts      TEXT NOT NULL,
    PRIMARY KEY (user_id, code)
);
CREATE TABLE IF NOT EXISTS access (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT,
    username   TEXT,
    granted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
    code       TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    used_by    INTEGER
);
CREATE TABLE IF NOT EXISTS access_requests (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT,
    username   TEXT,
    ts         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_usage (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
"""

_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def now() -> datetime:
    return datetime.now(TIMEZONE)


def today() -> date:
    return now().date()


# --- users -------------------------------------------------------------------

def get_user(user_id: int) -> sqlite3.Row | None:
    return conn().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def ensure_user(user_id: int, name: str) -> sqlite3.Row:
    c = conn()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name, now().isoformat()),
    )
    c.commit()
    return get_user(user_id)


def update_user(user_id: int, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn().execute(f"UPDATE users SET {cols} WHERE user_id = ?", (*fields.values(), user_id))
    conn().commit()


def users_with_reminders() -> list[sqlite3.Row]:
    return conn().execute("SELECT * FROM users WHERE reminders = 1").fetchall()


# --- meals -------------------------------------------------------------------

def add_meal(user_id: int, meal_type: str, title: str, items: list[dict],
             kcal: float, protein: float, fat: float, carbs: float, health_score: int) -> int:
    ts = now()
    cur = conn().execute(
        "INSERT INTO meals (user_id, day, ts, meal_type, title, items_json, kcal, protein_g,"
        " fat_g, carbs_g, health_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, ts.date().isoformat(), ts.isoformat(), meal_type, title,
         json.dumps(items, ensure_ascii=False), kcal, protein, fat, carbs, health_score),
    )
    conn().commit()
    return cur.lastrowid


def meals_for_day(user_id: int, day: date) -> list[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM meals WHERE user_id = ? AND day = ? ORDER BY ts",
        (user_id, day.isoformat()),
    ).fetchall()


def all_meals(user_id: int) -> list[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM meals WHERE user_id = ? ORDER BY ts", (user_id,)
    ).fetchall()


def delete_last_meal(user_id: int) -> sqlite3.Row | None:
    row = conn().execute(
        "SELECT * FROM meals WHERE user_id = ? ORDER BY ts DESC LIMIT 1", (user_id,)
    ).fetchone()
    if row:
        conn().execute("DELETE FROM meals WHERE id = ?", (row["id"],))
        conn().commit()
    return row


def day_totals(user_id: int, day: date) -> dict:
    row = conn().execute(
        "SELECT COALESCE(SUM(kcal),0) kcal, COALESCE(SUM(protein_g),0) protein,"
        " COALESCE(SUM(fat_g),0) fat, COALESCE(SUM(carbs_g),0) carbs, COUNT(*) n"
        " FROM meals WHERE user_id = ? AND day = ?",
        (user_id, day.isoformat()),
    ).fetchone()
    return dict(row)


def daily_kcal(user_id: int, days: int) -> list[tuple[date, float]]:
    start = today() - timedelta(days=days - 1)
    rows = conn().execute(
        "SELECT day, SUM(kcal) kcal FROM meals WHERE user_id = ? AND day >= ? GROUP BY day",
        (user_id, start.isoformat()),
    ).fetchall()
    by_day = {r["day"]: r["kcal"] for r in rows}
    return [(start + timedelta(days=i), by_day.get((start + timedelta(days=i)).isoformat(), 0.0))
            for i in range(days)]


def meal_count(user_id: int) -> int:
    return conn().execute("SELECT COUNT(*) FROM meals WHERE user_id = ?", (user_id,)).fetchone()[0]


def streak(user_id: int) -> int:
    """Кількість днів поспіль (до сьогодні або вчора) з хоча б одним записом."""
    rows = conn().execute(
        "SELECT DISTINCT day FROM meals WHERE user_id = ? ORDER BY day DESC", (user_id,)
    ).fetchall()
    days = {date.fromisoformat(r["day"]) for r in rows}
    d = today() if today() in days else today() - timedelta(days=1)
    count = 0
    while d in days:
        count += 1
        d -= timedelta(days=1)
    return count


# --- water -------------------------------------------------------------------

def add_water(user_id: int, ml: int) -> None:
    conn().execute("INSERT INTO water (user_id, day, ml) VALUES (?, ?, ?)",
                   (user_id, today().isoformat(), ml))
    conn().commit()


def water_for_day(user_id: int, day: date) -> int:
    return conn().execute(
        "SELECT COALESCE(SUM(ml),0) FROM water WHERE user_id = ? AND day = ?",
        (user_id, day.isoformat()),
    ).fetchone()[0]


# --- weight ------------------------------------------------------------------

def add_weight(user_id: int, kg: float) -> None:
    c = conn()
    c.execute("DELETE FROM weights WHERE user_id = ? AND day = ?", (user_id, today().isoformat()))
    c.execute("INSERT INTO weights (user_id, day, kg) VALUES (?, ?, ?)",
              (user_id, today().isoformat(), kg))
    c.commit()


def weight_history(user_id: int) -> list[tuple[date, float]]:
    rows = conn().execute(
        "SELECT day, kg FROM weights WHERE user_id = ? ORDER BY day", (user_id,)
    ).fetchall()
    return [(date.fromisoformat(r["day"]), r["kg"]) for r in rows]


# --- achievements ------------------------------------------------------------

def unlock(user_id: int, code: str) -> bool:
    """Повертає True, якщо досягнення отримано вперше."""
    cur = conn().execute(
        "INSERT OR IGNORE INTO achievements (user_id, code, ts) VALUES (?, ?, ?)",
        (user_id, code, now().isoformat()),
    )
    conn().commit()
    return cur.rowcount > 0


def achievements(user_id: int) -> set[str]:
    rows = conn().execute("SELECT code FROM achievements WHERE user_id = ?", (user_id,)).fetchall()
    return {r["code"] for r in rows}


# --- access ------------------------------------------------------------------

def has_access(user_id: int) -> bool:
    return conn().execute("SELECT 1 FROM access WHERE user_id = ?", (user_id,)).fetchone() is not None


def grant_access(user_id: int, name: str, username: str | None) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO access (user_id, name, username, granted_at) VALUES (?, ?, ?, ?)",
              (user_id, name, username, now().isoformat()))
    c.execute("DELETE FROM access_requests WHERE user_id = ?", (user_id,))
    c.commit()


def revoke_access(user_id: int) -> bool:
    cur = conn().execute("DELETE FROM access WHERE user_id = ?", (user_id,))
    conn().commit()
    return cur.rowcount > 0


def access_list() -> list[sqlite3.Row]:
    return conn().execute("SELECT * FROM access ORDER BY granted_at").fetchall()


def create_invite(code: str) -> None:
    conn().execute("INSERT INTO invites (code, created_at) VALUES (?, ?)", (code, now().isoformat()))
    conn().commit()


def use_invite(code: str, user_id: int, max_age_days: int = 7) -> bool:
    """Позначає одноразове запрошення використаним. False — якщо код невалідний або старий."""
    row = conn().execute("SELECT * FROM invites WHERE code = ? AND used_by IS NULL",
                         (code,)).fetchone()
    if row is None or now() - datetime.fromisoformat(row["created_at"]) > timedelta(days=max_age_days):
        return False
    conn().execute("UPDATE invites SET used_by = ? WHERE code = ?", (user_id, code))
    conn().commit()
    return True


def add_access_request(user_id: int, name: str, username: str | None) -> bool:
    """Повертає True, якщо це перший запит від цієї людини (щоб не спамити власника)."""
    cur = conn().execute(
        "INSERT OR IGNORE INTO access_requests (user_id, name, username, ts) VALUES (?, ?, ?, ?)",
        (user_id, name, username, now().isoformat()),
    )
    conn().commit()
    return cur.rowcount > 0


# --- AI usage limit ----------------------------------------------------------

def use_ai_quota(user_id: int, limit: int) -> bool:
    """Зараховує один запит до ШІ. Повертає False, якщо денний ліміт вичерпано."""
    c = conn()
    day = today().isoformat()
    row = c.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ?",
                    (user_id, day)).fetchone()
    if row and row["count"] >= limit:
        return False
    c.execute(
        "INSERT INTO ai_usage (user_id, day, count) VALUES (?, ?, 1)"
        " ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
        (user_id, day),
    )
    c.commit()
    return True
