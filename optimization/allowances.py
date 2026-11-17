"""Measured-cargo planning allowances. Positive settings require floor-only layouts.

Server-authoritative manifests/profiles only. Padding is never load-bearing.
Coordinates identify the measured cargo minimum corner, also the envelope origin.
"""
from copy import deepcopy

from .allocation import pack_allocated, validate_allocation, _config as _allocation_config, _select_quota
from .manual_layout import validate_manual_layout, ManualLayoutError
from .packing import _validate_items, _resolve_container, _custom_container, _mass_distribution, pack_items, _hold_summary

_FIELDS = ('dimension_tolerance_mm', 'horizontal_gap_mm', 'wall_clearance_mm',
           'roof_clearance_mm', 'door_clearance_mm')
NOTICE = ('Planning allowances are user-supplied, not recommended universal gaps. Tolerance is added once '
          'to each total measured dimension. Horizontal gap separates tolerance envelopes. Wall clearance '
          'applies to both ends and sides; roof clearance above; no clearance below cargo. Door clearance '
          'is subtracted once from total doorway width and height. Positive allowances force all cargo '
          'onto the floor with no stacking. No strength, ventilation, reefer, securing or transport approval. '
          'Mass centre uses original measured dimensions; dimensional uncertainty is not a measured mass distribution.')


def _settings(raw):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - set(_FIELDS) - {'source_reference'}:
        raise ValueError('Invalid allowance fields')
    config = {}
    for key in _FIELDS:
        value = raw.get(key, 0)
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f'{key} must be an integer from 0 to 100')
        config[key] = value
    reference = raw.get('source_reference', '')
    if not isinstance(reference, str) or len(reference) > 200:
        raise ValueError('source_reference must be text up to 200 characters')
    config['source_reference'] = reference.strip()
    if any(config[k] for k in _FIELDS) and not config['source_reference']:
        raise ValueError('Provide a source_reference for nonzero allowances')
    return config


def _active(config):
    return any(config[k] for k in _FIELDS)


def _equipment(container_id, custom_profile):
    if container_id == 'custom_dry':
        return _custom_container(custom_profile)
    if custom_profile is not None:
        raise ValueError('custom_profile only allowed for custom_dry')
    return _resolve_container(container_id)


def _transform(source, container, config):
    t, gap, wall, roof, door = (config[k] for k in _FIELDS)
    inner = container['inside_mm']
    # Trailing horizontal gap is canceled at the outer boundary by enlarging
    # the computational region by exactly one gap, not the physical container.
    inside = {'length': inner['length'] - 2 * wall + gap,
              'width': inner['width'] - 2 * wall + gap,
              'height': inner['height'] - roof}
    doorway = {'width': min(inside['width'], container['door_mm']['width'] - door + gap),
               'height': min(inside['height'], container['door_mm']['height'] - door)}
    if any(v < 1 or v > 100000 for v in list(inside.values()) + list(doorway.values())):
        raise ValueError('Allowances leave no usable space or exceed the bounded planning engine range')
    # Check actual space too: a gap must not turn a closed aperture positive.
    if inner['length'] <= 2*wall or inner['width'] <= 2*wall or container['door_mm']['width'] <= door:
        raise ValueError('Allowances leave no usable space')
    profile = {'name': 'Internal allowance computation', 'inside_mm': inside, 'door_mm': doorway,
               'max_payload_kg': container['max_payload_kg'],
               'dimensions_source': {'kind': 'user_measurement', 'reference': 'Derived computational envelope; not physical equipment'}}
    transformed = [{**p, 'length_mm': p['length_mm']+t+gap, 'width_mm': p['width_mm']+t+gap,
                    'height_mm': p['height_mm']+t, 'floor_only': True, 'stackable': False} for p in source]
    return transformed, profile


def _restore(engine, source, container, config):
    result = deepcopy(engine)
    originals = {p['item_id']: p for p in source}
    wall, t, gap = config['wall_clearance_mm'], config['dimension_tolerance_mm'], config['horizontal_gap_mm']
    for status in ('placed', 'unplaced'):
        for p in result[status]:
            original = originals[p['item_id']]
            p.update({key: value for key, value in original.items() if key != 'orientation'})
            if status == 'unplaced':
                p['orientation'] = original['orientation']
                continue
            dx, dy = original['length_mm'], original['width_mm']
            if p['rotation_deg'] == 90:
                dx, dy = dy, dx
            p.update(x=p['x']+wall, y=p['y']+wall, dx=dx, dy=dy, dz=original['height_mm'])
            p['planning_envelope_mm'] = {'dx': dx+t, 'dy': dy+t, 'dz': original['height_mm']+t}
            p['planning_floor_only'] = True
            p['supported_cargo_kg'] = 0.0
    result['container'] = deepcopy(container)
    result['totals']['placed_volume_m3'] = sum(p['dx']*p['dy']*p['dz'] for p in result['placed'])/1e9
    result['totals']['placed_envelope_volume_m3'] = sum(
        p['planning_envelope_mm']['dx']*p['planning_envelope_mm']['dy']*p['planning_envelope_mm']['dz']
        for p in result['placed'])/1e9
    result['mass_distribution'] = _mass_distribution(result['placed'], container)
    result['mass_distribution']['notice'] += ' Allowances do not change measured-box centres; actual dimensional uncertainty is not modeled.'
    result['allowances'] = {'config': deepcopy(config), 'status': 'floor_only_allowance_preview',
                            'coordinate_basis': 'measured_cargo_minimum_corner_and_tolerance_envelope_origin',
                            'envelope_volume_excludes_horizontal_gap': True, 'notice': NOTICE}
    return result


COMBINED_NOTICE = ('Customer quotas use original measured gross cargo volume and mass against whole original equipment, '
                   'not enlarged envelope volume or reduced usable space. Original partition boundaries stay fixed. '
                   'Each internal horizontal partition high edge reserves one additional horizontal gap; this conservative '
                   'buffer also applies when the adjacent partition is empty. Physical outer boundaries do not add this '
                   'buffer. Wall and roof clearances apply only at physical equipment boundaries. All placements are '
                   'floor-only; elevated partitions remain held. Door checks use the real globally reduced opening, '
                   'with local region width/height additionally limiting fit, not a claim about a loading path.')


def _combined_region_bounds(customer, container, config):
    """Envelope bounds, original region intersected with physical clearances."""
    inner = container['inside_mm']
    wall, gap = config['wall_clearance_mm'], config['horizontal_gap_mm']
    bounds = deepcopy(customer['bounds_mm'])
    for axis, dim in (('x', 'length'), ('y', 'width')):
        low, high = bounds[axis]
        buffer = gap if high < inner[dim] else 0
        bounds[axis] = [max(low, wall), min(high-buffer, inner[dim]-wall)]
    bounds['z'][1] = min(bounds['z'][1], inner['height']-config['roof_clearance_mm'])
    return bounds


def _validate_combined(result, allocation, config):
    result = validate_allocation(result, allocation)
    for customer in result['allocation']['customers']:
        bounds = _combined_region_bounds(customer, result['container'], config)
        customer['planning_envelope_bounds_mm'] = bounds
        customer['quota_volume_basis'] = 'original_measured_gross_cargo'
        customer['placed_envelope_volume_m3'] = 0
        for cargo in result['placed']:
            if cargo['customer_id'] != customer['id']:
                continue
            envelope = cargo['planning_envelope_mm']
            for axis, extent in zip('xyz', ('dx', 'dy', 'dz')):
                if cargo[axis] < bounds[axis][0] or cargo[axis]+envelope[extent] > bounds[axis][1]:
                    raise ManualLayoutError('allocation_envelope_bounds',
                                            'Tolerance envelope enters a reserved boundary buffer or leaves its customer region.',
                                            [cargo['item_id']])
            customer['placed_envelope_volume_m3'] += envelope['dx']*envelope['dy']*envelope['dz']/1e9
    result['allocation']['notice'] += ' ' + COMBINED_NOTICE
    result['allowances']['allocation_boundary_policy'] = 'one_horizontal_gap_at_internal_high_edges'
    result['allowances']['allocation_notice'] = COMBINED_NOTICE
    return result


def _pack_combined(source, container, allocation, config):
    customers = _allocation_config(allocation, source, container)
    transformed, global_profile = _transform(source, container, config)
    transformed_by_id = {p['item_id']: p for p in transformed}
    placed, unplaced, shared = [], [], []
    wall, gap = config['wall_clearance_mm'], config['horizontal_gap_mm']
    for customer in customers:
        eligible, held = _select_quota(source, customer, container)
        unplaced.extend(held)
        if not eligible:
            continue
        if customer['region'] is None:
            shared.extend(transformed_by_id[p['item_id']] for p in eligible)
            continue
        bounds = _combined_region_bounds(customer, container, config)
        # Engine boxes include trailing horizontal gap. Add it back to the
        # envelope bounds here; internal boundary buffer has already removed it.
        inside = {'length': bounds['x'][1]-bounds['x'][0]+gap,
                  'width': bounds['y'][1]-bounds['y'][0]+gap,
                  'height': bounds['z'][1]-bounds['z'][0]}
        if any(bounds[a][1] <= bounds[a][0] for a in 'xyz'):
            unplaced.extend({**p, 'reason': 'allocation_clearances_no_usable_region'} for p in eligible)
            continue
        profile = deepcopy(global_profile)
        profile['inside_mm'] = inside
        profile['door_mm'] = {k: min(global_profile['door_mm'][k], inside[k]) for k in ('width', 'height')}
        result = pack_items([transformed_by_id[p['item_id']] for p in eligible], 'custom_dry', custom_profile=profile)
        for p in result['placed']:
            # _restore applies the global wall inset. These offsets cancel it
            # so the output remains in the original physical equipment frame.
            placed.append({**p, 'x': p['x']+bounds['x'][0]-wall,
                           'y': p['y']+bounds['y'][0]-wall, 'z': p['z']})
        unplaced.extend(result['unplaced'])
    if shared:
        result = pack_items(shared, 'custom_dry', custom_profile=global_profile)
        placed.extend(result['placed'])
        unplaced.extend(result['unplaced'])
    hold_summary = _hold_summary(unplaced)
    engine = {'container': container, 'placed': placed, 'unplaced': unplaced,
              'readiness': hold_summary['readiness'],
              'totals': {'input_count': len(source), 'placed_count': len(placed), 'unplaced_count': len(unplaced),
                         **{k:v for k,v in hold_summary.items() if k != 'readiness'},
                         'placed_weight_kg': sum(int(round(p['weight_kg']*1000)) for p in placed)/1000}}
    return _validate_combined(_restore(engine, source, container, config), allocation, config)


def pack_with_allowances(items, container_id='20std', custom_profile=None, allocation=None, allowances=None):
    config = _settings(allowances)
    if not _active(config):
        return pack_allocated(items, container_id, custom_profile, allocation)
    source = _validate_items(items)
    container = _equipment(container_id, custom_profile)
    if allocation is not None:
        return _pack_combined(source, container, allocation, config)
    transformed, profile = _transform(source, container, config)
    engine = pack_items(transformed, 'custom_dry', custom_profile=profile)
    return _restore(engine, source, container, config)


def validate_with_allowances(result, placements, source_items, allowances=None, allocation=None):
    """Validate edits against a freshly regenerated authoritative packing result."""
    config = _settings(allowances)
    if not _active(config):
        if result.get('allowances'):
            raise ValueError('Allowance settings changed; repack before editing')
        updated = validate_manual_layout(result, placements, source_items=source_items)
        return validate_allocation(updated, allocation) if allocation is not None else updated
    if result.get('allowances', {}).get('config') != config:
        raise ValueError('Allowance settings changed; repack before editing')
    source = _validate_items(source_items)
    # First verify source identity, original measurements, rotation permissions,
    # physical geometry and exact edit schema before any coordinate conversion.
    validate_manual_layout(result, placements, source_items=source)
    transformed, profile = _transform(source, result['container'], config)
    by_id = {p['item_id']: p for p in transformed}
    engine = deepcopy(result)
    engine['container'] = _custom_container(profile)
    for status in ('placed', 'unplaced'):
        for p in engine[status]:
            chosen = p['orientation']
            p.update(by_id[p['item_id']])
            if status == 'placed':
                p['orientation'] = chosen
                p['x'] -= config['wall_clearance_mm']
                p['y'] -= config['wall_clearance_mm']
    edits = deepcopy(placements)
    for edit in edits:
        if edit['z'] != 0:
            raise ManualLayoutError('floor_only', 'Positive allowances require floor-only placements', [edit['item_id']])
        if edit['x'] < config['wall_clearance_mm'] or edit['y'] < config['wall_clearance_mm']:
            raise ManualLayoutError('wall_clearance', f"Keep cargo at least {config['wall_clearance_mm']} mm from the side/end walls.", [edit['item_id']])
        edit['x'] -= config['wall_clearance_mm']
        edit['y'] -= config['wall_clearance_mm']
    try:
        checked = validate_manual_layout(engine, edits, source_items=transformed)
    except ManualLayoutError as exc:
        # Measured cargo geometry already passed above. This second pass checks
        # enlarged planning envelopes plus the requested horizontal gap.
        if exc.code == 'overlap':
            raise ManualLayoutError(
                'planning_clearance_overlap',
                'Tolerance envelopes overlap or the required horizontal inter-cargo gap is not maintained. '
                'Measured cargo boxes may still be separate.',
                exc.item_ids) from None
        raise
    restored = _restore(checked, source, result['container'], config)
    return _validate_combined(restored, allocation, config) if allocation is not None else restored
