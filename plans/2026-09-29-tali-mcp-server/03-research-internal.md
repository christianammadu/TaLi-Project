# 03 — Internal Research: TaLi Model Context Protocol (MCP) Server

## Codebase Readiness & Integration Seams

- **Database Layer**: SQLAlchemy ORM models in `app/data/models.py`, session management via `app/data/db.py` session_scope.
- **Authentication**: Passwordless OTP in `app/portal/auth.py`, admin bcrypt auth in `app/admin/auth.py`.
- **API & Channels**: Modular Flask blueprints in `app/web/`, `app/portal/`, and `app/admin/`.
- **Test Infrastructure**: Pytest fixtures with session mocking in `tests/conftest.py`.
