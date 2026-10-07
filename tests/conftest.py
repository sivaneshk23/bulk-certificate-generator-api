import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.sqlite3"
os.environ["PROCESSING_MODE"] = "sync"
os.environ["STORAGE_DIR"] = "tests/test_storage"
os.environ["MAX_RECIPIENTS_PER_JOB"] = "100"

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import job_service


@pytest.fixture(autouse=True)
def reset_database(tmp_path, monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    storage = tmp_path / "certificates"
    monkeypatch.setattr(job_service.settings, "storage_dir", str(storage))
    storage.mkdir(parents=True, exist_ok=True)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
