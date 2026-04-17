"""Weather skill: NL questions without a city must not be sent to wttr.in as the location string."""

import importlib.util
from pathlib import Path

import pytest


def _load_get_weather():
    root = Path(__file__).resolve().parent.parent
    path = root / "skills/weather-1.0.0/scripts/get_weather.py"
    spec = importlib.util.spec_from_file_location("get_weather_skill", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gw():
    return _load_get_weather()


def test_cn_tomorrow_only_question_clears_location_for_core_fallback(gw):
    """No embedded place → do not keep full sentence for wttr (would 500)."""
    raw = "明天天气怎么样"
    assert gw.extract_location_from_query(raw) == ""
    assert not gw._looks_like_plain_place(raw)
    location = raw
    extracted = gw.extract_location_from_query(location)
    if extracted:
        location = extracted
    elif not gw._looks_like_plain_place(location):
        location = ""
    assert location == ""


def test_cn_city_in_question_keeps_city(gw):
    assert gw.extract_location_from_query("北京明天天气怎么样") == "北京"


def test_plain_city_unchanged(gw):
    assert gw.extract_location_from_query("Paris") == "Paris"


def test_mixed_daily_reminder_and_beijing_forecast_not_garbage_city(gw):
    """Regression: mixed 提醒 + 北京的天气预报 must resolve to 北京 for wttr."""
    q = "每天早上八点钟给我发送北京的天气预报"
    assert gw.extract_location_from_query(q) == "北京"
