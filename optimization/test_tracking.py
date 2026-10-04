"""Provider boundary tests: mocked transport only, no network or database."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from optimization import tracking


class MarineForecastTests(TestCase):
    def setUp(self):
        tracking._cache.clear()
        tracking._last_request = None
        tracking._daily_date = None
        tracking._daily_attempts = 0
        self.now = datetime(2026, 10, 4, 12, 5, tzinfo=timezone.utc)
        self.fixture = {
            "latitude": 12.1, "longitude": 72.2, "utc_offset_seconds": 0,
            "current": {"time": "2026-10-04T12:00", "wave_height": 1.4,
                        "wave_period": 6.2, "wave_direction": 245.0},
            "current_units": {"wave_height": "m", "wave_period": "s", "wave_direction": "°"},
        }
        self.opener = MagicMock()
        self.transport = patch.object(tracking, "build_opener", return_value=self.opener).start()
        patch.object(tracking, "_utcnow", return_value=self.now).start()
        self.clock = patch.object(tracking.time, "monotonic", return_value=100.0).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(tracking._cache.clear)
        self.respond(self.fixture)

    def respond(self, payload):
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(payload).encode()
        self.opener.open.return_value.__enter__.return_value = response
        return response

    def assert_error(self, code, *coords):
        with self.assertRaises(tracking.TrackingError) as raised:
            tracking.get_marine_forecast(*(coords or (12, 72)))
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_coordinates_and_time_are_truthful(self):
        result = tracking.get_marine_forecast("12", "72")
        self.assertEqual(result["requested_coordinates"], {"latitude": 12.0, "longitude": 72.0})
        self.assertEqual(result["forecast_grid_coordinates"]["latitude"], 12.1)
        self.assertEqual(result["valid_at"], "2026-10-04T12:00:00Z")
        self.assertEqual(result["retrieved_at"], "2026-10-04T12:05:00Z")
        self.assertEqual(result["wave_height_m"], 1.4)
        self.assertIn("not observed", result["notice"])

    def test_fixed_host_small_request_and_timeout(self):
        response = self.respond(self.fixture)
        tracking.get_marine_forecast(12, 72)
        request = self.opener.open.call_args.args[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "marine-api.open-meteo.com", "/v1/marine"))
        query = parse_qs(parsed.query)
        self.assertEqual(query["forecast_hours"], ["1"])
        self.assertEqual(query["timezone"], ["GMT"])
        self.assertNotIn("apikey", query)
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 5)
        response.read.assert_called_once_with(65537)

    def test_invalid_coordinates_never_use_network(self):
        for value in (True, None, [], {}, "nan", "inf", float("nan"), 91, -91, "72,73", "https://other.test"):
            with self.subTest(value=value):
                self.assert_error("invalid_coordinates", value, 0)
        self.assert_error("invalid_coordinates", 0, 181)
        self.opener.open.assert_not_called()

    def test_nulls_remain_unknown_and_zero_is_preserved(self):
        self.fixture["current"].update(wave_height=None, wave_period=0, wave_direction=None)
        self.respond(self.fixture)
        result = tracking.get_marine_forecast(12, 72)
        self.assertIsNone(result["wave_height_m"])
        self.assertIsNone(result["wave_direction_deg"])
        self.assertEqual(result["wave_period_s"], 0)

    def test_cache_is_copy_and_preserves_retrieval_time(self):
        first = tracking.get_marine_forecast(12, 72)
        first["source"]["name"] = "tampered"
        cached = tracking.get_marine_forecast(12, 72)
        self.assertTrue(cached["cached"])
        self.assertNotEqual(cached["source"]["name"], "tampered")
        self.assertEqual(cached["retrieved_at"], "2026-10-04T12:05:00Z")
        self.assertEqual(tracking._daily_attempts, 1)
        self.opener.open.assert_called_once()

    def test_global_rate_limit_and_failed_attempt_budget(self):
        self.opener.open.side_effect = URLError("private failure detail")
        self.assert_error("forecast_unavailable")
        self.assert_error("forecast_rate_limited", 13, 73)
        self.opener.open.assert_called_once()

    def test_busy_guard_never_blocks_or_calls_network(self):
        tracking._lock.acquire()
        try:
            self.assertEqual(self.assert_error("forecast_busy").status, 429)
            self.opener.open.assert_not_called()
        finally:
            tracking._lock.release()

    def test_cache_expiry_and_maximum_keys(self):
        tracking.get_marine_forecast(12, 72)
        self.clock.return_value = 700
        self.assertFalse(tracking.get_marine_forecast(12, 72)["cached"])
        # With a 60s interval, normal 600s TTL expires before 32 keys collect.
        # Extend TTL only in this test to exercise the independent capacity cap.
        with patch.object(tracking, "CACHE_TTL_SECONDS", 3600):
            for i in range(33):
                self.clock.return_value = 760 + i * tracking.MIN_REQUEST_INTERVAL
                tracking.get_marine_forecast(i, 0)
        self.assertEqual(len(tracking._cache), 32)
        self.assertNotIn((0.0, 0.0), tracking._cache)

    def test_cache_does_not_extend_forecast_validity(self):
        self.fixture["current"]["time"] = "2026-10-04T11:06"
        self.respond(self.fixture)
        tracking.get_marine_forecast(12, 72)
        self.clock.return_value = 220
        with patch.object(tracking, "_utcnow", return_value=self.now + timedelta(minutes=2)):
            self.assert_error("stale_forecast")
        self.assertNotIn((12.0, 72.0), tracking._cache)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_daily_budget_counts_failures_and_resets_utc_day(self):
        tracking._daily_date = self.now.date()
        tracking._daily_attempts = tracking.MAX_DAILY_ATTEMPTS - 1
        self.opener.open.side_effect = URLError("private detail")
        self.assert_error("forecast_unavailable")
        self.assertEqual(tracking._daily_attempts, 200)
        self.clock.return_value = 160
        self.assertEqual(self.assert_error("forecast_daily_budget").status, 429)
        self.assertEqual(self.opener.open.call_count, 1)
        with patch.object(tracking, "_utcnow", return_value=self.now + timedelta(days=1)):
            self.assert_error("forecast_unavailable")
        self.assertEqual(tracking._daily_attempts, 1)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_stale_and_future_forecasts_rejected(self):
        for delta in (-61, 16):
            tracking._last_request = None
            self.fixture["current"]["time"] = (self.now + timedelta(minutes=delta)).isoformat()
            self.respond(self.fixture)
            self.assert_error("stale_forecast")

    def test_malformed_units_values_and_envelopes(self):
        variants = [[], {}, {**self.fixture, "utc_offset_seconds": 3600},
                    {**self.fixture, "latitude": "nan"}]
        for key, value in (("time", "invalid"), ("wave_height", -1), ("wave_period", True),
                           ("wave_direction", 361), ("wave_period", float("inf"))):
            fixture = deepcopy(self.fixture)
            fixture["current"][key] = value
            variants.append(fixture)
        fixture = deepcopy(self.fixture)
        fixture["current_units"]["wave_height"] = "ft"
        variants.append(fixture)
        for payload in variants:
            tracking._last_request = None
            self.respond(payload)
            self.assert_error("malformed_forecast")

    def test_oversized_or_invalid_json_rejected(self):
        response = self.respond(self.fixture)
        response.read.return_value = b"x" * 65537
        self.assert_error("forecast_too_large")
        tracking._last_request = None
        response.read.return_value = b"not json"
        self.assert_error("malformed_forecast")

    def test_timeout_quota_and_upstream_errors_sanitized_no_retries(self):
        for error, code, status in (
            (TimeoutError("secret"), "forecast_timeout", 504),
            (URLError(TimeoutError("secret")), "forecast_timeout", 504),
            (HTTPError("secret", 429, "secret", {}, io.BytesIO()), "provider_quota", 429),
            (HTTPError("secret", 500, "secret", {}, io.BytesIO()), "forecast_unavailable", 502),
        ):
            tracking._last_request = None
            self.opener.open.reset_mock()
            self.opener.open.side_effect = error
            result = self.assert_error(code)
            self.assertEqual(result.status, status)
            self.assertNotIn("secret", result.message)
            self.opener.open.assert_called_once()

    def test_redirect_handler_rejects_redirect(self):
        with self.assertRaises(tracking.TrackingError) as raised:
            tracking._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test")
        self.assertEqual(raised.exception.code, "upstream_redirect")

    def test_ais_is_unconfigured_without_positions(self):
        status = tracking.get_ais_status()
        self.assertEqual(status["status"], "unconfigured")
        self.assertEqual(status["positions"], [])
        self.assertIn("licensed", status["message"])
        self.opener.open.assert_not_called()
