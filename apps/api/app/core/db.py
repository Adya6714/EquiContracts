"""Database sessions with transaction-local organisation scoping."""

import contextlib
from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()

app_engine = create_engine(settings.database_url, pool_pre_ping=True)
admin_engine = create_engine(settings.admin_database_url, pool_pre_ping=True)
system_engine = create_engine(settings.system_database_url, pool_pre_ping=True)
agent_engine = create_engine(settings.agent_database_url, pool_pre_ping=True)

AppSessionFactory = sessionmaker(bind=app_engine, expire_on_commit=False)
AdminSessionFactory = sessionmaker(bind=admin_engine, expire_on_commit=False)
SystemSessionFactory = sessionmaker(bind=system_engine, expire_on_commit=False)
AgentSessionFactory = sessionmaker(bind=agent_engine, expire_on_commit=False)


@contextlib.contextmanager
def org_scoped_session(org_id: UUID) -> Iterator[Session]:
    """Yield an app-role session scoped to one org for this transaction."""

    session = AppSessionFactory()
    try:
        session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextlib.contextmanager
def agent_org_scoped_session(org_id: UUID) -> Iterator[Session]:
    """Yield an agent-role session scoped to one org for a worker run."""

    session = AgentSessionFactory()
    try:
        session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextlib.contextmanager
def provisioning_session() -> Iterator[Session]:
    """Yield the narrow admin session used for pre-tenant provisioning."""

    session = AdminSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextlib.contextmanager
def privileged_session() -> Iterator[Session]:
    """Yield the limited system session for entry points without an org principal."""

    session = SystemSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
