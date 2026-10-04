"""On-demand educational marine forecasts; never vessel telemetry.

Caller must enable this only for authorized noncommercial use. Limits are per
Python process: one request in flight, one start per 60 seconds, at most 200
upstream attempts per UTC day (including failures), 32 cache keys, 10-minute
TTL. These restart-reset limits are not a workspace hard cap; multiple workers
need a shared limiter. No database or durable quota ledger is used.
No background collector, retries, credentials, paid endpoints, or AIS feeds.
The five-second urllib timeout bounds socket inactivity, not total wall time.
"""

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ENDPOINT = "https://marine-api.open-meteo.com/v1/marine"
MAX_RESPONSE_BYTES = 64 * 1024
TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 600
CACHE_MAX_KEYS = 32
MIN_REQUEST_INTERVAL = 60
MAX_DAILY_ATTEMPTS = 200
_lock = threading.Lock()
_cache = OrderedDict()
_last_request = None
_daily_date = None
_daily_attempts = 0


class TrackingError(Exception):
    """Public, sanitized error; never expose upstream bodies or URLs."""

    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TrackingError("upstream_redirect", "Forecast provider redirected unexpectedly.")


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _coordinate(value, limit):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TrackingError("invalid_coordinates", "Enter finite WGS84 coordinates.", 400)
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise TrackingError("invalid_coordinates", "Enter finite WGS84 coordinates.", 400) from None
    if not math.isfinite(number) or not -limit <= number <= limit:
        raise TrackingError("invalid_coordinates", "Enter finite WGS84 coordinates.", 400)
    return number


def _value(value, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid measurement")
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("invalid measurement")
    return value


def _parse(payload, latitude, longitude, retrieved):
    try:
        if not isinstance(payload, dict) or payload.get("error") or payload["utc_offset_seconds"] != 0:
            raise ValueError("invalid envelope")
        grid_lat = _coordinate(payload["latitude"], 90)
        grid_lon = _coordinate(payload["longitude"], 180)
        current = payload["current"]
        units = payload["current_units"]
        if not isinstance(current, dict) or not isinstance(units, dict):
            raise ValueError("invalid current")
        for key, unit in (("wave_height", "m"), ("wave_period", "s"), ("wave_direction", "°")):
            if units[key] != unit:
                raise ValueError("invalid units")
        valid = datetime.fromisoformat(current["time"].replace("Z", "+00:00"))
        if valid.tzinfo is None:
            valid = valid.replace(tzinfo=timezone.utc)
        if valid.utcoffset().total_seconds() != 0:
            raise ValueError("non UTC time")
        age = (retrieved - valid).total_seconds()
        if age > 3600 or age < -900:
            raise TrackingError("stale_forecast", "Forecast time is outside the current validity window.")
        result = {
            "status": "forecast",
            "requested_coordinates": {"latitude": latitude, "longitude": longitude},
            "forecast_grid_coordinates": {"latitude": grid_lat, "longitude": grid_lon},
            "valid_at": _iso(valid),
            "retrieved_at": _iso(retrieved),
            "wave_height_m": _value(current["wave_height"]),
            "wave_period_s": _value(current["wave_period"]),
            "wave_direction_deg": _value(current["wave_direction"], 360),
            "source": {
                "name": "Open-Meteo Marine Weather API",
                "url": "https://open-meteo.com/en/docs/marine-weather-api",
                "model": "Best Match (individual model not identified in response)",
                "model_attribution": "Open-Meteo and its marine model data providers",
                "model_attribution_url": "https://open-meteo.com/en/docs/marine-weather-api#data-sources",
                "license_url": "https://open-meteo.com/en/license",
            },
            "cached": False,
            "notice": "Model forecast at manually entered coordinates; not observed vessel conditions or navigation advice.",
        }
    except TrackingError as exc:
        if exc.code == "stale_forecast":
            raise
        raise TrackingError("malformed_forecast", "Forecast provider returned invalid data.") from None
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise TrackingError("malformed_forecast", "Forecast provider returned invalid data.") from None
    return result


def get_marine_forecast(latitude, longitude):
    """Fetch current model wave forecast; all outbound URLs are fixed-host HTTPS."""
    global _last_request, _daily_date, _daily_attempts
    latitude = _coordinate(latitude, 90)
    longitude = _coordinate(longitude, 180)
    key = (latitude, longitude)
    if not _lock.acquire(blocking=False):
        raise TrackingError("forecast_busy", "A forecast request is already in progress. Try again shortly.", 429)
    try:
        now = time.monotonic()
        for stale_key in list(_cache):
            if now - _cache[stale_key][0] >= CACHE_TTL_SECONDS:
                del _cache[stale_key]
        if key in _cache:
            result = deepcopy(_cache[key][1])
            valid = datetime.fromisoformat(result["valid_at"].replace("Z", "+00:00"))
            age = (_utcnow() - valid).total_seconds()
            if -900 <= age <= 3600:
                _cache.move_to_end(key)
                result["cached"] = True
                return result
            del _cache[key]
        if _last_request is not None and now - _last_request < MIN_REQUEST_INTERVAL:
            raise TrackingError("forecast_rate_limited", "Wait 60 seconds between new forecast requests.", 429)
        utc_date = _utcnow().date()
        if _daily_date != utc_date:
            _daily_date, _daily_attempts = utc_date, 0
        if _daily_attempts >= MAX_DAILY_ATTEMPTS:
            raise TrackingError("forecast_daily_budget", "The daily forecast request budget was reached. Try again tomorrow (UTC).", 429)
        _last_request = now
        _daily_attempts += 1
        url = ENDPOINT + "?" + urlencode({
            "latitude": latitude, "longitude": longitude,
            "current": "wave_height,wave_period,wave_direction",
            "timezone": "GMT", "forecast_hours": 1, "cell_selection": "sea",
        })
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "CargoEducationalPortfolio/1.0"})
        # Disable implicit proxy routing and all redirects. urllib performs no retries.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise TrackingError("forecast_unavailable", "Forecast provider is unavailable.")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise TrackingError("forecast_too_large", "Forecast response exceeded the size limit.")
            payload = json.loads(raw)
        except HTTPError as exc:
            if exc.code == 429:
                raise TrackingError("provider_quota", "Forecast provider quota was reached. Try again later.", 429) from None
            raise TrackingError("forecast_unavailable", "Forecast provider is unavailable.") from None
        except (TimeoutError, socket.timeout):
            raise TrackingError("forecast_timeout", "Forecast provider timed out.", 504) from None
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TrackingError("forecast_timeout", "Forecast provider timed out.", 504) from None
            raise TrackingError("forecast_unavailable", "Forecast provider is unavailable.") from None
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise TrackingError("malformed_forecast", "Forecast provider returned invalid data.") from None
        except OSError:
            raise TrackingError("forecast_unavailable", "Forecast provider is unavailable.") from None
        result = _parse(payload, latitude, longitude, _utcnow())
        _cache[key] = (time.monotonic(), deepcopy(result))
        while len(_cache) > CACHE_MAX_KEYS:
            _cache.popitem(last=False)
        return result
    finally:
        _lock.release()


def get_ais_status():
    """No provider is configured, so no vessel locations are claimed."""
    return {
        "status": "unconfigured", "code": "ais_unconfigured", "positions": [],
        "message": "AIS tracking is not configured. A licensed provider, permitted public-display rights, and credentials are required.",
    }
