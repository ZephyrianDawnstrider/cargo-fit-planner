import importlib
import os
import sys
import subprocess
from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.test import RequestFactory

from .admission import ComputeRateLimitMiddleware


class RenderDeploymentSettingsTests(SimpleTestCase):
    def test_production_settings_fail_closed_without_required_environment(self):
        sys.modules.pop("dcd_project.settings_render", None)
        with patch.dict(os.environ, {"SECRET_KEY": "", "RENDER_EXTERNAL_HOSTNAME": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                importlib.import_module("dcd_project.settings_render")

    def test_production_settings_are_stateless_and_do_not_inherit_legacy(self):
        sys.modules.pop("dcd_project.settings_render", None)
        env = {
            "SECRET_KEY": "s" * 64,
            "RENDER_EXTERNAL_HOSTNAME": "cargo-fit-planner.onrender.com",
            "CARGO_WEATHER_FREE_API_ENABLED": "",
        }
        with patch.dict(os.environ, env, clear=False):
            module = importlib.import_module("dcd_project.settings_render")
        self.assertFalse(module.DEBUG)
        self.assertEqual(module.ALLOWED_HOSTS, ["cargo-fit-planner.onrender.com"])
        self.assertEqual(module.DATABASES["default"]["ENGINE"], "django.db.backends.dummy")
        self.assertEqual(module.INSTALLED_APPS, [])
        self.assertNotIn("django.contrib.sessions.middleware.SessionMiddleware", module.MIDDLEWARE)
        self.assertNotIn("optimization.routers", module.DATABASE_ROUTERS)
        self.assertFalse(module.WEATHER_FREE_API_ENABLED)
        self.assertTrue(module.CSRF_COOKIE_SECURE)
        self.assertTrue(module.SECURE_SSL_REDIRECT)
        self.assertLess(module.MIDDLEWARE.index("optimization.admission.ComputeRateLimitMiddleware"), module.MIDDLEWARE.index("django.middleware.csrf.CsrfViewMiddleware"))

    @override_settings(ROOT_URLCONF="dcd_project.urls_render", ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
    def test_health_route_is_get_only_and_does_not_need_database(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok\n")
        self.assertEqual(self.client.post("/healthz").status_code, 405)

    @override_settings(ROOT_URLCONF="dcd_project.urls_render", ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^healthz$"], SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_health_is_exempt_from_internal_http_redirect_and_page_uses_https(self):
        health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        redirect = self.client.get("/")
        self.assertEqual(redirect.status_code, 301)
        self.assertTrue(redirect["Location"].startswith("https://"))

    @override_settings(ROOT_URLCONF="dcd_project.urls_render", ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), SECURE_HSTS_SECONDS=86_400, SECURE_HSTS_INCLUDE_SUBDOMAINS=True, CSRF_COOKIE_SECURE=True, CSRF_COOKIE_HTTPONLY=True)
    def test_secure_page_sets_transport_and_csrf_cookie_flags(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=86400", response["Strict-Transport-Security"])
        csrf = response.cookies["csrftoken"]
        self.assertTrue(csrf["secure"])
        self.assertTrue(csrf["httponly"])

    def test_wsgi_entrypoint_fails_closed_without_secret(self):
        env = os.environ.copy()
        env.update({"SECRET_KEY": "", "RENDER_EXTERNAL_HOSTNAME": "", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "."})
        child = subprocess.run(
            [sys.executable, "-c", "import dcd_project.wsgi_render"],
            cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("SECRET_KEY", child.stderr)

    def test_staged_runtime_contains_only_allowlisted_app_files(self):
        from scripts.build_render_runtime import ALLOWLIST, MARKER, TARGET, build_runtime

        copied = build_runtime()
        self.assertEqual(set(copied), set(ALLOWLIST))
        staged = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file()}
        self.assertEqual(staged, set(ALLOWLIST) | {MARKER})
        self.assertNotIn("db.sqlite3", staged)
        self.assertNotIn("dcd_project/settings.py", staged)
        self.assertNotIn("optimization/models.py", staged)
        code = (
            "import importlib.util, pathlib, dcd_project.settings_render as s, "
            "optimization.mvp_views as v, optimization.tracking as t; root=pathlib.Path.cwd().resolve(); "
            "assert pathlib.Path(s.__file__).resolve().is_relative_to(root); "
            "assert pathlib.Path(v.__file__).resolve().is_relative_to(root); "
            "assert pathlib.Path(t.__file__).resolve().is_relative_to(root); "
            "assert importlib.util.find_spec('optimization.models') is None"
        )
        env = os.environ.copy()
        env.update({"SECRET_KEY": "s" * 64, "RENDER_EXTERNAL_HOSTNAME": "cargo-fit-planner.onrender.com", "CARGO_WEATHER_FREE_API_ENABLED": "true", "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1", "DJANGO_SETTINGS_MODULE": "dcd_project.settings_render"})
        child = subprocess.run([sys.executable, "-c", code], cwd=TARGET, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        flow = (
            "import dcd_project.wsgi_render; from django.test import Client; from unittest.mock import patch; from optimization.packing import DEMO_CSV; "
            "c=Client(HTTP_HOST='cargo-fit-planner.onrender.com'); "
            "h=c.get('/healthz'); assert h.status_code==200 and h.content==b'ok\\n'; "
            "p=c.post('/', {'cargo_csv':DEMO_CSV}, secure=True); assert p.status_code==200 and b'BOX-001' in p.content; "
            "csv=c.post('/export/csv/', {'cargo_csv':DEMO_CSV}, secure=True); assert csv.status_code==200 and b'BOX-001' in csv.content and 'no-store' in csv['Cache-Control']; "
            "js=c.post('/export/json/', {'cargo_csv':DEMO_CSV}, secure=True); assert js.status_code==200 and b'BOX-001' in js.content and 'no-store' in js['Cache-Control']; "
            "fixture={'status':'forecast','requested_coordinates':{'latitude':1,'longitude':2}}; "
            "weather_mock=patch('optimization.mvp_views.get_marine_forecast', return_value=fixture); weather_mock.start(); "
            "w=c.post('/weather/', {'latitude':'1','longitude':'2'}, secure=True); weather_mock.stop(); "
            "assert w.status_code==200 and w.json()==fixture and 'no-store' in w['Cache-Control']; "
            "print('health=200 pack=200 csv=200 json=200 weather=200 mocked')"
        )
        flow_result = subprocess.run([sys.executable, "-c", flow], cwd=TARGET, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(flow_result.returncode, 0, flow_result.stderr)
        self.assertIn("health=200 pack=200 csv=200 json=200 weather=200 mocked", flow_result.stdout)
        self.assertFalse((TARGET / "db.sqlite3").exists())


class ComputeRateLimitTests(SimpleTestCase):
    def setUp(self):
        cls = ComputeRateLimitMiddleware
        cls._tokens = float(cls.CAPACITY)
        cls._updated_at = __import__("time").monotonic()
        self.factory = RequestFactory()
        self.middleware = ComputeRateLimitMiddleware(lambda request: HttpResponse("accepted"))

    def test_compute_burst_is_bounded_and_retry_header_is_set(self):
        for _ in range(ComputeRateLimitMiddleware.CAPACITY):
            self.assertEqual(self.middleware(self.factory.post("/", data={"cargo_csv": "a"})).status_code, 200)
        limited = self.middleware(self.factory.post("/", data={"cargo_csv": "a"}))
        self.assertEqual(limited.status_code, 429)
        self.assertGreaterEqual(int(limited["Retry-After"]), 1)

    def test_health_get_is_exempt_and_oversized_request_is_rejected_before_compute(self):
        self.assertEqual(self.middleware(self.factory.get("/healthz")).status_code, 200)
        request = self.factory.post("/", data={"cargo_csv": "x"})
        request.META["CONTENT_LENGTH"] = str(ComputeRateLimitMiddleware.MAX_REQUEST_BYTES + 1)
        rejected = self.middleware(request)
        self.assertEqual(rejected.status_code, 413)

    def test_unknown_length_request_is_read_only_to_the_hard_body_limit(self):
        class Request:
            method = "POST"
            path = "/"
            META = {}

            def __init__(self):
                self.requested = 0

            def read(self, size):
                self.requested = size
                return b"x" * size

        request = Request()
        response = self.middleware(request)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(request.requested, ComputeRateLimitMiddleware.MAX_REQUEST_BYTES + 1)

    def test_encoded_form_expansion_limit_covers_a_256kib_csv(self):
        max_csv_bytes = 256 * 1024
        # Worst-case percent encoding expands each source byte by 3x; include
        # a small form-name/CSRF allowance in the configured raw-body cap.
        encoded_body_bound = max_csv_bytes * 3 + 2048
        self.assertLessEqual(encoded_body_bound, ComputeRateLimitMiddleware.MAX_REQUEST_BYTES)

    def test_weather_posts_share_bounded_ingress_bucket_and_body_cap(self):
        for _ in range(ComputeRateLimitMiddleware.CAPACITY):
            self.assertEqual(self.middleware(self.factory.post("/weather/", data={"latitude": "1"})).status_code, 200)
        limited = self.middleware(self.factory.post("/weather/", data={"latitude": "1"}))
        self.assertEqual(limited.status_code, 429)
        oversized = self.factory.post("/weather/", data={"latitude": "1"})
        oversized.META["CONTENT_LENGTH"] = str(ComputeRateLimitMiddleware.MAX_REQUEST_BYTES + 1)
        self.assertEqual(self.middleware(oversized).status_code, 413)
