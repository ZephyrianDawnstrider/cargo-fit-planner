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

from .packing import CONTAINERS, CSV_TEMPLATE, DEMO_CSV, CsvValidationError, pack_items, parse_csv
from .tracking import TrackingError, get_ais_status, get_marine_forecast


MAX_CSV_BYTES = 256 * 1024
_COMPUTE_SLOT = threading.BoundedSemaphore(1)
SHIPMENT_FIELDS = {
    "shipment_reference": ("Shipment reference", 80),
    "booking_reference": ("Booking reference", 80),
    "bill_of_lading": ("Bill of lading number", 80),
    "shipper": ("Shipper", 120),
    "consignee": ("Consignee", 120),
    "origin": ("Origin", 100),
    "destination": ("Destination", 100),
}
CUSTOM_PROFILE_FIELDS = {"name", "inside_mm", "door_mm", "max_payload_kg", "dimensions_source"}
CUSTOM_DIMENSION_FIELDS = {"length", "width", "height"}


def _weight_sum(items):
    return sum((Decimal(str(item["weight_kg"])) for item in items), Decimal("0"))


def _format_kg(value):
    amount = Decimal(str(value))
    return f"{amount:.3E}" if amount.adjusted() >= 9 else f"{amount:.3f}"


def _custom_profile_data(data, container_id):
    if container_id != "custom_dry":
        return None
    raw = data.get("custom_profile_json", "")
    if not raw or len(raw) > 2048:
        raise ValueError("Enter and review all custom dry-box measurements before packing.")
    try:
        profile = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("Custom profile data is invalid. Re-enter the measurements.") from None
    if not isinstance(profile, dict) or set(profile) != CUSTOM_PROFILE_FIELDS:
        raise ValueError("Custom profile data is incomplete. Re-enter the measurements.")
    inside, door, source = profile.get("inside_mm"), profile.get("door_mm"), profile.get("dimensions_source")
    if not isinstance(inside, dict) or set(inside) != CUSTOM_DIMENSION_FIELDS:
        raise ValueError("Enter inside length, width and height for the custom dry box.")
    if not isinstance(door, dict) or set(door) != {"width", "height"}:
        raise ValueError("Enter door width and height for the custom dry box.")
    if not isinstance(source, dict) or set(source) != {"kind", "reference"}:
        raise ValueError("Identify where the custom dimensions and payload came from.")
    if not isinstance(source.get("kind"), str) or source["kind"] not in {"user_measurement", "equipment_plate", "carrier_document"}:
        raise ValueError("Choose how the custom equipment values were obtained.")
    return profile


def _pack_source(source, container_id="20std", custom_profile=None):
    if _source_too_large(source):
        raise ValueError("CSV is too large. Keep uploads under 256 KiB.")
    if container_id not in CONTAINERS and container_id != "custom_dry":
        raise ValueError("Select one of the listed container profile examples.")
    return pack_items(parse_csv(source), container_id=container_id, custom_profile=custom_profile)


def _shipment_data(data):
    shipment = {}
    for field, (label, limit) in SHIPMENT_FIELDS.items():
        value = data.get(field, "").strip()
        if len(value) > limit:
            raise ValueError(f"{label} must be at most {limit} characters.")
        if "\x00" in value:
            raise ValueError(f"{label} contains an invalid character.")
        shipment[field] = value
    return shipment


def _container_choices():
    choices = []
    for container_id, profile in CONTAINERS.items():
        inside, door = profile["inside_mm"], profile["door_mm"]
        choices.append({
            "id": container_id,
            "name": profile["name"],
            "profile": profile,
            "summary": f"Inside {inside['length']} × {inside['width']} × {inside['height']} mm · door {door['width']} × {door['height']} mm · {profile['max_payload_kg']:,} kg payload",
        })
    return choices


def _selected_profile(container_id):
    if container_id == "custom_dry":
        return {
            "id": "custom_dry", "name": "Custom measured dry closed box · unverified",
            "inside_mm": {"length": "not supplied", "width": "not supplied", "height": "not supplied"},
            "door_mm": {"width": "not supplied", "height": "not supplied"},
            "max_payload_kg": "not supplied", "source_url": None,
            "profile_notice": "Custom dry-box dimensions are unverified.",
        }
    return CONTAINERS.get(container_id, CONTAINERS["20std"])


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
        "container_choices": _container_choices(),
        "selected_container_id": "20std",
        "selected_profile": _selected_profile("20std"),
        "shipment": {field: "" for field in SHIPMENT_FIELDS},
        "shipment_fields": SHIPMENT_FIELDS,
        "custom_profile_json": "",
        "custom_selected": False,
    }
    if request.method == "POST":
        source = request.POST.get("cargo_csv", "")
        selected_container_id = request.POST.get("container_id", "20std").strip()
        context.update({"cargo_csv": source, "selected_container_id": selected_container_id,
                        "selected_profile": _selected_profile(selected_container_id)})
        custom_profile_json = request.POST.get("custom_profile_json", "")
        context["custom_profile_json"] = custom_profile_json
        context["custom_selected"] = selected_container_id == "custom_dry"
        try:
            shipment = _shipment_data(request.POST)
            custom_profile = _custom_profile_data(request.POST, selected_container_id)
            if custom_profile is not None:
                context["selected_profile"] = custom_profile
        except (AttributeError, ValueError) as exc:
            context["error"] = str(exc)
            shipment = {field: request.POST.get(field, "") for field in SHIPMENT_FIELDS}
            custom_profile = None
        context["shipment"] = shipment
        if context.get("error"):
            response = render(request, "optimization/mvp.html", context)
            response["Cache-Control"] = "no-store"
            return response
        if not _COMPUTE_SLOT.acquire(blocking=False):
            return _busy_response()
        try:
            if _source_too_large(source):
                raise ValueError("CSV is too large. Keep uploads under 256 KiB.")
            items = parse_csv(source)
            if selected_container_id not in CONTAINERS and selected_container_id != "custom_dry":
                raise ValueError("Select one of the listed container profile examples.")
            result = pack_items(items, container_id=selected_container_id, custom_profile=custom_profile)
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
                "selected_profile": result["container"],
                "shipment": shipment,
                "container_profile_notice": result["container"].get("profile_notice", ""),
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
        container_id = request.POST.get("container_id", "20std").strip()
        shipment = _shipment_data(request.POST)
        custom_profile = _custom_profile_data(request.POST, container_id)
        result = _pack_source(request.POST.get("cargo_csv", ""), container_id, custom_profile)
        output = io.StringIO(newline="")
        fields = [
            "item_id", "source_item_id", "name", "status", "reason",
            "x", "y", "z", "dx", "dy", "dz",
            "length_mm", "width_mm", "height_mm", "weight_kg", "stackable",
            "orientation", "rotation_deg", "load_unit_type", "floor_only", "is_dg",
            "un_number", "imdg_class", "packing_group", "readiness", "container_id", "container_name",
            "container_family", "container_type", "container_status", "profile_notice",
            "profile_length_mm", "profile_width_mm", "profile_height_mm", "door_width_mm",
            "door_height_mm", "payload_limit_kg", "profile_source_url", "profile_source_checked",
            "dimensions_source_kind", "dimensions_source_reference", *SHIPMENT_FIELDS.keys(),
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        profile = result["container"]
        export_profile = {
            "container_id": profile["id"], "container_name": profile["name"],
            "profile_length_mm": profile["inside_mm"]["length"],
            "profile_width_mm": profile["inside_mm"]["width"],
            "profile_height_mm": profile["inside_mm"]["height"],
            "door_width_mm": profile["door_mm"]["width"],
            "door_height_mm": profile["door_mm"]["height"],
            "payload_limit_kg": profile["max_payload_kg"],
            "profile_source_url": profile["source_url"],
            "profile_source_checked": profile["source_checked"],
            "container_family": profile.get("family", "freight_container"),
            "container_type": profile.get("type", "dry_closed_container"),
            "container_status": profile.get("status", "published_example"),
            "profile_notice": profile.get("profile_notice", ""),
            "dimensions_source_kind": profile.get("dimensions_source", {}).get("kind", ""),
            "dimensions_source_reference": profile.get("dimensions_source", {}).get("reference", ""),
        }
        for status in ("placed", "unplaced"):
            for item in result.get(status, []):
                writer.writerow(_safe_csv_row({**item, "status": status,
                                               "readiness": result.get("readiness", "packing_preview_only"),
                                               **export_profile, **shipment}))
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
        container_id = request.POST.get("container_id", "20std").strip()
        shipment = _shipment_data(request.POST)
        custom_profile = _custom_profile_data(request.POST, container_id)
        result = _pack_source(request.POST.get("cargo_csv", ""), container_id, custom_profile)
        result["shipment"] = shipment
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
