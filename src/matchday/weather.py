import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import urlopen

from .domain import timestamp


def forecast(fixture, now=None, opener=urlopen):
    now = now or datetime.now(UTC)
    kickoff = timestamp(fixture["kickoff"])
    hours = (kickoff - now).total_seconds() / 3600
    if not 0 < hours < 7 * 24 or fixture.get("latitude") is None:
        return None
    query = urlencode(
        {
            "latitude": fixture["latitude"],
            "longitude": fixture["longitude"],
            "hourly": "temperature_2m,precipitation_probability",
            "timezone": "UTC",
            "timeformat": "unixtime",
            "forecast_days": 7,
        }
    )
    with opener("https://api.open-meteo.com/v1/forecast?" + query, timeout=15) as response:
        raw = json.load(response)
    hourly = raw["hourly"]
    index = min(
        range(len(hourly["time"])), key=lambda i: abs(hourly["time"][i] - kickoff.timestamp())
    )
    epoch = hourly["time"][index]
    if abs(epoch - kickoff.timestamp()) > 3600:
        return None
    temp = hourly["temperature_2m"][index]
    rain = hourly["precipitation_probability"][index]
    if temp is None or rain is None:
        return None
    return {
        "temperature_c": float(temp),
        "rain_probability": int(rain),
        "forecast_for": datetime.fromtimestamp(epoch, UTC).isoformat(),
        "fetched_at": now.isoformat(),
        "source": "Open-Meteo",
        "attribution": "Weather data by Open-Meteo.com",
    }
