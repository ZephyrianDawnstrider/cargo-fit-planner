"""Synthetic, database-free cargo MVP views."""

import csv
import io
import json

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .packing import CSV_TEMPLATE, DEMO_CSV, pack_items, parse_csv


MAX_CSV_BYTES = 256 * 1024


def _pack_source(source):
    if len(source.encode("utf-8")) > MAX_CSV_BYTES:
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


def index(request):
    context = {"csv_template": CSV_TEMPLATE, "demo_csv": DEMO_CSV}
    if request.method == "POST":
        source = request.POST.get("cargo_csv", "")
        try:
            items = parse_csv(source)
            if len(source.encode("utf-8")) > MAX_CSV_BYTES:
                raise ValueError("CSV is too large. Keep uploads under 256 KiB.")
            result = pack_items(items)
        except (ValueError, TypeError) as exc:
            context.update({"cargo_csv": source, "error": str(exc)})
        else:
            context.update({"cargo_csv": source, "items": items, "result": result})
    return render(request, "optimization/mvp.html", context)


@require_POST
def export_csv(request):
    try:
        result = _pack_source(request.POST.get("cargo_csv", ""))
    except (ValueError, TypeError, UnicodeError) as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    output = io.StringIO(newline="")
    fields = ["item_id", "status", "reason", "x", "y", "z", "dx", "dy", "dz", "weight_kg", "orientation"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in result.get("placed", []):
        writer.writerow(_safe_csv_row({**item, "status": "placed"}))
    for item in result.get("unplaced", []):
        writer.writerow(_safe_csv_row({**item, "status": "unplaced"}))
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cargo-packing.csv"'
    return response


@require_POST
def export_json(request):
    try:
        result = _pack_source(request.POST.get("cargo_csv", ""))
    except (ValueError, TypeError, UnicodeError) as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    response = HttpResponse(json.dumps(result, indent=2), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cargo-packing.json"'
    return response


def demo_csv(request):
    response = HttpResponse(CSV_TEMPLATE, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cargo-template.csv"'
    return response
