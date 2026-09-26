#!/usr/bin/env python3
"""LedgerLock CTF — intentionally vulnerable training application.

This application contains a deliberate broken object-level authorization flaw.
Run it only in an isolated lab environment.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/ledgerlock.db"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
SESSION_LIFETIME = 8 * 60 * 60
MAX_BODY_BYTES = 64 * 1024


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 220_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_value: str) -> bool:
    try:
        salt_hex, expected_hex = stored_value.split(":", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 220_000
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def make_flag() -> str:
    configured = os.environ.get("FLAG", "").strip()
    if configured:
        if not re.fullmatch(r"flag\{[A-Za-z0-9_:-]{6,100}\}", configured):
            raise ValueError("FLAG must use the format flag{letters_numbers_or_symbols}")
        return configured
    return f"flag{{idor_{secrets.token_hex(10)}}}"


def initialize_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                team TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                internal_notes TEXT NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_cases_owner ON cases(owner_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
            """
        )

        already_seeded = db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if already_seeded:
            return

        db.executemany(
            "INSERT INTO users (id, username, display_name, password_hash, team) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (1, "analyst", "Morgan Reed", hash_password("Analyst!2026"), "Operations"),
                (2, "rchen", "Riley Chen", hash_password(secrets.token_urlsafe(24)), "Finance"),
                (3, "jpatel", "Jordan Patel", hash_password(secrets.token_urlsafe(24)), "Security"),
            ],
        )

        flag = make_flag()
        db.executemany(
            """
            INSERT INTO cases
                (id, owner_id, title, category, status, priority, created_at, summary, internal_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (4101, 2, "Quarterly vendor reconciliation", "Finance", "Closed", "Low", "2026-08-30", "Reconcile vendor totals after the quarterly close.", "Difference accepted after controller review."),
                (4102, 1, "Scanner sync failures", "Operations", "Open", "Medium", "2026-09-02", "Three receiving scanners intermittently fail to sync completed jobs.", "Collect radio diagnostics during the next occurrence."),
                (4103, 3, "Archived account review", "Access", "Closed", "Low", "2026-09-04", "Confirm that archived contractors no longer retain portal access.", "Sampling completed; no active sessions remained."),
                (4104, 1, "Dispatch queue latency", "Operations", "Monitoring", "High", "2026-09-07", "Dispatch updates are taking more than two minutes during shift change.", "Metrics point to a burst of client refreshes at 18:00 UTC."),
                (4105, 2, "Expense batch mismatch", "Finance", "Investigating", "Medium", "2026-09-09", "One imported batch does not match its signed control total.", "Awaiting a clean export from the upstream system."),
                (4106, 3, "Legacy token inventory", "Access", "Open", "High", "2026-09-11", "Inventory long-lived integration tokens before the rotation window.", "Do not revoke production tokens until owners confirm the change."),
                (4107, 3, "Northstar recovery validation", "Restricted", "Sealed", "Critical", "2026-09-12", "Validate the sealed recovery record after the Northstar tabletop exercise.", flag),
                (4108, 2, "Travel policy exception", "Finance", "Pending", "Low", "2026-09-14", "Review a policy exception for delayed travel reimbursement.", "Manager approval attached in the finance system."),
            ],
        )


def page(title: str, body: str, username: str | None = None) -> bytes:
    account = ""
    if username:
        account = f"""
        <div class="account">
          <span class="account-dot"></span>
          <span>{html.escape(username)}</span>
          <form method="post" action="/logout"><button class="link-button" type="submit">Sign out</button></form>
        </div>"""
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · LedgerLock</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/dashboard" aria-label="LedgerLock home">
      <span class="brand-mark">LL</span>
      <span><strong>LedgerLock</strong><small>Incident Records</small></span>
    </a>
    {account}
  </header>
  <main>{body}</main>
  <footer>LedgerLock Records Platform · Training Environment</footer>
</body>
</html>"""
    return document.encode()


def login_page(error: str = "") -> bytes:
    error_html = f'<div class="alert" role="alert">{html.escape(error)}</div>' if error else ""
    body = f"""
    <section class="login-shell">
      <div class="login-copy">
        <span class="eyebrow">CONTROL WHAT MATTERS</span>
        <h1>Operational records,<br><em>without the noise.</em></h1>
        <p>Review assigned incidents, preserve case history, and keep internal teams moving.</p>
        <div class="status-line"><span></span> All systems operational</div>
      </div>
      <div class="login-card">
        <span class="eyebrow">EMPLOYEE ACCESS</span>
        <h2>Welcome back</h2>
        <p>Sign in with your assigned training account.</p>
        {error_html}
        <form method="post" action="/login" class="login-form">
          <label>Username<input name="username" autocomplete="username" required></label>
          <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
          <button class="primary" type="submit">Sign in</button>
        </form>
        <div class="training-credentials">
          <strong>Training credentials</strong>
          <code>analyst / Analyst!2026</code>
        </div>
      </div>
    </section>"""
    return page("Sign in", body)


def dashboard_page(user: sqlite3.Row) -> bytes:
    body = f"""
    <section class="dashboard">
      <div class="welcome">
        <div><span class="eyebrow">{html.escape(user['team']).upper()} WORKSPACE</span>
          <h1>Assigned records</h1>
          <p>Cases currently visible to your account.</p>
        </div>
        <div class="scope-card"><span>Access scope</span><strong>Assigned only</strong></div>
      </div>
      <div class="workspace-grid">
        <section class="panel records-panel">
          <div class="panel-heading"><div><h2>My cases</h2><p>Select a record to review details.</p></div><span id="case-count" class="count-pill">—</span></div>
          <div id="case-list" class="case-list"><div class="loading">Loading assigned records…</div></div>
        </section>
        <aside class="panel detail-panel" id="case-detail">
          <div class="empty-state"><span class="empty-icon">↗</span><h2>No record selected</h2><p>Choose a case from the queue to inspect its summary and notes.</p></div>
        </aside>
      </div>
    </section>
    <script src="/static/dashboard.js" defer></script>"""
    return page("Assigned records", body, user["display_name"])


class LedgerLockHandler(BaseHTTPRequestHandler):
    server_version = "LedgerLock/1.0"

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"{self.address_string()} - {format_string % args}")

    def send_bytes(
        self,
        content: bytes,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(
            json.dumps(payload, separators=(",", ":")).encode(),
            status,
            "application/json; charset=utf-8",
        )

    def redirect(self, location: str, cookie: str | None = None) -> None:
        headers = {"Location": location}
        if cookie:
            headers["Set-Cookie"] = cookie
        self.send_bytes(b"", HTTPStatus.SEE_OTHER, headers=headers)

    def request_user(self) -> sqlite3.Row | None:
        raw_cookie = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
            token = cookie.get("ledgerlock_session")
        except Exception:
            return None
        if token is None:
            return None
        now = int(time.time())
        with db_connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            return db.execute(
                """
                SELECT users.id, users.username, users.display_name, users.team
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at >= ?
                """,
                (token.value, now),
            ).fetchone()

    def require_user(self, api: bool = False) -> sqlite3.Row | None:
        user = self.request_user()
        if user is not None:
            return user
        if api:
            self.send_json({"error": "authentication_required"}, HTTPStatus.UNAUTHORIZED)
        else:
            self.redirect("/")
        return None

    def read_form(self) -> dict[str, str] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json({"error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            return None
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = parse_qs(body, keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/healthz":
            self.send_json({"status": "ok"})
            return

        if path == "/":
            if self.request_user():
                self.redirect("/dashboard")
            else:
                self.send_bytes(login_page())
            return

        if path == "/dashboard":
            user = self.require_user()
            if user:
                self.send_bytes(dashboard_page(user))
            return

        if path == "/static/style.css":
            self.send_bytes((STATIC_ROOT / "style.css").read_bytes(), content_type="text/css; charset=utf-8")
            return

        if path == "/static/dashboard.js":
            self.send_bytes((STATIC_ROOT / "dashboard.js").read_bytes(), content_type="application/javascript; charset=utf-8")
            return

        if path == "/api/cases":
            user = self.require_user(api=True)
            if not user:
                return
            with db_connect() as db:
                rows = db.execute(
                    """
                    SELECT id, title, category, status, priority, created_at
                    FROM cases WHERE owner_id = ? ORDER BY created_at DESC
                    """,
                    (user["id"],),
                ).fetchall()
            self.send_json({"cases": [dict(row) for row in rows], "count": len(rows)})
            return

        case_match = re.fullmatch(r"/api/cases/(\d+)", path)
        if case_match:
            user = self.require_user(api=True)
            if not user:
                return
            case_id = int(case_match.group(1))
            with db_connect() as db:
                # INTENTIONAL CTF VULNERABILITY:
                # This query verifies that the object exists, but never verifies
                # that owner_id matches the authenticated user.
                record = db.execute(
                    """
                    SELECT cases.id, cases.title, cases.category, cases.status,
                           cases.priority, cases.created_at, cases.summary,
                           cases.internal_notes, users.display_name AS owner
                    FROM cases JOIN users ON users.id = cases.owner_id
                    WHERE cases.id = ?
                    """,
                    (case_id,),
                ).fetchone()
            if not record:
                self.send_json({"error": "case_not_found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"case": dict(record)})
            return

        self.send_bytes(page("Not found", '<section class="not-found"><h1>404</h1><p>That page does not exist.</p><a href="/dashboard">Return to records</a></section>'), HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/login":
            form = self.read_form()
            if form is None:
                return
            username = form.get("username", "")[:100]
            password = form.get("password", "")[:200]
            with db_connect() as db:
                user = db.execute(
                    "SELECT id, password_hash FROM users WHERE username = ?", (username,)
                ).fetchone()
                if not user or not verify_password(password, user["password_hash"]):
                    self.send_bytes(login_page("The username or password is incorrect."), HTTPStatus.UNAUTHORIZED)
                    return
                token = secrets.token_urlsafe(32)
                expires = int(time.time()) + SESSION_LIFETIME
                db.execute(
                    "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                    (token, user["id"], expires),
                )
            cookie = f"ledgerlock_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_LIFETIME}"
            self.redirect("/dashboard", cookie)
            return

        if path == "/logout":
            raw_cookie = self.headers.get("Cookie", "")
            cookie = SimpleCookie()
            try:
                cookie.load(raw_cookie)
                token = cookie.get("ledgerlock_session")
                if token:
                    with db_connect() as db:
                        db.execute("DELETE FROM sessions WHERE token = ?", (token.value,))
            except Exception:
                pass
            self.redirect("/", "ledgerlock_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
            return

        self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), LedgerLockHandler)
    print(f"LedgerLock listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
