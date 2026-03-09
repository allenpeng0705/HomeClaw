"""
Companion auth: login (username/password) and token-based "me" / "my friends" API.
Step 12: Companion never gets the full user list; only login → user_id + token + friends, and GET /api/me/friends with token.
Never crash Core; 401 on invalid credentials or missing/expired token.
Tokens are persisted to disk so sessions survive Core restarts.
"""
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from base.base import User
from base.util import Util

# Token store: token_str -> {"user_id": str, "expires_at": float}. Loaded from disk; saved on each login.
_COMPANION_TOKENS: Dict[str, Dict[str, Any]] = {}
_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_TOKENS_LOADED = False
_TOKENS_FILENAME = "companion_tokens.json"


def _tokens_path() -> Path:
    """Path to persisted companion tokens file. Under data_path (e.g. database/). Never raises."""
    try:
        root = (Util().data_path() or "").strip() or "database"
        return Path(root) / _TOKENS_FILENAME
    except Exception:
        return Path("database") / _TOKENS_FILENAME


def _load_tokens_from_disk() -> None:
    """Load tokens from disk once. Merge into _COMPANION_TOKENS. Never raises."""
    global _TOKENS_LOADED
    if _TOKENS_LOADED:
        return
    _TOKENS_LOADED = True
    try:
        path = _tokens_path()
        if not path.is_file():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            return
        now = time.time()
        for t, v in tokens.items():
            if not isinstance(v, dict) or not t or not isinstance(t, str):
                continue
            try:
                exp = v.get("expires_at")
                exp = float(exp) if exp is not None else 0.0
            except (TypeError, ValueError):
                exp = 0.0
            if exp > now:
                uid = str(v.get("user_id") or "").strip()
                _COMPANION_TOKENS[t] = {"user_id": uid, "expires_at": exp}
    except Exception as e:
        logger.debug("companion_auth: load tokens failed: {}", e)


def _save_tokens_to_disk() -> None:
    """Write current _COMPANION_TOKENS to disk. Only serializes valid entries. Never raises."""
    try:
        path = _tokens_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        safe = {}
        for t, v in list(_COMPANION_TOKENS.items()):
            if not isinstance(t, str) or not t or not isinstance(v, dict):
                continue
            try:
                uid = str(v.get("user_id") or "").strip()
                exp = v.get("expires_at")
                exp = float(exp) if exp is not None else 0.0
                safe[t] = {"user_id": uid, "expires_at": exp}
            except (TypeError, ValueError):
                continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"tokens": safe}, f, indent=0)
    except Exception as e:
        logger.debug("companion_auth: save tokens failed: {}", e)


def _clean_expired_tokens() -> None:
    """Remove expired entries from _COMPANION_TOKENS. Never raises."""
    try:
        now = time.time()
        try:
            items = list(_COMPANION_TOKENS.items())
        except Exception:
            items = []
        expired = [t for t, v in items if isinstance(v, dict) and (v.get("expires_at") or 0) < now]
        for t in expired:
            try:
                _COMPANION_TOKENS.pop(t, None)
            except Exception:
                pass
    except Exception as e:
        logger.debug("companion_auth: clean_expired failed: {}", e)


def _name_to_preset_key(name: str) -> Optional[str]:
    """Map known preset friend names to preset key so API always returns preset for Reminder/Note/Finder. Never raises."""
    n = (name or "").strip().lower()
    if not n:
        return None
    if n in ("reminder",):
        return "reminder"
    if n in ("finder", "files"):
        return "finder"
    if n in ("note", "notes") or "note" in n:
        return "note"
    if "reminder" in n:
        return "reminder"
    if "finder" in n or "file" in n:
        return "finder"
    return None


def _user_to_friends_list(user: User) -> List[Dict[str, Any]]:
    """Return list of { name, relation?, who?, identity?, preset?, type?, user_id? } for user.friends. Never raises.
    When type=='user' and user_id is set, this friend is a real person (user-to-user); otherwise AI friend (user→Core).
    Ensures preset is set for known names (Reminder, Note, Finder) so Companion can show preset thumbnails."""
    try:
        friends = getattr(user, "friends", None)
        if not isinstance(friends, list) or not friends:
            return [{"name": "HomeClaw", "relation": None, "who": None, "identity": None, "type": "ai"}]
        out = []
        for f in friends:
            if not hasattr(f, "name"):
                continue
            try:
                fname = (getattr(f, "name", "") or "").strip() or "HomeClaw"
                item = {
                    "name": fname,
                    "relation": getattr(f, "relation", None),
                    "who": getattr(f, "who", None),
                    "identity": getattr(f, "identity", None),
                }
                preset = getattr(f, "preset", None)
                if preset is not None and str(preset).strip():
                    item["preset"] = str(preset).strip()
                else:
                    derived = _name_to_preset_key(fname)
                    if derived:
                        item["preset"] = derived
                ftype = (getattr(f, "type", None) or "").strip().lower() or "ai"
                if ftype not in ("user", "ai", "remote_ai", "remote_user"):
                    ftype = "ai"
                item["type"] = ftype
                if ftype == "user":
                    uid = (getattr(f, "user_id", None) or "").strip()
                    if uid:
                        item["user_id"] = uid
                out.append(item)
            except Exception:
                continue
        return out if out else [{"name": "HomeClaw", "relation": None, "who": None, "identity": None, "type": "ai"}]
    except Exception as e:
        logger.debug("companion_auth: _user_to_friends_list failed: {}", e)
        return [{"name": "HomeClaw", "relation": None, "who": None, "identity": None, "type": "ai"}]


def get_companion_token_user(request: Request) -> Tuple[str, User]:
    """Dependency: require Authorization: Bearer <session_token>. Resolve to (user_id, user). Raises HTTPException(401) if missing or invalid. Never crashes Core."""
    _load_tokens_from_disk()
    _clean_expired_tokens()
    try:
        auth = (request.headers.get("Authorization") or "").strip()
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization (expected Bearer <token>)")
        token = auth[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Missing token")
        entry = _COMPANION_TOKENS.get(token)
        if not isinstance(entry, dict):
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        expires = entry.get("expires_at") or 0
        if expires < time.time():
            _COMPANION_TOKENS.pop(token, None)
            raise HTTPException(status_code=401, detail="Token expired")
        try:
            user_id = (str(entry.get("user_id") or "").strip())
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid token")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        try:
            users = Util().get_users() or []
        except Exception:
            users = []
        if not isinstance(users, list):
            users = []
        user = None
        for u in users:
            try:
                uid = getattr(u, "id", None) or getattr(u, "name", "") or ""
                if (uid or "") == user_id:
                    user = u
                    break
            except Exception:
                continue
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user_id, user
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("companion_auth: token lookup failed: {}", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_api_auth_login_handler(core):  # noqa: ARG001
    """POST /api/auth/login. Body: { username, password }. Returns { user_id, token, name, friends }. 401 on invalid. Never crashes."""
    async def api_auth_login(request: Request):
        _load_tokens_from_disk()
        try:
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})
            if not isinstance(body, dict):
                return JSONResponse(status_code=400, content={"detail": "JSON object required"})
            try:
                username = (str(body.get("username") or "").strip())
            except (TypeError, ValueError):
                username = ""
            try:
                raw = body.get("password")
                password = (str(raw) if raw is not None else "").strip()
            except (TypeError, ValueError):
                password = ""
            if not username:
                return JSONResponse(status_code=401, content={"detail": "username required"})
            try:
                users = Util().get_users() or []
            except Exception:
                users = []
            if not isinstance(users, list):
                users = []
            user = None
            for u in users:
                try:
                    un = getattr(u, "username", None) or ""
                    if (str(un).strip() if un is not None else "") == username:
                        user = u
                        break
                except Exception:
                    continue
            if not user:
                return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})
            try:
                stored = getattr(user, "password", None) or ""
                if not isinstance(stored, str):
                    stored = str(stored) if stored else ""
                stored = (stored or "").strip()
            except Exception:
                stored = ""
            if stored != password:
                return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})
            try:
                user_id = (str(getattr(user, "id", None) or getattr(user, "name", "") or "").strip()) or username
            except (TypeError, ValueError):
                user_id = username
            try:
                name = (str(getattr(user, "name", "") or "").strip()) or user_id
            except (TypeError, ValueError):
                name = user_id
            token = uuid.uuid4().hex
            expires_at = time.time() + _TOKEN_TTL_SECONDS
            _COMPANION_TOKENS[token] = {"user_id": user_id, "expires_at": expires_at}
            _clean_expired_tokens()
            _save_tokens_to_disk()
            friends = _user_to_friends_list(user)
            return JSONResponse(content={
                "user_id": user_id,
                "token": token,
                "name": name,
                "friends": friends,
            })
        except Exception as e:
            logger.exception("companion_auth: login failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Login failed"})
    return api_auth_login


def get_api_me_handler(core):  # noqa: ARG001
    """GET /api/me. Requires Bearer token. Returns { user_id, name, friends }. 401 if invalid. Never crashes."""
    async def api_me(
        request: Request,
        token_user: Tuple[str, User] = Depends(get_companion_token_user),
    ):
        try:
            user_id, user = token_user
            try:
                name = (str(getattr(user, "name", "") or "").strip()) or user_id
            except (TypeError, ValueError):
                name = user_id
            friends = _user_to_friends_list(user)
            return JSONResponse(content={"user_id": user_id, "name": name, "friends": friends})
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("companion_auth: /api/me failed: {}", e)
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    return api_me


def get_api_me_friends_handler(core):  # noqa: ARG001
    """GET /api/me/friends. Requires Bearer token. Returns { friends: [...] }. 401 if invalid. Never crashes."""
    async def api_me_friends(
        request: Request,
        token_user: Tuple[str, User] = Depends(get_companion_token_user),
    ):
        try:
            _user_id, user = token_user
            friends = _user_to_friends_list(user)
            return JSONResponse(content={"friends": friends})
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("companion_auth: /api/me/friends failed: {}", e)
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    return api_me_friends
