"""Stateless sequential multi-container planning and authoritative exports."""
import csv
import io
import json
import re
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .packing import CONTAINERS, DEMO_CSV, parse_csv
from .pricing import RATE_FIELDS, quote_fields, estimate
from . import mvp_views as single

INPUT_FIELDS = ('cargo_csv', 'container_id', 'max_containers', 'custom_profile_json',
                'allowances_json', *single.SHIPMENT_FIELDS, *RATE_FIELDS)


def _plan(data):
    # Never silently reinterpret a single-load allocation or edited placement.
    if data.get('allocation_json', '').strip():
        raise ValueError('Customer allocations are not supported in multi-container mode. Use the single-container workspace.')
    if data.get('manual_layout_json', '').strip():
        raise ValueError('Manual placement snapshots are not supported in multi-container mode. Export a freshly generated plan.')
    limit = data.get('max_containers', '2')
    if not isinstance(limit, str) or not re.fullmatch('[1-5]', limit):
        raise ValueError('Choose a maximum of 1 to 5 containers.')
    container_id = data.get('container_id', '20std').strip()
    if container_id not in CONTAINERS and container_id != 'custom_dry':
        raise ValueError('Choose a supported dry-container profile.')
    if container_id != 'custom_dry' and data.get('custom_profile_json', '').strip():
        raise ValueError('Custom measurements require the custom dry-box selection; clear them for a published profile.')
    custom = single._custom_profile_data(data, container_id)
    source = data.get('cargo_csv', '')
    if single._source_too_large(source):
        raise ValueError('CSV is too large. Keep uploads under 256 KiB.')
    items = parse_csv(source)
    shipment, quote = single._shipment_data(data), quote_fields(data)
    allowances = single._allowances_data(data)
    from .multi_container import pack_multiple
    result = pack_multiple(items, container_id=container_id, custom_profile=custom,
                           max_containers=int(limit), allowances=allowances)
    single._with_unverified_floor_checks(result)
    result['shipment'] = shipment
    # Validate a supplied quote even when nothing can be placed.
    estimate({'container': result['container'], 'placed': [], 'totals': {}}, shipment, quote)
    for load in result['loads']:
        single._with_unverified_floor_checks(load)
        load['pricing'] = estimate(load, shipment, quote)
        inner = load['container']['inside_mm']
        volume = inner['length'] * inner['width'] * inner['height'] / 1e9
        payload = load['container']['max_payload_kg']
        load['capacity'] = {
            'payload_limit_kg': payload,
            'payload_remaining_kg': round(max(0, payload-load['totals']['placed_weight_kg']), 3),
            'payload_used_percent': round(load['totals']['placed_weight_kg']/payload*100, 1),
            'nominal_volume_m3': round(volume, 6),
            'nominal_volume_remaining_m3': round(max(0, volume-load['totals']['placed_volume_m3']), 6),
            'nominal_volume_used_percent': round(load['totals']['placed_volume_m3']/volume*100, 1),
            'notice': 'Nominal remaining volume is not necessarily usable space; dimensions, fragmentation, allowances and handling constraints still govern fit.',
        }
    prices = [load['pricing'] for load in result['loads']]
    complete = bool(prices) and all(p['status'] == 'estimate' for p in prices)
    result['pricing'] = {
        'status': 'estimate' if complete else 'unpriced',
        'amount': str(sum((Decimal(p['amount']) for p in prices), Decimal(0))) if complete else None,
        'currency': prices[0]['currency'] if complete else None,
        'quote': quote,
        'notice': 'Sum of per-container estimates for placed cargo only. Remaining/held cargo and excluded charges are not priced. A trip rate applies separately to every used container; this is not a minimum-cost plan, booking or invoice.',
    }
    return result


def _context(data=None):
    snapshot = {field: '' for field in INPUT_FIELDS}
    snapshot.update(cargo_csv=DEMO_CSV, container_id='20std', max_containers='2')
    if data is not None:
        snapshot.update({field: data.get(field, snapshot[field]) for field in INPUT_FIELDS})
    return {'snapshot': snapshot, 'profiles': CONTAINERS.values(),
            'quote_inputs': [{'key': key, 'label': label, 'limit': limit, 'value': snapshot[key]}
                             for key, (label, limit) in RATE_FIELDS.items()],
            'shipment_inputs': [{'key': key, 'label': label, 'limit': limit, 'value': snapshot[key]}
                                for key, (label, limit) in single.SHIPMENT_FIELDS.items()]}


@never_cache
@require_http_methods(['GET', 'POST'])
def index(request):
    context = _context(request.POST if request.method == 'POST' else None)
    status = 200
    if request.method == 'POST':
        if not single._COMPUTE_SLOT.acquire(blocking=False):
            return single._busy_response()
        try:
            context['result'] = _plan(request.POST)
        except (ValueError, TypeError, UnicodeError) as exc:
            context['error'] = str(exc)
            status = 400
        finally:
            single._COMPUTE_SLOT.release()
    return render(request, 'optimization/multi.html', context, status=status)


def _export(request, kind):
    if not single._COMPUTE_SLOT.acquire(blocking=False):
        return single._busy_response()
    try:
        result = _plan(request.POST)
        if kind == 'json':
            content = json.dumps(result, indent=2, allow_nan=False)
            mime = 'application/json; charset=utf-8'
        else:
            fields = ['load_number', 'status', 'reason', 'item_id', 'source_item_id', 'name',
                      'x', 'y', 'z', 'dx', 'dy', 'dz', 'length_mm', 'width_mm', 'height_mm',
                      'weight_kg', 'orientation', 'rotation_deg', 'load_unit_type', 'stackable', 'floor_only',
                      'max_supported_load_kg', 'stacking_rating_source', 'supported_cargo_kg',
                      'is_dg', 'un_number', 'imdg_class', 'packing_group',
                      'requires_temperature_control', 'temperature_min_c', 'temperature_max_c',
                      'handling_source', 'dg_declaration_reference', 'container_id',
                      'equipment_json', 'planning_envelope_json', 'allowances_json', 'planning_notice',
                      'floor_concentrated_load_check', 'forklift_axle_load_check', 'unverified_checks_notice',
                      'special_handling_review_notice', 'whole_container_estimate', 'cost_currency', 'cost_status',
                      'quote_json', 'pricing_notice', *single.SHIPMENT_FIELDS]
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            common = {'container_id': result['container']['id'],
                      'equipment_json': json.dumps(result['container'], ensure_ascii=False),
                      'planning_notice': result['planning']['notice'],
                      'pricing_notice': 'whole_container_estimate is repeated per item, not an item charge. Do not sum rows. '+result['pricing']['notice'],
                      'floor_concentrated_load_check': 'UNVERIFIED', 'forklift_axle_load_check': 'UNVERIFIED',
                      'unverified_checks_notice': result['unverified_checks']['notice'],
                      'special_handling_review_notice': result['special_handling_review']['notice'],
                      'quote_json': json.dumps(result['pricing']['quote'], ensure_ascii=False), **result['shipment']}
            for load in result['loads']:
                for item in load['placed']:
                    writer.writerow(single._safe_csv_row({**item, **common, 'load_number': load['load_number'],
                        'status': 'placed', 'reason': '',
                        'planning_envelope_json': json.dumps(item.get('planning_envelope_mm', {})),
                        'allowances_json': json.dumps(load.get('allowances', {}), ensure_ascii=False),
                        'whole_container_estimate': load['pricing']['amount'],
                        'cost_currency': load['pricing']['currency'], 'cost_status': load['pricing']['status']}))
            for item in result['unplaced']:
                writer.writerow(single._safe_csv_row({**item, **common, 'load_number': '', 'status': 'unplaced',
                    'allowances_json': json.dumps(single._allowances_data(request.POST) or {}),
                    'cost_status': 'unpriced'}))
            content, mime = out.getvalue(), 'text/csv; charset=utf-8'
        response = HttpResponse(content, content_type=mime)
        response['Content-Disposition'] = f'attachment; filename="cargo-multi-plan.{kind}"'
        return response
    except (ValueError, TypeError, UnicodeError) as exc:
        return HttpResponse(str(exc), status=400, content_type='text/plain; charset=utf-8')
    finally:
        single._COMPUTE_SLOT.release()


@never_cache
@require_POST
def export_json(request):
    return _export(request, 'json')


@never_cache
@require_POST
def export_csv(request):
    return _export(request, 'csv')
