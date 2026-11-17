"""Customer reservation planning, not a transport or load-strength approval.

Call only with authoritative source items/equipment. Manual edits must first pass
manual_layout.validate_manual_layout, then validate_allocation. Nonzero envelope
allowances are deliberately unsupported until their export semantics are defined.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from .packing import (_validate_items, _resolve_container, _custom_container,
                      _mass_distribution, pack_items)

_AXES = {'x': 'length', 'y': 'width', 'z': 'height'}
NOTICE = ('Customer caps reserve shares of whole-equipment payload and internal volume; '
          'unused shares are not transferred. Largest-volume-first quota selection happens before geometric packing; failed selections are not backfilled, so this does not maximize utilization. Region reservations are geometric only. '
          'Elevated Z regions are held because no supporting structure is modeled. '
          'No strength, axle, stability, loading-path or transport approval is provided.')


def _percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('quota percentages must be finite numbers from 0 to 100')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('invalid quota percentage') from None
    if not number.is_finite() or not 0 <= number <= 100:
        raise ValueError('quota percentages must be finite numbers from 0 to 100')
    return number


def _config(config, items, container):
    if not isinstance(config, dict) or set(config) - {'customers', 'dimension_tolerance_mm', 'wall_clearance_mm'}:
        raise ValueError('invalid allocation config fields')
    for key in ('dimension_tolerance_mm', 'wall_clearance_mm'):
        value = config.get(key, 0)
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f'{key} must be an integer from 0 to 100')
        if value:
            raise ValueError(f'{key} is not yet supported; use 0 (original gross dimensions)')
    customers = config.get('customers')
    if not isinstance(customers, list) or not 1 <= len(customers) <= 8:
        raise ValueError('customers must contain 1 to 8 reservations')
    source_ids = {i.get('source_item_id') for i in items}
    if any(not isinstance(s, str) or not s for s in source_ids):
        raise ValueError('allocation requires parsed source_item_id on every unit')
    assigned, ids, normalized = set(), set(), []
    sums = {'weight_percent': Decimal(0), 'volume_percent': Decimal(0)}
    for customer in customers:
        if not isinstance(customer, dict) or set(customer) != {'id', 'source_item_ids', 'weight_percent', 'volume_percent', 'region'}:
            raise ValueError('customer requires id, source_item_ids, weight_percent, volume_percent and region')
        ident = customer['id']
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 64 or ident in ids:
            raise ValueError('customer id must be unique nonblank text up to 64 characters')
        ids.add(ident)
        sources = customer['source_item_ids']
        if (not isinstance(sources, list) or not 1 <= len(sources) <= 100
                or any(not isinstance(s, str) for s in sources)
                or len(set(sources)) != len(sources) or set(sources) - source_ids or assigned.intersection(sources)):
            raise ValueError('source_item_ids must be known, unique and assigned to exactly one customer')
        assigned.update(sources)
        for key in sums:
            sums[key] += _percent(customer[key])
        region = customer['region']
        bounds = {axis: [0, container['inside_mm'][dim]] for axis, dim in _AXES.items()}
        if region is not None:
            if (not isinstance(region, dict) or set(region) != {'axis', 'parts', 'index'}
                    or not isinstance(region['axis'], str) or region['axis'] not in _AXES
                    or type(region['parts']) is not int or region['parts'] not in (2, 3, 4)
                    or type(region['index']) is not int or not 0 <= region['index'] < region['parts']):
                raise ValueError('region requires axis x/y/z, parts 2/3/4 and zero-based index')
            axis, parts, index = region['axis'], region['parts'], region['index']
            size = bounds[axis][1]
            bounds[axis] = [size * index // parts, size * (index + 1) // parts]
            if bounds[axis][0] == bounds[axis][1]:
                raise ValueError('region has no whole-millimetre space')
        normalized.append({**deepcopy(customer), 'bounds_mm': bounds})
    if assigned != source_ids:
        raise ValueError('every source item must be assigned to a customer')
    if any(v > 100 for v in sums.values()):
        raise ValueError('customer quota percentages must sum to at most 100')
    reserved = [c for c in normalized if c['region'] is not None]
    if reserved and len(reserved) != len(normalized):
        raise ValueError('cannot mix shared-space and explicit region reservations')
    for i, a in enumerate(reserved):
        for b in reserved[i + 1:]:
            if all(max(a['bounds_mm'][k][0], b['bounds_mm'][k][0]) < min(a['bounds_mm'][k][1], b['bounds_mm'][k][1]) for k in _AXES):
                raise ValueError('customer regions must not overlap')
    return normalized


def _caps(customer, container):
    size = container['inside_mm']
    volume = size['length'] * size['width'] * size['height']
    grams = int(round(container['max_payload_kg'] * 1000))
    return (int(Decimal(grams) * _percent(customer['weight_percent']) / 100),
            int(Decimal(volume) * _percent(customer['volume_percent']) / 100))


def validate_allocation(result, config):
    """Validate customer caps/regions after static manual validation; return a clone.

    Does NOT replace geometry/manual validation. Result must be server-generated.
    Metadata is recomputed rather than trusting browser allocation fields.
    """
    units = result['placed'] + result['unplaced']
    customers = _config(config, units, result['container'])
    reports = []
    for customer in customers:
        placed = [p for p in result['placed'] if p['source_item_id'] in customer['source_item_ids']]
        grams = sum(int(round(p['weight_kg'] * 1000)) for p in placed)
        volume = sum(int(p['dx'] * p['dy'] * p['dz']) for p in placed)
        max_grams, max_volume = _caps(customer, result['container'])
        if grams > max_grams or volume > max_volume:
            raise ValueError(f"customer {customer['id']} exceeds reserved quota")
        for p in placed:
            for axis, extent in zip('xyz', ('dx', 'dy', 'dz')):
                low, high = customer['bounds_mm'][axis]
                if p[axis] < low or p[axis] + p[extent] > high:
                    raise ValueError(f"customer {customer['id']} leaves its reserved region")
            if customer['bounds_mm']['z'][0] > 0:
                raise ValueError('elevated Z reservations require unmodeled supporting structure')
        reports.append({**customer, 'weight_limit_kg': max_grams / 1000,
                        'volume_limit_m3': max_volume / 1e9,
                        'placed_weight_kg': grams / 1000, 'placed_volume_m3': volume / 1e9,
                        'placed_count': len(placed)})
    clone = deepcopy(result)
    owners = {source: c['id'] for c in customers for source in c['source_item_ids']}
    for unit in clone['placed'] + clone['unplaced']:
        unit['customer_id'] = owners[unit['source_item_id']]
    clone['allocation'] = {'status': 'reservation_preview_only', 'config': deepcopy(config),
                           'customers': reports, 'notice': NOTICE}
    return clone


def pack_allocated(items, container_id='20std', custom_profile=None, config=None):
    """Deterministic quota-filtered packing; original dimensions/masses unchanged.

    Quota selection is largest-volume first before packing, not optimized backfill.
    Source groups refer to CSV row IDs, including all expanded quantity units.
    With no config, delegates unchanged to pack_items.
    """
    if config is None:
        return pack_items(items, container_id, custom_profile=custom_profile)
    normalized = _validate_items(items)
    if container_id == 'custom_dry':
        container = _custom_container(custom_profile)
    else:
        if custom_profile is not None:
            raise ValueError('custom_profile only allowed for custom_dry')
        container = _resolve_container(container_id)
    customers = _config(config, normalized, container)
    placed, unplaced, shared = [], [], []
    for customer in customers:
        group = sorted((p for p in normalized if p['source_item_id'] in customer['source_item_ids']),
                       key=lambda p: (-int(p['length_mm']) * int(p['width_mm']) * int(p['height_mm']), -p['weight_kg'], p['item_id']))
        max_g, max_v = _caps(customer, container)
        used_g = used_v = 0
        eligible = []
        for p in group:
            volume = int(p['length_mm']) * int(p['width_mm']) * int(p['height_mm'])
            if p['is_dg']:
                reason = 'manual_compliance_hold'
            elif customer['bounds_mm']['z'][0] > 0:
                reason = 'allocation_elevated_region_unsupported'
            elif p['weight_kg'] > max_g / 1000 or used_g + int(round(p['weight_kg'] * 1000)) > max_g:
                reason = 'customer_weight_quota'
            elif used_v + volume > max_v:
                reason = 'customer_volume_quota'
            else:
                eligible.append(p)
                used_g += int(round(p['weight_kg'] * 1000))
                used_v += volume
                continue
            unplaced.append({**p, 'reason': reason})
        if not eligible:
            continue
        if customer['region'] is None:
            shared.extend(eligible)
            continue
        bounds = customer['bounds_mm']
        inside = {dim: bounds[axis][1] - bounds[axis][0] for axis, dim in _AXES.items()}
        profile = {'name': 'Customer planning region', 'inside_mm': inside,
                   'door_mm': {k: min(container['door_mm'][k], inside[k]) for k in ('width', 'height')},
                   'max_payload_kg': container['max_payload_kg'],
                   'dimensions_source': {'kind': 'user_measurement', 'reference': 'Derived planning partition, not equipment dimensions'}}
        result = pack_items(eligible, 'custom_dry', custom_profile=profile)
        for p in result['placed']:
            placed.append({**p, **{axis: p[axis] + bounds[axis][0] for axis in _AXES}})
        unplaced.extend(result['unplaced'])
    if shared:
        result = pack_items(shared, container_id, custom_profile=custom_profile)
        placed.extend(result['placed'])
        unplaced.extend(result['unplaced'])
    holds = sum(p['reason'] == 'manual_compliance_hold' for p in unplaced)
    result = {'container': deepcopy(container), 'placed': placed, 'unplaced': unplaced,
              'mass_distribution': _mass_distribution(placed, container),
              'readiness': 'manual_compliance_hold' if holds else 'packing_preview_only',
              'totals': {'input_count': len(normalized), 'placed_count': len(placed), 'unplaced_count': len(unplaced),
                         'manual_compliance_hold_count': holds,
                         'placed_weight_kg': sum(int(round(p['weight_kg'] * 1000)) for p in placed) / 1000,
                         'placed_volume_m3': sum(p['dx'] * p['dy'] * p['dz'] for p in placed) / 1e9}}
    return validate_allocation(result, config)
