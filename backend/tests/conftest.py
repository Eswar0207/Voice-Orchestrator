"""
Shared pytest fixtures.

NOTE: tests use a throwaway local SQLite file for speed/isolation in CI
(no Docker dependency needed to run `pytest`). Production and local dev
always use PostgreSQL as configured in DATABASE_URL — this test DB is a
testing convenience only, not a deployment target, and the ORM models
contain no SQLite-specific or Postgres-only types that would silently break
when pointed at real Postgres (JSONB has a portable fallback in the test
engine via SQLAlchemy's generic JSON variant during tests).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("VAPI_WEBHOOK_SECRET", "test-secret")
os.environ["SIMULATION_MODE"] = "false"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as db_module
from app.database import Base


@pytest.fixture(autouse=True)
def _isolated_test_db(monkeypatch, tmp_path):
    """Point the app's engine/session at a fresh SQLite file per test."""
    db_path = tmp_path / "test.db"
    test_engine = create_engine(f"sqlite:///{db_path}")
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.create_all(bind=test_engine)

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)

    # Also patch the orchestrator module's imported reference
    import app.orchestrator as orch_module
    monkeypatch.setattr(orch_module, "SessionLocal", TestSessionLocal)

    yield TestSessionLocal

    Base.metadata.drop_all(bind=test_engine)
