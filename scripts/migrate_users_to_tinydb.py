"""
One-time migration: copy users from config/user.yml into TinyDB (database/users.json).

Run from project root with the same Python environment you use for Core (e.g. venv with
dependencies installed):

  python scripts/migrate_users_to_tinydb.py

This overwrites any existing user documents in TinyDB with the users from user.yml.
Use this when you have existing user.yml and want Core to use TinyDB without re-creating users.
"""
import os
import sys
from pathlib import Path

# Project root = parent of scripts/
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

os.chdir(str(_project_root))


def main():
    config_dir = _project_root / "config"
    user_yml = config_dir / "user.yml"
    database_dir = _project_root / "database"

    if not user_yml.is_file():
        print(f"Not found: {user_yml}")
        print("Nothing to migrate. Create config/user.yml first.")
        return 1

    try:
        from base.base import User
        from base import user_store
    except ImportError as e:
        print("Migration needs project dependencies (e.g. run with the same env as Core).")
        print(f"Import error: {e}")
        return 1

    users = User.from_yaml(str(user_yml))
    if not users:
        print("No users in user.yml (or parse failed). Nothing to migrate.")
        return 0

    # Callables that return config dir and database dir (same as Util)
    config_path_fn = lambda: str(config_dir)
    data_path_fn = lambda: str(database_dir)

    user_store.save_all(users, config_path_fn, data_path_fn)
    db_path = Path(data_path_fn()) / "users.json"
    print(f"Migrated {len(users)} user(s) from {user_yml} to TinyDB at {db_path}")
    for u in users:
        name = getattr(u, "name", None) or getattr(u, "id", "?")
        print(f"  - {name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
