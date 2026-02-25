import os
import threading

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.orm import scoped_session, sessionmaker

from .models import Base
from loguru import logger


def _default_sqlite_uri() -> str:
    """Lazy import Util to avoid circular import: base.util -> memory.chat -> memory.database -> base.util."""
    from base.util import Util
    return f'sqlite:///{os.path.join(Util().data_path(), "chats.db")}'


def _resolve_database_uri() -> str:
    """Resolve relational DB URI from core.yml (database.backend + database.url) or env MEMORY_DB_URI."""
    import os as _os
    env_uri = _os.environ.get("MEMORY_DB_URI", "").strip()
    if env_uri:
        return env_uri
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        db = getattr(meta, "database", None)
        if db is None:
            return _default_sqlite_uri()
        url = (getattr(db, "url", None) or "").strip()
        backend = (getattr(db, "backend", None) or "sqlite").lower()
        if backend in ("mysql", "postgresql") and url:
            return url
        if backend == "sqlite":
            return url if url else _default_sqlite_uri()
        return _default_sqlite_uri()
    except Exception:
        return _default_sqlite_uri()


class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(DatabaseManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, echo: bool = False):
        self.database_uri = _resolve_database_uri()
        self.echo = echo
        self.engine: Engine = None
        self._session_factory = None
        self.setup_engine()
        self.init_db()

    def create_tables(self):
        Base.metadata.create_all(self.engine)
        # Migration: add user_id and channel_key to one-shot reminders (for deliver_to_user)
        try:
            if self.engine and "sqlite" in (self.engine.url.drivername or ""):
                from sqlalchemy import text
                for col in ("user_id", "channel_key"):
                    try:
                        with self.engine.begin() as conn:
                            conn.execute(text(
                                f"ALTER TABLE homeclaw_tam_one_shot_reminders ADD COLUMN {col} VARCHAR"
                            ))
                    except Exception:
                        pass  # column may already exist
        except Exception as e:
            logger.debug("TAM one_shot migration (user_id/channel_key): {}", e)
        logger.debug("All the tables created successfully.")


    def setup_engine(self) -> None:
        """Initializes the database engine and session factory."""
        if not self.database_uri:
            raise RuntimeError("Database URI is not set. Set the MEMORY_DB_URI environment variable.")
        connect_args = {}
        if self.database_uri.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(self.database_uri, echo=self.echo, connect_args=connect_args)
        logger.debug("create session factory")
        self._session_factory = scoped_session(sessionmaker(bind=self.engine))
        if not self._session_factory:
            logger.debug("session factory created failed")
        logger.debug("session factory created")
        Base.metadata.bind = self.engine
        self.create_tables()

    def init_db(self) -> None:
        """Creates all tables defined in the Base metadata."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized. Call setup_engine() first.")
        Base.metadata.create_all(self.engine)

    def get_session(self) -> SQLAlchemySession:
        """Provides a session for database operations."""
        logger.debug("Database Manager get session")
        if not self._session_factory:
            raise RuntimeError("Session factory is not initialized. Call setup_engine() first.")
        return self._session_factory()

    def close_session(self) -> None:
        """Closes the current session."""
        if self._session_factory:
            self._session_factory.remove()

    def execute_transaction(self, transaction_block):
        """Executes a block of code within a database transaction."""
        session = self.get_session()
        try:
            transaction_block(session)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            self.close_session()

# Convenience functions for backward compatibility and ease of use
def setup_engine(database_uri: str = None, echo: bool = False) -> None:
    database_manager = DatabaseManager()
    if database_uri is not None:
        database_manager.database_uri = database_uri
    database_manager.echo = echo
    database_manager.setup_engine()


'''
def alembic_upgrade() -> None:
    """Upgrades the database to the latest version."""
    alembic_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    alembic_cfg = Config(alembic_config_path)
    command.upgrade(alembic_cfg, "head")

'''
