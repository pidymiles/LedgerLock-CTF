#!/usr/bin/env python3
"""Organizer-only utility for inspecting the generated challenge flag."""

import os
import sqlite3
from pathlib import Path


db_path = Path(os.environ.get("DATABASE_PATH", "/data/ledgerlock.db"))
if not db_path.exists():
    raise SystemExit("Database not found. Start the challenge first.")

with sqlite3.connect(db_path) as db:
    row = db.execute(
        "SELECT internal_notes FROM cases WHERE internal_notes LIKE 'flag{%}' LIMIT 1"
    ).fetchone()

if not row:
    raise SystemExit("Flag record not found.")

print(row[0])
