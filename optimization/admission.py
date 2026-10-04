"""Process-local rate gate placed before CSRF and form parsing in production."""

import math
from io import BytesIO
import threading
import time

from django.http import HttpResponse


class ComputeRateLimitMiddleware:
    """Allow a small burst, then at most one bounded POST per 10 seconds.

    State is process-local and intentionally independent of client-supplied IPs,
    cookies, and forwarded headers. Render runs this MVP with one instance.
    """

    CAPACITY = 4
    REFILL_SECONDS = 10.0
    # Maximal percent-encoding can triple each decoded UTF-8 byte; 800 KiB
    # leaves room for a parser-valid 256 KiB CSV plus form fields/boundaries.
    MAX_REQUEST_BYTES = 800 * 1024
    PATHS = {"/", "/export/csv/", "/export/json/", "/weather/"}

    _lock = threading.Lock()
    _tokens = float(CAPACITY)
    _updated_at = time.monotonic()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path in self.PATHS:
            raw_length = request.META.get("CONTENT_LENGTH", "")
            if raw_length:
                try:
                    if int(raw_length) > self.MAX_REQUEST_BYTES:
                        return HttpResponse("Request body exceeds the 800 KiB limit.", status=413, content_type="text/plain; charset=utf-8")
                except ValueError:
                    return HttpResponse("Invalid request body length.", status=400, content_type="text/plain; charset=utf-8")
            now = time.monotonic()
            with self._lock:
                elapsed = max(0.0, now - type(self)._updated_at)
                type(self)._tokens = min(
                    self.CAPACITY,
                    type(self)._tokens + elapsed / self.REFILL_SECONDS,
                )
                type(self)._updated_at = now
                if type(self)._tokens < 1:
                    wait = (1 - type(self)._tokens) * self.REFILL_SECONDS
                    response = HttpResponse("Compute request rate limit reached. Retry later.", status=429, content_type="text/plain; charset=utf-8")
                    response["Retry-After"] = str(max(1, math.ceil(wait)))
                    return response
                type(self)._tokens -= 1
            # Bound even requests without Content-Length before CSRF/form parsing.
            # Cache the bounded bytes so downstream Django parsing sees them.
            body = request.read(self.MAX_REQUEST_BYTES + 1)
            if len(body) > self.MAX_REQUEST_BYTES:
                return HttpResponse("Request body exceeds the 800 KiB limit.", status=413, content_type="text/plain; charset=utf-8")
            request._body = body
            request._stream = BytesIO(body)
        return self.get_response(request)
