"""Deterministic, conservative MVP for packing cargo into one 20 ft container.

The profile is the Hapag-Lloyd 20' standard example published at
https://www.hapag-lloyd.com/en/services-information/cargo-fleet/container/20-standard.html
(checked 2026-10-03). Values are an example, not universal container limits.

This is a deterministic feasibility heuristic, not an optimizer. Inputs use
whole millimetres and weights in 0.001 kg increments. It models
rectangular cargo, straight-through door clearance, container containment,
non-overlap, payload, and conservative single-item full-footprint support.
It does not model load strength, lashing, axle/floor point loads, loading
sequence/access after placement, or cargo-specific handling constraints.
"""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Any, Iterable


CSV_TEMPLATE = """item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation
"""

DEMO_CSV = """item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation
BOX,Sample box,600,400,350,18,4,true,yaw
CRATE,Heavy crate,900,700,800,220,1,false,fixed
"""

CSV_HEADERS = (
    "item_id", "name", "length_mm", "width_mm", "height_mm", "weight_kg",
    "quantity", "stackable", "orientation",
)
MAX_CSV_BYTES = 1_000_000
MAX_ROWS = 100
MAX_UNITS = 100
MAX_ITEMS = 100
MAX_CSV_ERRORS = 20
MAX_ITEM_ID_CHARS = 64
MAX_ITEM_NAME_CHARS = 120
MAX_CANDIDATE_CHECKS_PER_PACK = 100_000
MAX_CANDIDATE_CHECKS_PER_ORIENTATION = 2_000

CONTAINER = {
    "name": "20 ft standard (Hapag-Lloyd example)",
    "source_url": "https://www.hapag-lloyd.com/en/services-information/cargo-fleet/container/20-standard.html",
    "source_checked": "2026-10-03",
    "inside_mm": {"length": 5900, "width": 2352, "height": 2395},
    "door_mm": {"width": 2340, "height": 2292},
    "max_payload_kg": 28130,
}


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


class CsvValidationError(ValueError):
    """All-or-nothing manifest validation details for forms and API callers."""

    def __init__(self, errors: list[dict[str, Any]], *, truncated: bool = False):
        self.errors = errors[:MAX_CSV_ERRORS]
        self.truncated = truncated or len(errors) > MAX_CSV_ERRORS
        summary = "; ".join(
            (f"row {error['row']} " if error["row"] is not None else "")
            + f"{error['field']}: {error['message']}"
            for error in self.errors[:3]
        )
        omitted = " (further errors omitted)" if self.truncated else ""
        super().__init__(f"CSV validation found {len(self.errors)} error(s): {summary}{omitted}")


def _parse_flag(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise ValueError("must be true/false, yes/no, or 1/0")


def parse_csv(text: str) -> list[dict[str, Any]]:
    """Validate the documented CSV and expand quantities to individual units."""
    if not isinstance(text, str):
        raise CsvValidationError([{"row": None, "field": "csv", "message": "input must be text"}])
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise CsvValidationError([{"row": None, "field": "csv", "message": "input contains invalid Unicode"}]) from None
    if encoded_size > MAX_CSV_BYTES:
        raise CsvValidationError([{"row": None, "field": "csv", "message": f"exceeds the {MAX_CSV_BYTES}-byte input limit"}])
    errors: list[dict[str, Any]] = []
    truncated = False

    def add_error(row: int | None, field: str, message: str) -> None:
        nonlocal truncated
        if len(errors) < MAX_CSV_ERRORS:
            errors.append({"row": row, "field": field, "message": message})
        else:
            truncated = True

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if headers is None:
            add_error(None, "header", "a header row is required")
            raise CsvValidationError(errors)
        if headers and headers[0].startswith("\ufeff"):
            headers[0] = headers[0].lstrip("\ufeff")
            reader.fieldnames = headers
        seen_headers: set[str] = set()
        for header in headers:
            if header in seen_headers:
                add_error(None, header or "header", f"duplicate column {header!r}")
            seen_headers.add(header)
        missing = [header for header in CSV_HEADERS if header not in headers]
        extra = [header for header in headers if header not in CSV_HEADERS]
        for header in missing:
            add_error(None, header, "required column is missing")
        for header in extra:
            add_error(None, header, "unexpected column")
        if errors:
            raise CsvValidationError(errors, truncated=truncated)
        expanded: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        source_rows = 0
        for row in reader:
            source_rows += 1
            if source_rows > MAX_ROWS:
                add_error(reader.line_num, "rows", f"exceeds the {MAX_ROWS}-row limit")
                break
            row_number = reader.line_num or None
            if None in row:
                add_error(row_number, "columns", "too many columns")
            source_id = (row.get("item_id") or "").strip()
            name = (row.get("name") or "").strip()
            if not source_id:
                add_error(row_number, "item_id", "required value is blank")
            elif len(source_id) > MAX_ITEM_ID_CHARS:
                add_error(row_number, "item_id", f"must be at most {MAX_ITEM_ID_CHARS} characters")
            elif source_id in seen_ids:
                add_error(row_number, "item_id", f"duplicate value {source_id!r}")
            else:
                seen_ids.add(source_id)
            if not name:
                add_error(row_number, "name", "required value is blank")
            elif len(name) > MAX_ITEM_NAME_CHARS:
                add_error(row_number, "name", f"must be at most {MAX_ITEM_NAME_CHARS} characters")
            for field in CSV_HEADERS[2:]:
                if field not in row or row[field] is None or not row[field].strip():
                    add_error(row_number, field, "required value is blank")
            dimensions = {}
            for field in ("length_mm", "width_mm", "height_mm"):
                raw = row.get(field) or ""
                if raw.strip():
                    try:
                        value = _finite_number(raw.strip(), field)
                        if value < 1 or not value.is_integer():
                            raise ValueError("must be a whole number of millimetres (at least 1)")
                        dimensions[field] = value
                    except ValueError as exc:
                        add_error(row_number, field, str(exc))
            weight = None
            try:
                weight = _finite_number(row.get("weight_kg") or "", "weight_kg")
                if weight < 0:
                    raise ValueError("cannot be negative")
                if weight != round(weight, 3):
                    raise ValueError("must use increments of 0.001 kg")
            except ValueError as exc:
                if row.get("weight_kg") and row["weight_kg"].strip():
                    add_error(row_number, "weight_kg", str(exc))
                weight = None
            quantity = None
            raw_quantity = row.get("quantity") or ""
            if raw_quantity.strip():
                quantity_text = raw_quantity.strip()
                if not re.fullmatch(r"[0-9]+", quantity_text):
                    add_error(row_number, "quantity", "must be a positive integer")
                else:
                    quantity_text = quantity_text.lstrip("0") or "0"
                    if len(quantity_text) > len(str(MAX_UNITS)):
                        add_error(row_number, "quantity", f"expanded manifest exceeds the {MAX_UNITS}-unit limit")
                    else:
                        quantity = int(quantity_text)
                        if quantity <= 0:
                            add_error(row_number, "quantity", "must be a positive integer")
                        elif len(expanded) + quantity > MAX_UNITS:
                            add_error(row_number, "quantity", f"expanded manifest exceeds the {MAX_UNITS}-unit limit")
                            quantity = None
            stackable = None
            if row.get("stackable") and row["stackable"].strip():
                try:
                    stackable = _parse_flag(row["stackable"])
                except ValueError as exc:
                    add_error(row_number, "stackable", str(exc))
            orientation = (row.get("orientation") or "").strip().lower()
            if orientation and orientation not in {"fixed", "yaw"}:
                add_error(row_number, "orientation", "must be fixed or yaw")
            valid = bool(source_id and name and dimensions.keys() >= {"length_mm", "width_mm", "height_mm"}
                         and weight is not None and quantity and stackable is not None
                         and orientation in {"fixed", "yaw"})
            if not valid:
                continue
            for unit_index in range(1, quantity + 1):
                expanded.append({
                    "item_id": f"{source_id}-{unit_index:03d}",
                    "source_item_id": source_id,
                    "name": name,
                    **dimensions,
                    "weight_kg": weight,
                    "stackable": stackable,
                    "orientation": orientation,
                })
        if truncated or errors:
            raise CsvValidationError(errors, truncated=truncated)
        if not expanded:
            raise CsvValidationError([{"row": None, "field": "rows", "message": "at least one cargo item is required"}])
        return expanded
    except csv.Error as exc:
        add_error(reader.line_num or None, "csv", f"invalid CSV syntax: {exc}")
        raise CsvValidationError(errors, truncated=truncated) from exc


def _validate_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(items, (str, bytes, dict)):
        raise ValueError("items must be an iterable of item objects")
    try:
        result = list(items)
    except TypeError as exc:
        raise ValueError("items must be an iterable of item objects") from exc
    if len(result) > MAX_ITEMS:
        raise ValueError(f"items exceeds the {MAX_ITEMS}-unit limit")
    if not result:
        raise ValueError("at least one cargo item is required")
    ids: set[str] = set()
    normalized = []
    required = ("item_id", "name", "length_mm", "width_mm", "height_mm", "weight_kg", "stackable", "orientation")
    for index, item in enumerate(result, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index}: expected an object")
        missing = [key for key in required if key not in item]
        if missing:
            raise ValueError(f"item {index}: missing {', '.join(missing)}")
        item_id, name = str(item["item_id"]).strip(), str(item["name"]).strip()
        if not item_id or not name:
            raise ValueError(f"item {index}: item_id and name are required")
        if item_id in ids:
            raise ValueError(f"duplicate item_id {item_id!r}")
        ids.add(item_id)
        data: dict[str, Any] = {"item_id": item_id, "name": name}
        for field in ("length_mm", "width_mm", "height_mm"):
            number = _finite_number(item[field], f"item {item_id} {field}")
            if number < 1 or not number.is_integer():
                raise ValueError(f"item {item_id}: {field} must be a whole number of millimetres (at least 1)")
            data[field] = number
        weight = _finite_number(item["weight_kg"], f"item {item_id} weight_kg")
        if weight < 0:
            raise ValueError(f"item {item_id}: weight_kg cannot be negative")
        if weight != round(weight, 3):
            raise ValueError(f"item {item_id}: weight_kg must use increments of 0.001 kg")
        if not isinstance(item["stackable"], bool):
            raise ValueError(f"item {item_id}: stackable must be boolean")
        orientation = item["orientation"]
        if not isinstance(orientation, str):
            raise ValueError(f"item {item_id}: orientation must be fixed or yaw")
        if orientation not in {"fixed", "yaw"}:
            raise ValueError(f"item {item_id}: orientation must be fixed or yaw")
        data.update(weight_kg=weight, stackable=item["stackable"], orientation=orientation)
        if "source_item_id" in item:
            data["source_item_id"] = str(item["source_item_id"])
        normalized.append(data)
    return normalized


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a["x"] < b["x"] + b["dx"] and b["x"] < a["x"] + a["dx"]
        and a["y"] < b["y"] + b["dy"] and b["y"] < a["y"] + a["dy"]
        and a["z"] < b["z"] + b["dz"] and b["z"] < a["z"] + a["dz"]
    )


def _orientations(item: dict[str, Any]) -> list[tuple[float, float, str]]:
    fixed = (item["length_mm"], item["width_mm"], "fixed")
    if item["orientation"] == "yaw" and item["length_mm"] != item["width_mm"]:
        return [fixed, (item["width_mm"], item["length_mm"], "yaw")]
    return [fixed]


def _fits_door_and_container(item: dict[str, Any]) -> bool:
    return any(
        orientation[1] <= CONTAINER["door_mm"]["width"]
        and item["height_mm"] <= CONTAINER["door_mm"]["height"]
        and orientation[0] <= CONTAINER["inside_mm"]["length"]
        and orientation[1] <= CONTAINER["inside_mm"]["width"]
        and item["height_mm"] <= CONTAINER["inside_mm"]["height"]
        for orientation in _orientations(item)
    )


def _candidate(item: dict[str, Any], placed: list[dict[str, Any]], budget: list[int]) -> tuple[dict[str, Any] | None, bool]:
    inner = CONTAINER["inside_mm"]
    door = CONTAINER["door_mm"]
    for dx, dy, direction in _orientations(item):
        examined = 0
        dz = item["height_mm"]
        # Every cargo orientation travels upright and straight through the door.
        if dy > door["width"] or dz > door["height"]:
            continue
        if dx > inner["length"] or dy > inner["width"] or dz > inner["height"]:
            continue
        supports = [None] + [p for p in placed if p["stackable"]]
        for support in supports:
            z = 0.0 if support is None else support["z"] + support["dz"]
            if z + dz > inner["height"]:
                continue
            if support is not None and not (
                support["x"] <= support["x"] + support["dx"] - dx
                and support["y"] <= support["y"] + support["dy"] - dy
            ):
                continue
            xs = {0.0}
            ys = {0.0}
            for p in placed:
                xs.add(p["x"] + p["dx"])
                ys.add(p["y"] + p["dy"])
            if support is not None:
                xs.add(support["x"])
                ys.add(support["y"])
            for x in sorted(xs):
                for y in sorted(ys):
                    if budget[0] <= 0:
                        return None, True
                    budget[0] -= 1
                    examined += 1
                    if examined > MAX_CANDIDATE_CHECKS_PER_ORIENTATION:
                        return None, False
                    if x + dx > inner["length"] or y + dy > inner["width"]:
                        continue
                    if support is not None and not (
                        support["x"] <= x and x + dx <= support["x"] + support["dx"]
                        and support["y"] <= y and y + dy <= support["y"] + support["dy"]
                    ):
                        continue
                    position = {"x": x, "y": y, "z": z, "dx": dx, "dy": dy, "dz": dz}
                    if any(_overlap(position, p) for p in placed):
                        continue
                    return {**position, "orientation": direction}, False
    return None, False


def pack_items(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pack as many units as a stable greedy heuristic can feasibly place."""
    normalized = _validate_items(items)
    normalized.sort(key=lambda item: (
        -(item["length_mm"] * item["width_mm"] * item["height_mm"]),
        -item["weight_kg"], item["item_id"],
    ))
    placed: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    payload_grams = 0
    candidate_budget = [MAX_CANDIDATE_CHECKS_PER_PACK]
    search_exhausted = False
    for item in normalized:
        # Reject an overweight item before converting kg to integer grams;
        # very large but finite values can overflow Python's float-to-int path.
        if item["weight_kg"] > CONTAINER["max_payload_kg"]:
            unplaced.append({**item, "reason": "payload_limit"})
            continue
        item_grams = int(round(item["weight_kg"] * 1000))
        if payload_grams + item_grams > CONTAINER["max_payload_kg"] * 1000:
            unplaced.append({**item, "reason": "payload_limit"})
            continue
        if not _fits_door_and_container(item):
            unplaced.append({**item, "reason": "door_or_container_dimensions"})
            continue
        if search_exhausted:
            unplaced.append({**item, "reason": "search_budget_exhausted"})
            continue
        position, budget_exhausted = _candidate(item, placed, candidate_budget)
        if budget_exhausted:
            search_exhausted = True
            unplaced.append({**item, "reason": "search_budget_exhausted"})
            continue
        if position is None:
            unplaced.append({**item, "reason": "no_feasible_space_found_by_heuristic"})
            continue
        placed.append({**item, **position, "rotation_deg": 90 if position["orientation"] == "yaw" else 0})
        payload_grams += item_grams
    total_volume = sum(p["dx"] * p["dy"] * p["dz"] for p in placed) / 1_000_000_000
    return {
        "container": {**CONTAINER, "inside_mm": dict(CONTAINER["inside_mm"]), "door_mm": dict(CONTAINER["door_mm"])},
        "placed": placed,
        "unplaced": unplaced,
        "totals": {
            "input_count": len(normalized),
            "placed_count": len(placed),
            "unplaced_count": len(unplaced),
            "placed_weight_kg": payload_grams / 1000,
            "placed_volume_m3": total_volume,
        },
    }
