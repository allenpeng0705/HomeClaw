"""
User store: TinyDB-backed persistence for users and friends.
Replaces user.yml as the source of truth. See docs_design/UserDataTinyDB.md.
"""
import os
from pathlib import Path
from typing import List, Optional

from loguru import logger

from base.base import User


_TABLE_NAME = "users"
_DB_FILENAME = "users.json"


def _get_db_path(config_path_fn, data_path_fn) -> Path:
    """Path to TinyDB file under data_path (e.g. database/users.json). Never raises."""
    try:
        root = ""
        try:
            r = data_path_fn()
            root = (r if r is not None else "").strip()
        except Exception:
            pass
        if not root and config_path_fn:
            try:
                cfg = config_path_fn()
                if cfg:
                    root = os.path.join(str(cfg), "..", "database")
            except Exception:
                pass
        if root:
            return Path(root).resolve() / _DB_FILENAME
    except Exception:
        pass
    return Path("database") / _DB_FILENAME


def _get_user_yml_path(config_path_fn) -> Path:
    """Path to config/user.yml for migration. Never raises."""
    try:
        if config_path_fn:
            cfg = config_path_fn()
            if cfg is not None and str(cfg).strip():
                return Path(str(cfg).strip()).resolve() / "user.yml"
    except Exception:
        pass
    return Path("config") / "user.yml"


def get_all(config_path_fn, data_path_fn) -> List[User]:
    """
    Load all users from TinyDB. If DB is empty and config/user.yml exists, migrate from YAML then return.
    Never raises; returns [] on error.
    """
    try:
        db_path = _get_db_path(config_path_fn, data_path_fn)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        from tinydb import TinyDB

        db = TinyDB(str(db_path))
        try:
            table = db.table(_TABLE_NAME)
            docs = table.all()
        finally:
            try:
                db.close()
            except Exception:
                pass

        if not docs:
            # Lazy migration: if user.yml exists, load from it and fill TinyDB
            yml_path = _get_user_yml_path(config_path_fn)
            if yml_path.is_file():
                try:
                    users = User.from_yaml(str(yml_path))
                    if users:
                        save_all(users, config_path_fn, data_path_fn)
                        return users
                except Exception as e:
                    logger.debug("user_store: migration from user.yml failed: {}", e)

            return []

        users = []
        for doc in docs:
            try:
                if not isinstance(doc, dict):
                    continue
                user = User.from_doc(doc)
                if user:
                    users.append(user)
            except Exception:
                continue
        return users
    except Exception as e:
        logger.debug("user_store get_all failed: {}", e)
        return []


def save_all(users: List[User], config_path_fn, data_path_fn) -> None:
    """
    Persist all users to TinyDB. Never raises; logs on failure.
    """
    db = None
    try:
        db_path = _get_db_path(config_path_fn, data_path_fn)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        from tinydb import TinyDB

        db = TinyDB(str(db_path))
        table = db.table(_TABLE_NAME)
        docs = []
        for u in users or []:
            if not isinstance(u, User):
                continue
            try:
                docs.append(u.to_doc())
            except Exception:
                continue
        table.truncate()
        if docs:
            table.insert_multiple(docs)
    except Exception as e:
        logger.warning("user_store save_all failed: {}", e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
