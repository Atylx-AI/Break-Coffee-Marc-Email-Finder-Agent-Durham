"""License Server — Email Finder Agent
Pure Python stdlib HTTP server. No external dependencies.
Runs on any Python 3.8+. Zero install issues on Render free tier.
"""
import sqlite3
import secrets
import json
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB = Path(__file__).parent / "licenses.db"

# Admin key (set this to a strong random string before deploying)
ADMIN_KEY = os.environ.get("ADMIN_LICENSE_KEY", "changeme-admin-key")

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

def _row_to_dict(row):
    return dict(row) if row else None

def _json_response(handler, data, status=200):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)

def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length > 0:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    return {}

class LicenseHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/api/license/health":
            _json_response(self, {"status": "ok"})

        elif path == "/api/license/list":
            ak = params.get("admin_key", [""])[0]
            if ak != ADMIN_KEY:
                _json_response(self, {"detail": "Unauthorized"}, 403)
                return
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM licenses ORDER BY created_at DESC"
                ).fetchall()
            _json_response(self, [_row_to_dict(r) for r in rows])

        elif path == "/api/license/validate":
            key = params.get("key", [""])[0]
            if not key:
                _json_response(self, {"detail": "key required"}, 400)
                return
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM licenses WHERE key = ?", (key,)
                ).fetchone()
                if not row:
                    _json_response(self, {"active": False, "reason": "License not found"}, 404)
                    return
                lic = _row_to_dict(row)
                conn.execute(
                    "UPDATE licenses SET last_seen = ? WHERE key = ?",
                    (datetime.utcnow().isoformat(), key)
                )
                conn.commit()
                if not lic["active"]:
                    _json_response(self, {"active": False, "reason": "License deactivated"})
                    return
                if lic["expires_at"]:
                    expires = datetime.fromisoformat(lic["expires_at"])
                    if expires < datetime.utcnow():
                        _json_response(self, {"active": False, "reason": "License expired"})
                        return
                _json_response(self, {
                    "active": True,
                    "company": lic["company"],
                    "expires_at": lic["expires_at"],
                    "version": "1.0.0"
                })
        else:
            _json_response(self, {"detail": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = _read_body(self)

        if path == "/api/license/activate":
            key = body.get("key", "")
            machine_id = body.get("machine_id", "")
            if not key:
                _json_response(self, {"detail": "key required"}, 400)
                return
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO activations (license_key, machine_id, activated_at)
                       VALUES (?, ?, ?)""",
                    (key, machine_id, datetime.utcnow().isoformat())
                )
                conn.execute(
                    "UPDATE licenses SET last_seen = ? WHERE key = ?",
                    (datetime.utcnow().isoformat(), key)
                )
                conn.commit()
            _json_response(self, {"status": "activated"})

        elif path == "/api/license/deactivate":
            if body.get("admin_key") != ADMIN_KEY:
                _json_response(self, {"detail": "Unauthorized"}, 403)
                return
            key = body.get("key", "")
            with get_db() as conn:
                row = conn.execute(
                    "SELECT key FROM licenses WHERE key = ?", (key,)
                ).fetchone()
                if not row:
                    _json_response(self, {"detail": "License not found"}, 404)
                    return
                conn.execute(
                    "UPDATE licenses SET active = 0 WHERE key = ?", (key,)
                )
                conn.commit()
            _json_response(self, {"status": "deactivated"})

        elif path == "/api/license/delete":
            if body.get("admin_key") != ADMIN_KEY:
                _json_response(self, {"detail": "Unauthorized"}, 403)
                return
            key = body.get("key", "")
            with get_db() as conn:
                row = conn.execute(
                    "SELECT key FROM licenses WHERE key = ?", (key,)
                ).fetchone()
                if not row:
                    _json_response(self, {"detail": "License not found"}, 404)
                    return
                conn.execute("DELETE FROM licenses WHERE key = ?", (key,))
                conn.commit()
            _json_response(self, {"status": "deleted"})

        elif path == "/api/license/add":
            company = body.get("company", "")
            days = int(body.get("days", 365))
            if body.get("admin_key") != ADMIN_KEY:
                _json_response(self, {"detail": "Unauthorized"}, 403)
                return
            key = f"EF-{secrets.token_hex(8).upper()}"
            expires = datetime.utcnow() + timedelta(days=days) if days > 0 else None
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO licenses (key, company, active, expires_at, created_at)
                       VALUES (?, ?, 1, ?, ?)""",
                    (key, company, expires.isoformat() if expires else None,
                     datetime.utcnow().isoformat())
                )
                conn.commit()
            _json_response(self, {
                "key": key, "company": company,
                "expires_at": expires.isoformat() if expires else None
            })
        else:
            _json_response(self, {"detail": "Not found"}, 404)

    def log_message(self, format, *args):
        pass

def run_server():
    init_db()
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), LicenseHandler)
    print(f"License server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
