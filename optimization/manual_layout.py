"""All-or-nothing validation of manual edits to a server-generated packing result.

The caller MUST regenerate ``packing_result`` from the submitted source manifest
and equipment on the server. A client-supplied result is not authoritative: this
module cannot establish the truth of cargo weights or equipment specifications.

Only already-placed units can move. This deliberately cannot introduce dangerous
or unplaced cargo, remove units, resize cargo, or change weight/handling flags.
Checks are static rectangular geometry, not collision-free loading paths,
strength, stability, axle/floor loads, securing, or operational approval.
"""
from copy import deepcopy
import math
from typing import Any

from .packing import MAX_ITEMS, _mass_distribution, _overlap, _validate_items, _stacking_violation, _annotate_supported_loads


class ManualLayoutError(ValueError):
    """A recoverable validation rejection; the original layout is unchanged."""

    def __init__(self, code: str, message: str, item_ids=()):
        super().__init__(message)
        self.code = code
        self.item_ids = list(item_ids)


def _reject(code, message, *ids):
    raise ManualLayoutError(code, message, ids)


def _container_limits(container):
    try:
        inner, door = container['inside_mm'], container['door_mm']
        dimensions = [inner[k] for k in ('length', 'width', 'height')]
        doorway = [door[k] for k in ('width', 'height')]
        for number in dimensions + doorway:
            if (isinstance(number, bool) or not isinstance(number, (int, float))
                    or not math.isfinite(number) or not 1 <= number <= 100_000
                    or int(number) != number):
                raise ValueError
        payload = container['max_payload_kg']
        if (isinstance(payload, bool) or not isinstance(payload, (int, float))
                or not math.isfinite(payload) or not 0 < payload <= 1_000_000
                or round(payload, 3) != payload):
            raise ValueError
        if door['width'] > inner['width'] or door['height'] > inner['height']:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        _reject('invalid_source', 'The source equipment profile is invalid. Repack the manifest first.')
    return inner, door, int(round(payload * 1000))


def validate_manual_layout(packing_result: dict[str, Any], placements: list[dict[str, Any]], *,
                           source_items=None) -> dict[str, Any]:
    """Return a deep-copied valid result or raise ``ManualLayoutError``.

    ``placements`` must exactly cover the existing placed IDs, once each. Each
    entry has exactly ``item_id, x, y, z, rotation_deg``. Coordinates are JSON
    integer millimetres (not booleans/strings/floats); yaw is 0 or 90 degrees.

    Pass the authoritative output of ``parse_csv`` as ``source_items`` to retain
    original fixed/yaw permissions: the packer result records chosen orientation,
    overwriting the original permission. Without source_items the result's fixed
    orientation is conservatively treated as fixed-only. No inputs are mutated.
    """
    if not isinstance(packing_result, dict):
        _reject('invalid_source', 'A server-generated packing result is required.')
    original_placed, unplaced = packing_result.get('placed'), packing_result.get('unplaced')
    if not isinstance(original_placed, list) or not isinstance(unplaced, list):
        _reject('invalid_source', 'The source cargo lists are invalid. Repack the manifest first.')
    try:
        baseline = _validate_items(original_placed + unplaced)
        source = _validate_items(source_items) if source_items is not None else baseline
    except (ValueError, TypeError) as exc:
        _reject('invalid_source', f'Invalid source cargo: {exc}')
    original_by_id = {p['item_id']: p for p in baseline}
    source_by_id = {p['item_id']: p for p in source}
    if set(source_by_id) != set(original_by_id):
        _reject('invalid_source', 'Source cargo IDs do not match the packing result. Repack first.')
    # Except chosen orientation, source metadata/rules must match the base result.
    for ident, original in original_by_id.items():
        expected = source_by_id[ident]
        if any(value != expected.get(key) for key, value in original.items() if key != 'orientation'):
            _reject('invalid_source', 'Source cargo changed. Repack before editing the layout.', ident)
    inner, door, max_grams = _container_limits(packing_result.get('container', {}))
    if not isinstance(placements, list) or len(placements) > MAX_ITEMS:
        _reject('invalid_edits', f'Placements must be a list of at most {MAX_ITEMS} entries.')
    placed_ids = {p['item_id'] for p in original_placed}
    if len(placements) != len(placed_ids):
        _reject('id_mismatch', 'Manual edits must include every placed cargo unit exactly once.')
    edits, seen = {}, set()
    required = {'item_id', 'x', 'y', 'z', 'rotation_deg'}
    for edit in placements:
        if not isinstance(edit, dict) or set(edit) != required:
            _reject('invalid_edits', 'Each edit needs exactly item_id, x, y, z and rotation_deg.')
        ident = edit['item_id']
        if not isinstance(ident, str) or ident not in placed_ids or ident in seen:
            _reject('id_mismatch', 'Unknown, duplicate or unplaced cargo ID in manual edits.')
        seen.add(ident)
        for axis in ('x', 'y', 'z'):
            if type(edit[axis]) is not int or not 0 <= edit[axis] <= 100_000:
                _reject('invalid_coordinate', 'Coordinates must be nonnegative integer millimetres, at most 100000.', ident)
        if type(edit['rotation_deg']) is not int or edit['rotation_deg'] not in (0, 90):
            _reject('invalid_rotation', 'Only upright 0 or 90 degree yaw is supported.', ident)
        edits[ident] = edit
    if seen != placed_ids:
        _reject('id_mismatch', 'Manual edits must include every placed cargo unit exactly once.')
    moved = []
    grams = 0
    for old in original_placed:
        ident = old['item_id']
        rules, edit = source_by_id[ident], edits[ident]
        if rules['is_dg']:
            _reject('manual_compliance_hold', 'Dangerous-goods cargo cannot be manually placed.', ident)
        rotate = edit['rotation_deg']
        if rotate == 90 and rules['orientation'] != 'yaw':
            _reject('orientation_not_allowed', 'This unit must retain its fixed orientation.', ident)
        dx, dy = rules['length_mm'], rules['width_mm']
        if rotate == 90:
            dx, dy = dy, dx
        dz = rules['height_mm']
        if dy > door['width'] or dz > door['height']:
            _reject('door_clearance', 'The chosen upright orientation exceeds the doorway.', ident)
        if edit['x'] + dx > inner['length'] or edit['y'] + dy > inner['width'] or edit['z'] + dz > inner['height']:
            _reject('container_bounds', 'The cargo extends outside the container.', ident)
        if rules['floor_only'] and edit['z'] != 0:
            _reject('floor_only', 'This cargo unit must remain on the floor.', ident)
        if rules['weight_kg'] > max_grams / 1000:
            _reject('payload_limit', 'The cargo exceeds the equipment payload limit.', ident)
        grams += int(round(rules['weight_kg'] * 1000))
        if grams > max_grams:
            _reject('payload_limit', 'The total placed weight exceeds the equipment payload limit.')
        moved.append({**deepcopy(old), **edit, 'dx': dx, 'dy': dy, 'dz': dz,
                      'orientation': 'yaw' if rotate else 'fixed'})
    for index, cargo in enumerate(moved):
        for other in moved[index + 1:]:
            if _overlap(cargo, other):
                _reject('overlap', 'Cargo units overlap. Touching faces are allowed, intersections are not.',
                        cargo['item_id'], other['item_id'])
    violation = _stacking_violation(moved)
    if violation:
        code, message, ids = violation
        _reject(code, message, *ids)
    _annotate_supported_loads(moved)
    volume_mm3 = sum(int(p['dx']) * int(p['dy']) * int(p['dz']) for p in moved)
    if volume_mm3 > inner['length'] * inner['width'] * inner['height']:
        _reject('volume_limit', 'Placed cargo volume exceeds the container volume.')
    result = deepcopy(packing_result)
    result['placed'] = moved
    hold_count = sum(p.get('is_dg', False) for p in unplaced)
    result['readiness'] = 'manual_compliance_hold' if hold_count else 'packing_preview_only'
    result['totals'] = {**result.get('totals', {}), 'input_count': len(baseline),
                        'placed_count': len(moved), 'unplaced_count': len(unplaced),
                        'manual_compliance_hold_count': hold_count,
                        'placed_weight_kg': grams / 1000, 'placed_volume_m3': volume_mm3 / 1_000_000_000}
    result['mass_distribution'] = _mass_distribution(moved, result['container'])
    result['manual_layout'] = {
        'status': 'validated_geometry_preview',
        'notice': 'Manual layout passes static bounds, doorway, non-overlap, payload and single-unit full-footprint support checks only. No load-strength, dynamic stability, axle/floor load, securing or collision-free loading-path approval is provided.',
    }
    return result
