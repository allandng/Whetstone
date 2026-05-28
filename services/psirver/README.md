# Psirver

Placeholder for **Psirver**, the C++ code-execution backend.

Psirver is a standalone HTTP server (originally written for an Operating
Systems course) that runs submitted scripts as isolated jobs using
`fork`/`execvp`, capturing stdout/stderr, status, and supporting
termination. The Whetstone backend talks to it over loopback
(`127.0.0.1`) via `apps/backend/services/psirver_client.py`.

The actual C++ source will live here. Nothing is built yet.
