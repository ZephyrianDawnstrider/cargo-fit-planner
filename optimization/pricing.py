"""User-supplied scoped quote estimates. Never a live market-price service."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

RATE_FIELDS = {
    'rate_amount': ('Quoted amount', 30),
    'rate_currency': ('Currency (3 letters)', 3),
    'rate_basis': ('Basis: trip, tonne, or m3', 12),
    'rate_container_id': ('Quoted equipment ID', 40),
    'rate_origin': ('Quote origin', 100),
    'rate_destination': ('Quote destination', 100),
    'rate_valid_from': ('Valid from (YYYY-MM-DD)', 10),
    'rate_valid_until': ('Valid until (YYYY-MM-DD)', 10),
    'rate_shipment_date': ('Shipment date (YYYY-MM-DD)', 10),
    'rate_source': ('Carrier quote or tariff reference', 240),
    'rate_included': ('Included charges', 300),
    'rate_excluded': ('Excluded charges / assumptions', 300),
}


def quote_fields(data):
    result = {}
    for key, (label, limit) in RATE_FIELDS.items():
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
            raise ValueError(f'{label} is invalid or too long.')
        result[key] = value.strip()
    return result


def estimate(result, shipment, fields):
    quote = quote_fields(fields)
    base = {'amount': None, 'currency': None, 'status': 'unpriced', 'quote': quote,
            'notice': 'User-supplied quote estimate for placed cargo only; not a booking, invoice, live tariff or market average.'}
    if not quote['rate_amount']:
        return {**base, 'reason': 'No quote entered.'}
    required = [k for k in RATE_FIELDS if k != 'rate_excluded']
    if any(not quote[k] for k in required):
        raise ValueError('A quoted amount requires currency, basis, equipment, route, dates, source and included charges.')
    try:
        amount = Decimal(quote['rate_amount'])
    except InvalidOperation:
        raise ValueError('Quoted amount must be a valid decimal.') from None
    if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000000') or amount.as_tuple().exponent < -2:
        raise ValueError('Quoted amount must be nonnegative, at most 1e12 and have at most two decimal places.')
    if not re.fullmatch(r'[A-Za-z]{3}', quote['rate_currency']):
        raise ValueError('Currency must be a three-letter code such as INR.')
    quote['rate_currency'] = quote['rate_currency'].upper()
    if quote['rate_basis'] not in ('trip', 'tonne', 'm3'):
        raise ValueError('Rate basis must be trip, tonne or m3.')
    dates = {}
    for key in ('rate_valid_from', 'rate_valid_until', 'rate_shipment_date'):
        try:
            parsed = date.fromisoformat(quote[key])
        except ValueError:
            raise ValueError('Quote dates must use YYYY-MM-DD.') from None
        if parsed.isoformat() != quote[key]:
            raise ValueError('Quote dates must use YYYY-MM-DD.')
        dates[key] = parsed
    if dates['rate_valid_from'] > dates['rate_valid_until']:
        raise ValueError('Quote validity end must not precede its start.')
    if quote['rate_container_id'] != result['container']['id']:
        return {**base, 'reason': 'Quote equipment does not match the packed equipment.'}
    if any(quote['rate_'+key].casefold() != shipment.get(key,'').strip().casefold() for key in ('origin','destination')):
        return {**base, 'reason': 'Quote route does not match shipment origin/destination.'}
    if not dates['rate_valid_from'] <= dates['rate_shipment_date'] <= dates['rate_valid_until']:
        return {**base, 'reason': 'Shipment date is outside quote validity.'}
    if not result['placed']:
        return {**base, 'reason': 'No cargo was placed; no load price calculated.'}
    factor = {'trip': Decimal(1), 'tonne': Decimal(str(result['totals']['placed_weight_kg'])) / 1000,
              'm3': Decimal(str(result['totals']['placed_volume_m3']))}[quote['rate_basis']]
    total = (amount * factor).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return {**base, 'amount': str(total), 'currency': quote['rate_currency'], 'status': 'estimate',
            'reason': 'Quote scope matched; exclusions remain payable separately.'}
