import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadscout.api.main import app
from leadscout.db import get_session, make_engine
from leadscout.models import Base


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    return f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Schema is built by running the real Alembic migrations, not create_all."""
    eng = make_engine(database_url)
    with eng.begin() as conn:
        Base.metadata.drop_all(conn)
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    cfg = Config("alembic.ini")
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    with engine.connect() as conn:
        trans = conn.begin()
        sess = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")()
        try:
            yield sess
        finally:
            sess.close()
            trans.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
