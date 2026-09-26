"""
License Server — Email Finder Agent
Deploy on any free-tier host (Render, PythonAnywhere, Fly.io, etc.)
FastAPI + SQLite, zero external dependencies.
"""
import sqlite3
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Email Finder License Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = Path(__file__).parent / "licenses.db"

class ActivateRequest(BaseModel):
    key: str
    machine_id: str  # optional fingerprint

class KillRequest(BaseModel):
    key: str
    admin_key: str

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                key TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                last_seen TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT NOT NULL,
                machine_id TEXT,
                activated_at TEXT NOT NULL
            )
        """)
        conn.commit()

@app.on_event("startup")
def startup():
    init_db()

def _row_to_dict(row):
    return dict(row) if row else None

@app.get("/api/license/health")
def health():
    return {"status": "ok"}

@app.post("/api/license/validate")
def validate_license(key: str):
    """Check if license is active. Returns {active, expires, company}."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM licenses WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "License not found")
        license = _row_to_dict(row)
        
        # Update last seen
        conn.execute(
            "UPDATE licenses SET last_seen = ? WHERE key = ?",
            (datetime.utcnow().isoformat(), key)
        )
        conn.commit()
        
        if not license["active"]:
            return {"active": False, "reason": "License deactivated"}
        
        if license["expires_at"]:
            expires = datetime.fromisoformat(license["expires_at"])
            if expires < datetime.utcnow():
                return {"active": False, "reason": "License expired"}
        
        return {
            "active": True,
            "company": license["company"],
            "expires_at": license["expires_at"],
            "version": "1.0.0"
        }

@app.post("/api/license/activate")
def activate_license(req: ActivateRequest):
    """Record activation (optional)."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO activations (license_key, machine_id, activated_at)
               VALUES (?, ?, ?)""",
            (req.key, req.machine_id, datetime.utcnow().isoformat())
        )
        conn.execute(
            "UPDATE licenses SET last_seen = ? WHERE key = ?",
            (datetime.utcnow().isoformat(), req.key)
        )
        conn.commit()
    return {"status": "activated"}

@app.post("/api/license/deactivate")
def deactivate_license(req: KillRequest):
    """Admin endpoint to deactivate a license."""
    ADMIN_KEY = secrets.token_hex(32)  # Set this in production
    if req.admin_key != ADMIN_KEY:
        raise HTTPException(403, "Unauthorized")
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT key FROM licenses WHERE key = ?", (req.key,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "License not found")
        conn.execute(
            "UPDATE licenses SET active = 0 WHERE key = ?", (req.key,)
        )
        conn.commit()
    return {"status": "deactivated"}

@app.post("/api/license/delete")
def delete_license(req: KillRequest):
    """Admin endpoint to delete a license."""
    ADMIN_KEY = secrets.token_hex(32)
    if req.admin_key != ADMIN_KEY:
        raise HTTPException(403, "Unauthorized")
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT key FROM licenses WHERE key = ?", (req.key,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "License not found")
        conn.execute("DELETE FROM licenses WHERE key = ?", (req.key,))
        conn.commit()
    return {"status": "deleted"}

@app.get("/api/license/list")
def list_licenses(admin_key: str):
    """List all licenses (admin only)."""
    ADMIN_KEY = secrets.token_hex(32)
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "Unauthorized")
    
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM licenses ORDER BY created_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows]

@app.post("/api/license/add")
def add_license(company: str, days: int = 365, admin_key: str = ""):
    """Create a new license (admin only)."""
    ADMIN_KEY = secrets.token_hex(32)
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "Unauthorized")
    
    key = f"EF-{secrets.token_hex(8).upper()}"
    expires = datetime.utcnow() + timedelta(days=days) if days > 0 else None
    
    with get_db() as conn:
        conn.execute(
            """INSERT INTO licenses (key, company, active, expires_at, created_at)
               VALUES (?, ?, 1, ?, ?)""",
            (key, company, expires.isoformat() if expires else None, datetime.utcnow().isoformat())
        )
        conn.commit()
    
    return {"key": key, "company": company, "expires_at": expires.isoformat() if expires else None}
