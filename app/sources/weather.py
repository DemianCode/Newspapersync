"""Weather source using Open-Meteo (free, no API key required).

Returns current conditions, today's daily summary (high/low, sunrise/sunset,
max precipitation probability), and an hourly forecast for the remaining
hours of the day.
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from app import config_loader as cfg

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}

_WMO_EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️",
    80: "🌦️", 81: "🌦️", 82: "⛈️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}


def fetch() -> list[dict]:
    if cfg.get("WEATHER_ENABLED", "true").lower() != "true":
        return []

    lat = cfg.get("WEATHER_LAT", "")
    lon = cfg.get("WEATHER_LON", "")
    if not lat or not lon or lat in ("YOUR_LAT", ""):
        logger.warning("Weather disabled — set WEATHER_LAT and WEATHER_LON in Settings or docker-compose.yml")
        return []

    units = cfg.get("WEATHER_UNITS", "celsius").lower()
    temp_unit = "celsius" if units == "celsius" else "fahrenheit"
    temp_symbol = "°C" if temp_unit == "celsius" else "°F"
    location = cfg.get("WEATHER_LOCATION_NAME", "")

    try:
        resp = requests.get(_BASE_URL, params={
            "latitude": lat,
            "longitude": lon,
            "current": [
                "temperature_2m", "apparent_temperature",
                "weathercode", "windspeed_10m", "relativehumidity_2m",
            ],
            "hourly": [
                "temperature_2m", "precipitation_probability", "weathercode",
            ],
            "daily": [
                "temperature_2m_max", "temperature_2m_min",
                "weathercode", "precipitation_probability_max",
                "sunrise", "sunset",
            ],
            "temperature_unit": temp_unit,
            "windspeed_unit": "kmh",
            "forecast_days": 2,
            "timezone": "auto",
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Weather fetch failed: %s", exc)
        return []

    current = data.get("current", {})
    hourly  = data.get("hourly", {})
    daily   = data.get("daily", {})

    # ── Current conditions ────────────────────────────────────────────────────
    temp = current.get("temperature_2m", "?")
    feels = current.get("apparent_temperature", "?")
    wind = current.get("windspeed_10m", "?")
    humidity = current.get("relativehumidity_2m", "?")
    weather_code = current.get("weathercode", -1)
    condition = _WMO_CODES.get(weather_code, "Unknown")
    emoji = _WMO_EMOJI.get(weather_code, "🌡️")

    # ── Daily summary (today = index 0) ───────────────────────────────────────
    high        = daily.get("temperature_2m_max",          [None])[0]
    low         = daily.get("temperature_2m_min",          [None])[0]
    day_code    = daily.get("weathercode",                 [-1])[0]
    precip_max  = daily.get("precipitation_probability_max",[None])[0]
    sunrise_raw = daily.get("sunrise",                     [""])[0]   # e.g. "2024-01-15T06:23"
    sunset_raw  = daily.get("sunset",                      [""])[0]

    sunrise = sunrise_raw[11:16] if len(sunrise_raw) > 11 else sunrise_raw
    sunset  = sunset_raw[11:16]  if len(sunset_raw)  > 11 else sunset_raw

    day_condition = _WMO_CODES.get(day_code, condition)
    day_emoji     = _WMO_EMOJI.get(day_code, emoji)

    # Tomorrow summary (index 1)
    tmrw_high      = daily.get("temperature_2m_max",           [None, None])[1]
    tmrw_low       = daily.get("temperature_2m_min",           [None, None])[1]
    tmrw_code      = daily.get("weathercode",                  [-1, -1])[1]
    tmrw_precip    = daily.get("precipitation_probability_max", [None, None])[1]
    tmrw_condition = _WMO_CODES.get(tmrw_code, "")
    tmrw_emoji     = _WMO_EMOJI.get(tmrw_code, "")

    # ── Hourly rows: skip past hours, show rest of today every 3 h ───────────
    now_hour = datetime.now().hour  # e.g. 6 → start from index 6 (06:00)

    hourly_times  = hourly.get("time", [])
    hourly_temps  = hourly.get("temperature_2m", [])
    hourly_precip = hourly.get("precipitation_probability", [])
    hourly_codes  = hourly.get("weathercode", [])

    hourly_rows = []
    # Indices 0–23 = today; step by 3, starting from the current hour
    start = (now_hour // 3) * 3  # round down to nearest 3-hour slot
    for i in range(start, 24, 3):
        if i >= len(hourly_times):
            break
        code = hourly_codes[i] if i < len(hourly_codes) else -1
        hourly_rows.append({
            "time":      hourly_times[i][11:16] if len(hourly_times[i]) > 11 else hourly_times[i],
            "temp":      f"{hourly_temps[i]}{temp_symbol}"  if i < len(hourly_temps)  else "",
            "precip":    f"{hourly_precip[i]}%"             if i < len(hourly_precip) else "",
            "condition": _WMO_CODES.get(code, ""),
            "emoji":     _WMO_EMOJI.get(code, ""),
        })

    return [{
        "type": "weather",
        "source": "Open-Meteo",
        "title": f"Weather — {location}" if location else "Weather",
        "body": (
            f"{day_condition}. High {high}{temp_symbol}, low {low}{temp_symbol}. "
            f"Sunrise {sunrise}, sunset {sunset}. "
            f"Rain chance {precip_max}%. Wind {wind} km/h."
        ),
        "meta": {
            "temp":        temp,
            "feels_like":  feels,
            "temp_symbol": temp_symbol,
            "condition":   condition,
            "emoji":       emoji,
            "wind":        wind,
            "humidity":    humidity,
            # Today's forecast summary
            "high":        high,
            "low":         low,
            "day_condition": day_condition,
            "day_emoji":     day_emoji,
            "precip_max":  precip_max,
            "sunrise":     sunrise,
            "sunset":      sunset,
            # Tomorrow
            "tomorrow": {
                "high":      tmrw_high,
                "low":       tmrw_low,
                "condition": tmrw_condition,
                "emoji":     tmrw_emoji,
                "precip":    tmrw_precip,
            },
            # Hourly from now
            "hourly": hourly_rows,
        },
    }]
