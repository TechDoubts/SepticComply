"""
SepticComply Database Layer v1.0
SQLite persistence for tanks, service history, and compliance records.
"""
from __future__ import annotations
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

from src.compliance_engine import ComplianceEngine, ComplianceStatus, Tank, TankType, load_engine

DB_PATH = Path(__file__).parent.parent / "data" / "septiccomply.db"

engine = load_engine()


def tank_record_to_engine(tank: TankRecord) -> Tank:
    """Convert database record to engine Tank object."""
    return Tank(
        id=tank.id,
        state=tank.state,
        county=tank.county,
        municipality=tank.municipality,
        local_board=tank.local_board,
        tank_gallons=tank.tank_gallons,
        household_size=tank.household_size,
        tank_type=TankType(tank.tank_type),
        last_pumped=date.fromisoformat(tank.last_pumped) if tank.last_pumped else None,
        installed_date=date.fromisoformat(tank.installed_date) if tank.installed_date else None,
        hauler_license=tank.hauler_license,
        hauler_expiry=tank.hauler_expiry,
    )


@dataclass
class TankRecord:
    id: str
    state: str
    county: Optional[str]
    municipality: Optional[str]
    local_board: Optional[str]
    tank_gallons: int
    household_size: int
    tank_type: str
    last_pumped: Optional[str]
    installed_date: Optional[str]
    hauler_license: Optional[str]
    hauler_expiry: Optional[str]
    created_at: str
    updated_at: str


def get_db_path() -> Path:
    """Get database path, ensuring directory exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tanks (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                county TEXT,
                municipality TEXT,
                local_board TEXT,
                tank_gallons INTEGER NOT NULL,
                household_size INTEGER NOT NULL,
                tank_type TEXT NOT NULL,
                last_pumped TEXT,
                installed_date TEXT,
                hauler_license TEXT,
                hauler_expiry TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_history (
                id TEXT PRIMARY KEY,
                tank_id TEXT NOT NULL,
                service_date TEXT NOT NULL,
                hauler_license TEXT,
                gallons_pumped INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (tank_id) REFERENCES tanks (id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tanks_state ON tanks(state)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_service_history_tank ON service_history(tank_id)
        """)
        conn.commit()


def clear_all_data() -> None:
    """Clear all data (for testing)."""
    with get_connection() as conn:
        # Check if tables exist before deleting
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in tables}
        if "service_history" in table_names:
            conn.execute("DELETE FROM service_history")
        if "tanks" in table_names:
            conn.execute("DELETE FROM tanks")
        conn.commit()


def create_tank(
    state: str,
    county: Optional[str] = None,
    municipality: Optional[str] = None,
    local_board: Optional[str] = None,
    tank_gallons: int = 1000,
    household_size: int = 4,
    tank_type: str = "conventional",
    last_pumped: Optional[str] = None,
    installed_date: Optional[str] = None,
    hauler_license: Optional[str] = None,
    hauler_expiry: Optional[str] = None,
) -> TankRecord:
    """Create a new tank record."""
    tank_id = str(uuid.uuid4())
    now = date.today().isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO tanks (id, state, county, municipality, local_board, tank_gallons,
                             household_size, tank_type, last_pumped, installed_date,
                             hauler_license, hauler_expiry, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tank_id, state, county, municipality, local_board, tank_gallons,
              household_size, tank_type, last_pumped, installed_date,
              hauler_license, hauler_expiry, now, now))
        conn.commit()

    return get_tank(tank_id)


def get_tank(tank_id: str) -> Optional[TankRecord]:
    """Get tank by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tanks WHERE id = ?", (tank_id,)).fetchone()
        return TankRecord(**dict(row)) if row else None


def list_tanks(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """List tanks with pagination."""
    offset = (page - 1) * page_size

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM tanks").fetchone()["count"]
        rows = conn.execute(
            "SELECT * FROM tanks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset)
        ).fetchall()

    tanks = [TankRecord(**dict(row)) for row in rows]
    return {
        "tanks": [t.__dict__ for t in tanks],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def update_tank(tank_id: str, **updates) -> Optional[TankRecord]:
    """Update tank fields."""
    if not updates:
        return get_tank(tank_id)

    allowed_fields = {
        "county", "municipality", "local_board", "tank_gallons",
        "household_size", "tank_type", "last_pumped", "installed_date",
        "hauler_license", "hauler_expiry"
    }
    updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not updates:
        return get_tank(tank_id)

    updates["updated_at"] = date.today().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [tank_id]

    with get_connection() as conn:
        conn.execute(f"UPDATE tanks SET {set_clause} WHERE id = ?", values)
        conn.commit()

    return get_tank(tank_id)


def delete_tank(tank_id: str) -> bool:
    """Delete a tank and its service history."""
    with get_connection() as conn:
        conn.execute("DELETE FROM service_history WHERE tank_id = ?", (tank_id,))
        result = conn.execute("DELETE FROM tanks WHERE id = ?", (tank_id,))
        conn.commit()
        return result.rowcount > 0


def add_service_record(
    tank_id: str,
    service_date: str,
    hauler_license: Optional[str] = None,
    gallons_pumped: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Add a service history record."""
    record_id = str(uuid.uuid4())
    now = date.today().isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO service_history (id, tank_id, service_date, hauler_license,
                                       gallons_pumped, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record_id, tank_id, service_date, hauler_license,
              gallons_pumped, notes, now))
        conn.commit()

    return {"id": record_id, "tank_id": tank_id, "service_date": service_date,
            "hauler_license": hauler_license, "gallons_pumped": gallons_pumped,
            "notes": notes, "created_at": now}


def get_service_history(tank_id: str) -> list[dict[str, Any]]:
    """Get service history for a tank."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM service_history WHERE tank_id = ? ORDER BY service_date DESC",
            (tank_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_dashboard_stats() -> dict[str, Any]:
    """Get dashboard statistics."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM tanks").fetchone()["count"]
        by_state = conn.execute(
            "SELECT state, COUNT(*) as count FROM tanks GROUP BY state"
        ).fetchall()

    # Compute due_soon and overdue using compliance engine for accuracy
    due_soon = 0
    overdue = 0
    if total > 0:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM tanks").fetchall()
            for row in rows:
                tank_record = TankRecord(**dict(row))
                engine_tank = tank_record_to_engine(tank_record)
                schedule = engine.calculate_schedule(engine_tank)
                if schedule.status == ComplianceStatus.DUE_SOON:
                    due_soon += 1
                elif schedule.status == ComplianceStatus.OVERDUE:
                    overdue += 1

    return {
        "total_tanks": total,
        "by_state": {row["state"]: row["count"] for row in by_state},
        "due_soon": due_soon,
        "overdue": overdue,
        "compliant": total - due_soon - overdue,
    }


if __name__ == "__main__":
    init_db()
    print("Database initialized at", get_db_path())