"""Tests for reminder/cron message refinement (heuristic + optional LLM path)."""

import pytest

from core.reminder_message_refine import (
    normalize_llm_reminder_line,
    refine_scheduled_message_for_delivery,
    refine_scheduled_message_text,
)


def test_refine_chinese_birthday_buy_gift():
    q = "我儿子生日是8月19号，能不能提前一周提醒我买礼物"
    assert refine_scheduled_message_text(q) == "买礼物"


def test_refine_after_reminder_verb():
    assert refine_scheduled_message_text("明天下午三点提醒我开会") == "开会"


def test_refine_english_remind_me_to():
    assert refine_scheduled_message_text("Please can you remind me to call Mom") == "call Mom"


def test_refine_short_label_unchanged():
    assert refine_scheduled_message_text("喝水") == "喝水"


def test_refine_empty():
    assert refine_scheduled_message_text("") == "Reminder"
    assert refine_scheduled_message_text(None) == "Reminder"


def test_normalize_llm_reminder_line_fences_and_first_line():
    raw = '```\n买礼物\n```'
    assert normalize_llm_reminder_line(raw, max_chars=120) == "买礼物"
    assert normalize_llm_reminder_line('Say "hello"\nextra', max_chars=120) == 'Say "hello"'


@pytest.mark.asyncio
async def test_delivery_llm_path(monkeypatch):
    class _Core:
        async def openai_chat_completion(self, messages):
            assert "Turn this into" in messages[1]["content"]
            return "儿子生日礼物（提前一周）"

    import core.reminder_message_refine as mod

    monkeypatch.setattr(mod, "_read_reminder_message_llm_config", lambda: (True, 10.0))
    out = await refine_scheduled_message_for_delivery(
        _Core(),
        "我儿子生日是8月19号，能不能提前一周提醒我买礼物",
        max_chars=120,
    )
    assert "生日" in out and "礼物" in out


@pytest.mark.asyncio
async def test_delivery_llm_disabled_uses_heuristic(monkeypatch):
    import core.reminder_message_refine as mod

    monkeypatch.setattr(mod, "_read_reminder_message_llm_config", lambda: (False, 10.0))
    out = await refine_scheduled_message_for_delivery(
        None,
        "我儿子生日是8月19号，能不能提前一周提醒我买礼物",
        max_chars=120,
    )
    assert out == "买礼物"


def test_annual_birthday_fallback_uses_refined_message():
    from core.tool_helpers_fallback import infer_annual_birthday_advance_reminder_fallback

    r = infer_annual_birthday_advance_reminder_fallback(
        "我儿子生日是8月19号，能不能提前一周提醒我买礼物"
    )
    assert r is not None
    assert r["arguments"]["message"] == "买礼物"
