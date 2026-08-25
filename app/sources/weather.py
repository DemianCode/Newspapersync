"""Weather source using Open-Meteo (free, no API key required).

The newspaper is a *forecast* for the day ahead, so this module leads with
today's outlook — the day's weather code, high/low, rain chance, wind and
daylight hours — plus a fixed set of day-part slots (morning → night) and a
one-line look at tomorrow. Current conditions are still returned under
``meta.now`` for anything that wants them, but they are not the headline.
"""

from __future__ import annotations

import logging
from datetime import date

import requests

from app import config_loader as cfg

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}

# Icon slugs map onto the line-art SVGs drawn in templates/newspaper.html.
# Monochrome shapes print far more reliably on e-ink than colour emoji.
_WMO_ICONS = {
    0: "clear", 1: "mostly-clear", 2: "partly-cloudy", 3: "overcast",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle", 57: "drizzle",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "showers", 81: "showers", 82: "showers",
    85: "snow", 86: "snow",
    95: "thunder", 96: "thunder", 99: "thunder",
}

# Day parts shown in the forecast strip (hour of day → label).
_DAY_PARTS = [(6, "Morning"), (9, "Late AM"), (12, "Midday"),
              (15, "Afternoon"), (18, "Evening"), (21, "Night")]


def _icon(code) -> str:
    return _WMO_ICONS.get(code, "unknown")


def _condition(code) -> str:
    return _WMO_CODES.get(code, "Unknown")


def _at(seq, index, default=None):
    try:
        value = seq[index]
    except (IndexError, TypeError):
        return default
    return default if value is None else value


def _round(value):
    """Open-Meteo returns floats; whole numbers read better in print."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return value


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
                "temperature_2m", "apparent_temperature",
                "precipitation_probability", "weathercode", "windspeed_10m",
            ],
            "daily": [
                "temperature_2m_max", "temperature_2m_min",
                "apparent_temperature_max", "apparent_temperature_min",
                "weathercode", "precipitation_probability_max",
                "precipitation_sum", "windspeed_10m_max", "uv_index_max",
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

    current = data.get("current", {}) or {}
    hourly = data.get("hourly", {}) or {}
    daily = data.get("daily", {}) or {}

    # ── Today's forecast (daily index 0) ─────────────────────────────────────
    day_code = _at(daily.get("weathercode", []), 0, -1)
    high = _round(_at(daily.get("temperature_2m_max", []), 0))
    low = _round(_at(daily.get("temperature_2m_min", []), 0))
    feels_high = _round(_at(daily.get("apparent_temperature_max", []), 0))
    feels_low = _round(_at(daily.get("apparent_temperature_min", []), 0))
    precip_chance = _round(_at(daily.get("precipitation_probability_max", []), 0))
    precip_sum = _at(daily.get("precipitation_sum", []), 0)
    wind_max = _round(_at(daily.get("windspeed_10m_max", []), 0))
    uv_max = _round(_at(daily.get("uv_index_max", []), 0))

    sunrise_raw = _at(daily.get("sunrise", []), 0, "")   # "2024-01-15T06:23"
    sunset_raw = _at(daily.get("sunset", []), 0, "")
    sunrise = sunrise_raw[11:16] if len(sunrise_raw) > 11 else sunrise_raw
    sunset = sunset_raw[11:16] if len(sunset_raw) > 11 else sunset_raw

    day_condition = _condition(day_code)
    day_icon = _icon(day_code)

    # ── Tomorrow (daily index 1) ─────────────────────────────────────────────
    tmrw_code = _at(daily.get("weathercode", []), 1, -1)
    tomorrow = {
        "high": _round(_at(daily.get("temperature_2m_max", []), 1)),
        "low": _round(_at(daily.get("temperature_2m_min", []), 1)),
        "condition": _condition(tmrw_code) if tmrw_code != -1 else "",
        "icon": _icon(tmrw_code) if tmrw_code != -1 else "",
        "precip": _round(_at(daily.get("precipitation_probability_max", []), 1)),
    }

    # ── Day-part forecast for today ──────────────────────────────────────────
    # Anchor on the API's own local date so the slots always describe *today*
    # in the forecast location, regardless of where the container runs.
    today_str = _at(daily.get("time", []), 0, date.today().isoformat())

    times = hourly.get("time", []) or []
    temps = hourly.get("temperature_2m", []) or []
    precips = hourly.get("precipitation_probability", []) or []
    codes = hourly.get("weathercode", []) or []

    index_by_hour = {}
    for i, stamp in enumerate(times):
        if stamp.startswith(today_str) and len(stamp) >= 13:
            try:
                index_by_hour[int(stamp[11:13])] = i
            except ValueError:
                continue

    day_parts = []
    for hour, label in _DAY_PARTS:
        i = index_by_hour.get(hour)
        if i is None:
            continue
        code = _at(codes, i, -1)
        day_parts.append({
            "label": label,
            "time": f"{hour:02d}:00",
            "temp": _round(_at(temps, i)),
            "precip": _round(_at(precips, i)),
            "condition": _condition(code),
            "icon": _icon(code),
        })

    # ── Current conditions (kept, but not the headline) ──────────────────────
    now_code = current.get("weathercode", -1)
    now = {
        "temp": _round(current.get("temperature_2m")),
        "feels_like": _round(current.get("apparent_temperature")),
        "condition": _condition(now_code),
        "icon": _icon(now_code),
        "wind": _round(current.get("windspeed_10m")),
        "humidity": _round(current.get("relativehumidity_2m")),
    }

    summary = f"{day_condition}."
    if high is not None and low is not None:
        summary += f" High {high}{temp_symbol}, low {low}{temp_symbol}."
    if precip_chance is not None:
        summary += f" {precip_chance}% chance of rain."
    if wind_max is not None:
        summary += f" Wind up to {wind_max} km/h."
    if sunrise and sunset:
        summary += f" Sunrise {sunrise}, sunset {sunset}."

    return [{
        "type": "weather",
        "source": "Open-Meteo",
        "title": f"Forecast — {location}" if location else "Today's Forecast",
        "body": summary,
        "meta": {
            "location": location,
            "temp_symbol": temp_symbol,
            # Today's forecast
            "condition": day_condition,
            "icon": day_icon,
            "high": high,
            "low": low,
            "feels_high": feels_high,
            "feels_low": feels_low,
            "precip_chance": precip_chance,
            "precip_sum": precip_sum,
            "wind_max": wind_max,
            "uv_max": uv_max,
            "sunrise": sunrise,
            "sunset": sunset,
            # Rest of the outlook
            "day_parts": day_parts,
            "tomorrow": tomorrow,
            # Current conditions, for anything that still wants them
            "now": now,
        },
    }]
