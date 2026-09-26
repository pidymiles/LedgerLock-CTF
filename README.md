# LedgerLock: An IDOR CTF Challenge

LedgerLock is an intermediate web security challenge built around a realistic broken object-level authorization flaw. It runs as a single, dependency-free Python container and stores its records in SQLite.

## Scenario

You have been given employee access to LedgerLock, an internal incident-records portal. The dashboard claims your account can see only assigned cases. A sealed recovery record exists somewhere in the system, and its internal notes contain the flag.

Your objective is to retrieve the flag. Do not attack the login, modify the database, or inspect the container filesystem—the intended solution is entirely available over HTTP after signing in.

## Run locally

Requirements: Docker with the Compose plugin.

```bash
docker compose up --build -d
```

Open <http://127.0.0.1:5000> and sign in with:

```text
Username: analyst
Password: Analyst!2026
```

The application creates a unique flag during the first startup and keeps the SQLite database in a named Docker volume.

## Stop or reset

Stop the application while preserving its data:

```bash
docker compose down
```

Reset the database and generate a new flag:

```bash
docker compose down -v
docker compose up --build -d
```

## Customize the flag

Set `FLAG` before the first startup. The value must match `flag{...}` and may contain letters, numbers, underscores, colons, or hyphens.

```bash
FLAG='flag{your_event_flag_here}' docker compose up --build -d
```

If the volume already exists, reset it first or the existing flag will be retained.

## Organizer utility

After startup, the organizer can verify the active flag without resetting the database:

```bash
docker compose exec ledgerlock python manage.py
```

Do not give participants shell access to the host or container. The challenge is intentionally vulnerable and is bound to `127.0.0.1` by default. If remote players need access, place it behind an isolated lab proxy or VPN and apply normal CTF network controls.

## Spoiler-free hints

1. Use the browser's developer tools and watch what happens when you open one of your assigned records.
2. Authentication answers “who are you?” Authorization answers “may you access this specific object?”
3. Numeric identifiers often reveal more than an interface intends to show.

The solution writeup is intentionally distributed separately from this player package.
