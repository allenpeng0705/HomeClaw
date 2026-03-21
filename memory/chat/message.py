from datetime import datetime


class _MessageSlot:
    __slots__ = ("content",)

    def __init__(self, content: str = ""):
        self.content = content


class ChatMessage:
    def __init__(self):
        self.human_message = _MessageSlot()
        self.ai_message = _MessageSlot()
        self.created_at: datetime = datetime.utcnow()

    def add_user_message(self, text: str):
        self.human_message = _MessageSlot(text or "")

    def add_ai_message(self, text: str):
        self.ai_message = _MessageSlot(text or "")
