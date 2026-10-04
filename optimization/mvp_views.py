"""Synthetic, database-free cargo MVP views."""

import csv
import io
import json
import threading
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .packing import CSV_TEMPLATE, DEMO_CSV, CsvValidationError, pack_items, parse_csv
from .tracking import TrackingError, get_ais_status, get_marine_forecast


MAX_CSV_BYTES = 256 * 1024
_COMPUTE_SLOT = threading.BoundedSemaphore(1)


def _weight_sum(items):
    return sum((Decimal(str(item["weight_kg"])) for item in items), Decimal("0"))


def _format_kg(value):
    amount = Decimal(str(value))
    return f"{amount:.3E}" if amount.adjusted() >= 9 else f"{amount:.3f}"


def _pack_source(source):
    if _source_too_large(source):
        raise ValueError("CSV is too large. Keep uploads under 256 KiB.")
    return pack_items(parse_csv(source))


def _safe_csv_row(row):
    """Prefix text beginning with spreadsheet formula sigils before export."""
    safe = {}
    for key, value in row.items():
        if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
            value = "'" + value
        safe[key] = value
    return safe


@require_http_methods(["GET", "POST"])
@never_cache
def index(request):
    context = {
        "csv_template": CSV_TEMPLATE,
        "demo_csv": DEMO_CSV,
        "weather_enabled": getattr(settings, "WEATHER_FREE_API_ENABLED", False),
        "ais_status": get_ais_status(),
    }
    if request.method == "POST":
        if not _COMPUTE_SLOT.acquire(blocking=False):
            return _busy_response()
        try:
            source = request.POST.get("cargo_csv", "")
            if _source_too_large(source):
                raise ValueError("CSV is too large. Keep uploads under 256 KiB.")
            items = parse_csv(source)
            result = pack_items(items)
        except CsvValidationError as exc:
            context.update({
                "cargo_csv": source,
                "validation_errors": exc.errors,
                "validation_errors_truncated": exc.truncated,
            })
        except (ValueError, TypeError) as exc:
            context.update({"cargo_csv": source, "error": str(exc)})
        else:
            inside = result["container"]["inside_mm"]
            container_volume = inside["length"] * inside["width"] * inside["height"] / 1_000_000_000
            context.update({
                "cargo_csv": source,
                "items": items,
                "result": result,
                "placed_rows": [{**item, "weight_display": _format_kg(item["weight_kg"])} for item in result["placed"]],
                "unplaced_rows": [{**item, "weight_display": _format_kg(item["weight_kg"])} for item in result["unplaced"]],
                "source_row_count": len({item["source_item_id"] for item in items}),
                "input_weight_display": _format_kg(_weight_sum(items)),
                "placed_weight_display": _format_kg(result["totals"]["placed_weight_kg"]),
                "remaining_weight_display": _format_kg(_weight_sum(result["unplaced"])),
                "payload_utilization_pct": result["totals"]["placed_weight_kg"] / result["container"]["max_payload_kg"] * 100,
                "volume_utilization_pct": result["totals"]["placed_volume_m3"] / container_volume * 100,
            })
        finally:
            _COMPUTE_SLOT.release()
    response = render(request, "optimization/mvp.html", context)
    if request.method == "POST":
        response["Cache-Control"] = "no-store"
    return response


@require_POST
@never_cache
def export_csv(request):
    if not _COMPUTE_SLOT.acquire(blocking=False):
        return _busy_response()
    try:
        result = _pack_source(request.POST.get("cargo_csv", ""))
        output = io.StringIO(newline="")
        fields = [
            "item_id", "source_item_id", "name", "status", "reason",
            "x", "y", "z", "dx", "dy", "dz",
            "length_mm", "width_mm", "height_mm", "weight_kg", "stackable",
            "orientation", "rotation_deg",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in result.get("placed", []):
            writer.writerow(_safe_csv_row({**item, "status": "placed"}))
        for item in result.get("unplaced", []):
            writer.writerow(_safe_csv_row({**item, "status": "unplaced"}))
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="cargo-packing.csv"'
        return response
    except (ValueError, TypeError, UnicodeError) as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    finally:
        _COMPUTE_SLOT.release()


@require_POST
@never_cache
def export_json(request):
    if not _COMPUTE_SLOT.acquire(blocking=False):
        return _busy_response()
    try:
        result = _pack_source(request.POST.get("cargo_csv", ""))
        response = HttpResponse(json.dumps(result, indent=2), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="cargo-packing.json"'
        return response
    except (ValueError, TypeError, UnicodeError) as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    finally:
        _COMPUTE_SLOT.release()


def _source_too_large(source):
    try:
        return len(source.encode("utf-8")) > MAX_CSV_BYTES
    except UnicodeEncodeError:
        return False  # parse_csv returns the safe structured Unicode validation error.


def _busy_response():
    response = HttpResponse("A packing request is already being processed. Retry shortly.", status=503, content_type="text/plain; charset=utf-8")
    response["Retry-After"] = "2"
    return response


@require_GET
def demo_csv(request):
    response = HttpResponse(CSV_TEMPLATE, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cargo-template.csv"'
    return response


@require_GET
def healthz(request):
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")


@require_POST
@never_cache
def marine_forecast(request):
    from django.http import JsonResponse

    if not getattr(settings, "WEATHER_FREE_API_ENABLED", False):
        response = JsonResponse({"error": {"code": "weather_disabled", "message": "The educational marine forecast is not enabled on this deployment."}}, status=503)
    else:
        try:
            latitude = request.POST.get("latitude", "")
            longitude = request.POST.get("longitude", "")
            result = get_marine_forecast(latitude, longitude)
        except TrackingError as exc:
            response = JsonResponse({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)
        else:
            response = JsonResponse(result)
    response["Cache-Control"] = "no-store"
    return response
