"""Bounded sequential identical-equipment preview, not an optimal fleet plan.

A unit occurs exactly once across loads[].placed and top-level unplaced. Failed
attempts are not duplicated in each load. No global cargo centroid is meaningful
across separate equipment, so centres are reported per load only.
"""
from copy import deepcopy
from .packing import pack_items, _validate_items, _hold_summary, MAX_CANDIDATE_CHECKS_PER_PACK
from .allowances import _settings, _active, _equipment, _transform, _restore

MAX_CONTAINERS = 5
NOTICE = ('Sequential identical-equipment packing heuristic, not a minimum-container or utilization optimum. '
          'At most five nonempty loads and 100 expanded units, sharing one 100000-candidate search budget. '
          'Dangerous goods and temperature-controlled cargo are held once for manual review, never retried. '
          'Customer allocations are not supported in multi-container mode. Existing upright geometry, '
          'declared stacking limits and allowance limitations still apply; no transport-safety approval, live tariff or booking.')


def pack_multiple(items, container_id='20std', *, custom_profile=None, max_containers=2,
                  allocation=None, allowances=None):
    if type(max_containers) is not int or not 1 <= max_containers <= MAX_CONTAINERS:
        raise ValueError('max_containers must be an integer from 1 to 5')
    if allocation is not None:
        raise ValueError('Customer allocations are not supported in multi-container planning')
    original = _validate_items(items)
    container = _equipment(container_id, custom_profile)
    config = _settings(allowances)
    positive = _active(config)
    # Validate allowances/equipment even when all units will be held.
    if positive:
        _transform(original, container, config)
    originals = {p['item_id']: p for p in original}
    pending = original
    loads, final_unplaced = [], []
    budget = [MAX_CANDIDATE_CHECKS_PER_PACK]
    stop_reason = 'all_eligible_cargo_placed'
    while pending and len(loads) < max_containers:
        if positive:
            transformed, profile = _transform(pending, container, config)
            packed = pack_items(transformed, 'custom_dry', custom_profile=profile, _candidate_budget=budget)
            packed = _restore(packed, pending, container, config)
        else:
            packed = pack_items(pending, container_id, custom_profile=custom_profile, _candidate_budget=budget)
        retry = []
        for unit in packed['unplaced']:
            # A cumulative per-load payload limit may be solved in a new load;
            # an individually overweight unit or impossible envelope cannot.
            terminal = (unit['reason'] in ('manual_compliance_hold', 'temperature_control_manual_hold',
                                          'door_or_container_dimensions')
                        or unit['weight_kg'] > container['max_payload_kg'])
            if terminal:
                final_unplaced.append(unit)
            else:
                retry.append(unit)
        if packed['placed']:
            number = len(loads) + 1
            load = deepcopy(packed)
            load['load_number'] = number
            for unit in load['placed']:
                unit['load_number'] = number
            load['unplaced'] = []
            load['readiness'] = 'packing_preview_only'
            load['totals'].update(input_count=len(load['placed']), unplaced_count=0,
                                  manual_compliance_hold_count=0, temperature_control_manual_hold_count=0,
                                  manual_review_hold_count=0)
            loads.append(load)
        if not retry:
            pending = []
            break
        if not packed['placed']:
            stop_reason = 'no_progress' if budget[0] else 'candidate_budget_exhausted'
            final_unplaced.extend(retry)
            pending = []
            break
        if budget[0] == 0:
            stop_reason = 'candidate_budget_exhausted'
            final_unplaced.extend(retry)
            pending = []
            break
        if len(loads) == max_containers:
            stop_reason = 'container_limit_reached'
            final_unplaced.extend(retry)
            pending = []
            break
        # Restore authoritative allowed orientation/handling, never reuse the
        # chosen orientation or reason metadata as next-load input rules.
        pending = [originals[p['item_id']] for p in retry]
    if final_unplaced and stop_reason == 'all_eligible_cargo_placed':
        stop_reason = 'no_retryable_cargo' if loads else 'no_eligible_cargo_fit'
    hold = _hold_summary(final_unplaced)
    placed = [p for load in loads for p in load['placed']]
    result = {'container': deepcopy(container), 'loads': loads, 'unplaced': final_unplaced,
              'readiness': hold['readiness'],
              'planning': {'notice': NOTICE, 'requested_container_limit': max_containers,
                           'used_containers': len(loads), 'candidate_budget': MAX_CANDIDATE_CHECKS_PER_PACK,
                           'candidate_checks_used': MAX_CANDIDATE_CHECKS_PER_PACK-budget[0],
                           'stop_reason': stop_reason},
              'totals': {'input_count': len(original), 'placed_count': len(placed),
                         'unplaced_count': len(final_unplaced),
                         **{k:v for k,v in hold.items() if k!='readiness'},
                         'placed_weight_kg': sum(int(round(p['weight_kg']*1000)) for p in placed)/1000,
                         'placed_volume_m3': sum(p['dx']*p['dy']*p['dz'] for p in placed)/1e9}}
    if positive:
        result['allowances'] = {'config': config, 'notice': 'Each load uses its own floor-only allowance preview.'}
        result['totals']['placed_envelope_volume_m3'] = sum(load['totals']['placed_envelope_volume_m3'] for load in loads)
    return result
