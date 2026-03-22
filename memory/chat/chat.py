import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc

from memory.database.database import DatabaseManager
from memory.database.models import (
    ChatHistoryByRoleModel,
    ChatHistoryModel,
    ChatSessionModel,
    MemoryRunModel,
)
from .message import ChatMessage


class ChatHistory:
    def __init__(self):
        self.db = DatabaseManager()

    def add(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        friend_id: str = "",
        chat_message: ChatMessage = None,
    ):
        if chat_message is None:
            return
        session = self.db.get_session()
        try:
            row = ChatHistoryModel(
                app_id=app_id or "",
                id=str(uuid.uuid4()),
                user_name=user_name or "",
                user_id=user_id or "",
                session_id=session_id or "",
                friend_id=friend_id or "",
                question=chat_message.human_message.content,
                answer=chat_message.ai_message.content,
                meta_data="{}",
            )
            session.add(row)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning("ChatHistory.add error: {}", e)
        finally:
            self.db.close_session()

    def get(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        friend_id: Optional[str] = None,
        num_rounds: int = 10,
        fetch_all: bool = False,
        display_format: bool = False,
    ) -> List[ChatMessage]:
        session = self.db.get_session()
        try:
            q = session.query(ChatHistoryModel)
            if app_id:
                q = q.filter(ChatHistoryModel.app_id == app_id)
            if user_name:
                q = q.filter(ChatHistoryModel.user_name == user_name)
            if user_id:
                q = q.filter(ChatHistoryModel.user_id == user_id)
            if session_id:
                q = q.filter(ChatHistoryModel.session_id == session_id)
            if friend_id is not None:
                q = q.filter(ChatHistoryModel.friend_id == (friend_id or ""))
            q = q.order_by(desc(ChatHistoryModel.created_at))
            if not fetch_all:
                q = q.limit(num_rounds)
            rows = q.all()
            rows.reverse()
            result = []
            for row in rows:
                msg = ChatMessage()
                msg.add_user_message(row.question or "")
                msg.add_ai_message(row.answer or "")
                if row.created_at:
                    msg.created_at = row.created_at
                result.append(msg)
            return result
        except Exception as e:
            logger.warning("ChatHistory.get error: {}", e)
            return []
        finally:
            self.db.close_session()

    def get_sessions(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        friend_id: Optional[str] = None,
        num_rounds: int = 10,
        fetch_all: bool = False,
    ) -> List[dict]:
        session = self.db.get_session()
        try:
            q = session.query(ChatSessionModel)
            if app_id:
                q = q.filter(ChatSessionModel.app_id == app_id)
            if user_name:
                q = q.filter(ChatSessionModel.user_name == user_name)
            if user_id:
                q = q.filter(ChatSessionModel.user_id == user_id)
            if session_id:
                q = q.filter(ChatSessionModel.session_id == session_id)
            if friend_id is not None:
                q = q.filter(ChatSessionModel.friend_id == (friend_id or ""))
            q = q.order_by(desc(ChatSessionModel.created_at))
            if not fetch_all:
                q = q.limit(num_rounds)
            rows = q.all()
            rows.reverse()
            return [
                {
                    "app_id": r.app_id,
                    "session_id": r.session_id,
                    "user_name": r.user_name,
                    "user_id": r.user_id,
                    "friend_id": r.friend_id or "",
                    "created_at": str(r.created_at) if r.created_at else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("ChatHistory.get_sessions error: {}", e)
            return []
        finally:
            self.db.close_session()

    def get_runs(
        self,
        agent_id: str = "",
        user_name: str = "",
        user_id: str = "",
        num_rounds: int = 10,
        fetch_all: bool = False,
    ) -> List[dict]:
        session = self.db.get_session()
        try:
            q = session.query(MemoryRunModel)
            if agent_id:
                q = q.filter(MemoryRunModel.agent_id == agent_id)
            if user_name:
                q = q.filter(MemoryRunModel.user_name == user_name)
            if user_id:
                q = q.filter(MemoryRunModel.user_id == user_id)
            q = q.order_by(desc(MemoryRunModel.created_at))
            if not fetch_all:
                q = q.limit(num_rounds)
            rows = q.all()
            rows.reverse()
            return [
                {
                    "agent_id": r.agent_id,
                    "run_id": r.run_id,
                    "user_name": r.user_name,
                    "user_id": r.user_id,
                    "created_at": str(r.created_at) if r.created_at else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("ChatHistory.get_runs error: {}", e)
            return []
        finally:
            self.db.close_session()

    def get_hist_by_role(
        self,
        sender_name: str = "",
        responder_name: str = "",
        num_rounds: int = 10,
    ) -> List[ChatMessage]:
        session = self.db.get_session()
        try:
            q = session.query(ChatHistoryByRoleModel)
            if sender_name:
                q = q.filter(ChatHistoryByRoleModel.sender_name == sender_name)
            if responder_name:
                q = q.filter(ChatHistoryByRoleModel.responder_name == responder_name)
            q = q.order_by(desc(ChatHistoryByRoleModel.created_at)).limit(num_rounds)
            rows = q.all()
            rows.reverse()
            result = []
            for r in rows:
                msg = ChatMessage()
                msg.add_user_message(r.sender_text or "")
                msg.add_ai_message(r.responder_text or "")
                if r.created_at:
                    msg.created_at = r.created_at
                result.append(msg)
            return result
        except Exception as e:
            logger.warning("ChatHistory.get_hist_by_role error: {}", e)
            return []
        finally:
            self.db.close_session()

    def add_by_role(
        self,
        sender_name: str,
        responder_name: str,
        sender_text: str,
        responder_text: str,
    ):
        session = self.db.get_session()
        try:
            row = ChatHistoryByRoleModel(
                id=str(uuid.uuid4()),
                sender_name=sender_name or "",
                responder_name=responder_name or "",
                sender_text=sender_text or "",
                responder_text=responder_text or "",
            )
            session.add(row)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning("ChatHistory.add_by_role error: {}", e)
        finally:
            self.db.close_session()

    def get_transcript(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        limit: int = 50,
        offset: int = 0,
        fetch_all: bool = False,
    ) -> List[dict]:
        session = self.db.get_session()
        try:
            q = session.query(ChatHistoryModel)
            if app_id:
                q = q.filter(ChatHistoryModel.app_id == app_id)
            if user_name:
                q = q.filter(ChatHistoryModel.user_name == user_name)
            if user_id:
                q = q.filter(ChatHistoryModel.user_id == user_id)
            if session_id:
                q = q.filter(ChatHistoryModel.session_id == session_id)
            q = q.order_by(ChatHistoryModel.created_at)
            if not fetch_all:
                q = q.offset(offset).limit(limit)
            rows = q.all()
            return [
                {
                    "role": "user",
                    "content": r.question or "",
                    "answer": r.answer or "",
                    "created_at": str(r.created_at) if r.created_at else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("ChatHistory.get_transcript error: {}", e)
            return []
        finally:
            self.db.close_session()

    def get_transcript_jsonl(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        limit: int = 50,
        fetch_all: bool = False,
    ) -> str:
        rows = self.get_transcript(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            fetch_all=fetch_all,
        )
        lines = []
        for r in rows:
            lines.append(json.dumps({"role": "user", "content": r.get("content", "")}, ensure_ascii=False))
            lines.append(json.dumps({"role": "assistant", "content": r.get("answer", "")}, ensure_ascii=False))
        return "\n".join(lines)

    def prune_session(
        self,
        app_id: str = "",
        user_name: str = "",
        user_id: str = "",
        session_id: str = "",
        friend_id: Optional[str] = None,
        keep_last_n: int = 10,
    ) -> int:
        session = self.db.get_session()
        try:
            q = session.query(ChatHistoryModel)
            if app_id:
                q = q.filter(ChatHistoryModel.app_id == app_id)
            if user_name:
                q = q.filter(ChatHistoryModel.user_name == user_name)
            if user_id:
                q = q.filter(ChatHistoryModel.user_id == user_id)
            if session_id:
                q = q.filter(ChatHistoryModel.session_id == session_id)
            if friend_id is not None:
                q = q.filter(ChatHistoryModel.friend_id == (friend_id or ""))
            total = q.count()
            if total <= keep_last_n:
                return 0
            to_delete = q.order_by(ChatHistoryModel.created_at).limit(total - keep_last_n).all()
            deleted = 0
            for row in to_delete:
                session.delete(row)
                deleted += 1
            session.commit()
            return deleted
        except Exception as e:
            session.rollback()
            logger.warning("ChatHistory.prune_session error: {}", e)
            return 0
        finally:
            self.db.close_session()
