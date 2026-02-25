import uuid

from sqlalchemy import TIMESTAMP, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()
metadata = Base.metadata


class DataSource(Base):
    __tablename__ = "homeclaw_data_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    app_id = Column(Text, index=True)
    hash = Column(Text, index=True)
    type = Column(Text, index=True)
    value = Column(Text)
    meta_data = Column(Text, name="metadata")
    is_uploaded = Column(Integer, default=0)


class ChatHistoryModel(Base):
    __tablename__ = "homeclaw_chat_history"

    app_id = Column(String, primary_key=True)
    id = Column(String, primary_key=True)
    user_name = Column(String, primary_key=True, index=True)
    user_id = Column(String, primary_key=True, index=True)
    session_id = Column(String, primary_key=True, index=True)
    question = Column(Text)
    answer = Column(Text)
    meta_data = Column(Text, name="metadata")
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)
    
    
class ChatHistoryByRoleModel(Base):
    __tablename__ = "homeclaw_chat_history_by_role"
    id = Column(String, primary_key=True) 
    sender_name = Column(String, primary_key=True, index=True)
    responder_name = Column(String, primary_key=True, index=True)
    sender_text = Column(Text)
    responder_text = Column(Text)
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)


class ChatSessionModel(Base):
    __tablename__ = "homeclaw_session_history"

    app_id = Column(String, primary_key=True)
    id = Column(String, primary_key=True)
    user_name = Column(String, primary_key=True, index=True)
    user_id = Column(String, primary_key=True, index=True)
    session_id = Column(String, primary_key=True, index=True)
    meta_data = Column(Text, name="metadata")
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)


class MemoryRunModel(Base):
    __tablename__ = "homeclaw_run_history"

    agent_id = Column(String, primary_key=True)
    id = Column(String, primary_key=True)
    user_name = Column(String, primary_key=True, index=True)
    user_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, primary_key=True, index=True)
    meta_data = Column(Text, name="metadata")
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)


class LastChannelModel(Base):
    """Stores last channel (request metadata) for send_response_to_latest_channel. Key='default' for global latest; or app_id:user_id:session_id for per-session."""
    __tablename__ = "homeclaw_last_channel"

    key = Column(String, primary_key=True)  # "default" or "app_id:user_id:session_id"
    request_id = Column(String, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    channel_name = Column(String, nullable=False)
    app_id = Column(String, nullable=True)  # for HomeClaw console check
    request_metadata = Column(Text, nullable=False)  # JSON
    updated_at = Column(TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp(), index=True)


class TamCronJobModel(Base):
    """Persisted cron jobs (TAM). Survives Core restart; loaded and re-scheduled on TAM init."""
    __tablename__ = "homeclaw_tam_cron_jobs"

    job_id = Column(String, primary_key=True)
    cron_expr = Column(String, nullable=False)
    params = Column(Text, nullable=False)  # JSON, e.g. {"message": "..."}
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)


class TamOneShotReminderModel(Base):
    """Persisted one-shot reminders (TAM). Survives Core restart; loaded and re-scheduled on TAM init. Deleted after firing."""
    __tablename__ = "homeclaw_tam_one_shot_reminders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_at = Column(DateTime, nullable=False, index=True)  # when to send the reminder
    message = Column(Text, nullable=False)
    user_id = Column(String, nullable=True)  # for deliver_to_user (Companion push)
    channel_key = Column(String, nullable=True)  # for channel delivery (per-session cron)
    created_at = Column(TIMESTAMP, default=func.current_timestamp(), index=True)
