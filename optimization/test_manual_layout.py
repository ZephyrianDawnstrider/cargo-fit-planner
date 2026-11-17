"""Static manual-layout invariants; no browser, network, or physics claims."""
from copy import deepcopy
import json
import unittest

from optimization.manual_layout import ManualLayoutError, validate_manual_layout
from optimization.packing import pack_items, parse_csv


def item(ident, *, length=500, width=400, height=300, weight=10, **extra):
    return {'item_id': ident, 'name': ident, 'length_mm': length, 'width_mm': width,
            'height_mm': height, 'weight_kg': weight, 'stackable': True,
            'orientation': 'fixed', **extra}


def edits(result):
    return [{'item_id': p['item_id'], 'x': int(p['x']), 'y': int(p['y']),
             'z': int(p['z']), 'rotation_deg': p['rotation_deg']} for p in result['placed']]


class ManualLayoutTests(unittest.TestCase):
    def assert_rejected(self, code, result, changes, **kwargs):
        before, edits_before = deepcopy(result), deepcopy(changes)
        with self.assertRaises(ManualLayoutError) as context:
            validate_manual_layout(result, changes, **kwargs)
        self.assertEqual(context.exception.code, code)
        self.assertEqual(result, before)
        self.assertEqual(changes, edits_before)
        return context.exception

    def test_valid_translation_clones_and_recomputes_mass(self):
        result = pack_items([item('a', weight=30), item('b', weight=10)])
        old = deepcopy(result)
        changes = edits(result)
        for p in changes:
            p['x'] += 1000
        changed = validate_manual_layout(result, changes)
        self.assertEqual(result, old)
        self.assertEqual(changed['mass_distribution']['center_mm']['x'], 1250)
        self.assertEqual(changed['totals'], result['totals'])
        self.assertEqual(changed['manual_layout']['status'], 'validated_geometry_preview')
        self.assertIn('No load-strength', changed['manual_layout']['notice'])
        changed['container']['inside_mm']['length'] = 1
        self.assertNotEqual(changed['container'], result['container'])
        json.dumps(changed, allow_nan=False)

    def test_yaw_permission_uses_original_source_not_chosen_orientation(self):
        source = [item('a', orientation='yaw')]
        result = pack_items(source)
        self.assertEqual(result['placed'][0]['orientation'], 'fixed')
        changes = edits(result)
        changes[0]['rotation_deg'] = 90
        self.assert_rejected('orientation_not_allowed', result, changes)
        changed = validate_manual_layout(result, changes, source_items=source)
        cargo = changed['placed'][0]
        self.assertEqual((cargo['dx'], cargo['dy'], cargo['dz']), (400, 500, 300))
        self.assertEqual((cargo['orientation'], cargo['rotation_deg']), ('yaw', 90))
        self.assertEqual((cargo['length_mm'], cargo['width_mm']), (500, 400))

    def test_chosen_yaw_result_can_rotate_back_without_source(self):
        result = pack_items([item('a', length=1000, width=2400, orientation='yaw')])
        self.assertEqual(result['placed'][0]['rotation_deg'], 90)
        changes = edits(result)
        changes[0]['rotation_deg'] = 0
        self.assert_rejected('door_clearance', result, changes)

    def test_fixed_rotation_and_tipping_rejected(self):
        result = pack_items([item('a')])
        changes = edits(result)
        changes[0]['rotation_deg'] = 90
        self.assert_rejected('orientation_not_allowed', result, changes)
        for angle in (45, 180, -90, 0.0, True, '90'):
            changes[0]['rotation_deg'] = angle
            self.assert_rejected('invalid_rotation', result, changes)

    def test_collision_rejected_faces_may_touch(self):
        result = pack_items([item('a'), item('b')])
        changes = edits(result)
        changes[1].update(x=500, y=0, z=0)
        validate_manual_layout(result, changes)
        changes[1]['x'] = 499
        error = self.assert_rejected('overlap', result, changes)
        self.assertCountEqual(error.item_ids, ['a', 'b'])

    def test_container_exact_boundary_and_one_mm_beyond(self):
        result = pack_items([item('a')])
        changes = edits(result)
        changes[0].update(x=5896-500, y=2350-400)
        validate_manual_layout(result, changes)
        changes[0]['x'] += 1
        self.assert_rejected('container_bounds', result, changes)

    def test_coordinate_type_range_and_schema(self):
        result = pack_items([item('a')])
        for coordinate in (True, 1.0, '1', -1, 100001, None, float('nan'), float('inf')):
            changes = edits(result)
            changes[0]['x'] = coordinate
            with self.assertRaises(ManualLayoutError) as error:
                validate_manual_layout(result, changes)
            self.assertEqual(error.exception.code, 'invalid_coordinate')
        for field in ('weight_kg', 'dx', 'is_dg', 'stackable'):
            changes = edits(result)
            changes[0][field] = 0
            self.assert_rejected('invalid_edits', result, changes)
        changes = edits(result)
        del changes[0]['z']
        self.assert_rejected('invalid_edits', result, changes)
        self.assert_rejected('invalid_edits', result, {})
        self.assert_rejected('invalid_edits', result, [None])

    def test_ids_cannot_be_omitted_added_duplicated_or_replaced(self):
        result = pack_items([item('a'), item('b')])
        self.assert_rejected('id_mismatch', result, edits(result)[:1])
        self.assert_rejected('id_mismatch', result, edits(result) + edits(result)[:1])
        changes = edits(result)
        changes[1]['item_id'] = 'a'
        self.assert_rejected('id_mismatch', result, changes)
        changes[1]['item_id'] = 'unknown'
        self.assert_rejected('id_mismatch', result, changes)

    def test_floating_unit_rejected(self):
        result = pack_items([item('a')])
        changes = edits(result)
        changes[0]['z'] = 1
        self.assert_rejected('unsupported', result, changes)

    def test_full_support_is_order_independent_and_base_must_be_grounded(self):
        result = pack_items([item('base', length=1000, width=1000, height=400), item('top')])
        changes = edits(result)
        next(p for p in changes if p['item_id'] == 'top').update(x=0, y=0, z=400)
        changed = validate_manual_layout(result, list(reversed(changes)))
        self.assertEqual(changed['placed'][1]['z'], 400)
        for p in changes:
            p['z'] += 1
        self.assert_rejected('unsupported', result, changes)

    def test_partial_or_split_support_rejected(self):
        result = pack_items([item('a', length=500, width=500), item('b', length=500, width=500),
                             item('bridge', length=1000, width=500, height=100)])
        changes = [{'item_id': 'a', 'x': 0, 'y': 0, 'z': 0, 'rotation_deg': 0},
                   {'item_id': 'b', 'x': 500, 'y': 0, 'z': 0, 'rotation_deg': 0},
                   {'item_id': 'bridge', 'x': 0, 'y': 0, 'z': 300, 'rotation_deg': 0}]
        self.assert_rejected('unsupported', result, changes)
        changes[2]['x'] = 1
        self.assert_rejected('unsupported', result, changes)

    def test_nonstackable_and_floor_only_remain_independent(self):
        source = [item('base', length=1000, width=1000, height=400, stackable=False), item('top')]
        result = pack_items(source)
        changes = edits(result)
        next(p for p in changes if p['item_id'] == 'top').update(x=0, y=0, z=400)
        self.assert_rejected('unsupported', result, changes, source_items=source)
        source[0]['stackable'] = True
        source[1]['floor_only'] = True
        result = pack_items(source)
        self.assert_rejected('floor_only', result, changes, source_items=source)

    def test_relocated_support_must_still_cover_top(self):
        result = pack_items([item('base', length=5800, width=2300, height=500),
                             item('top', length=5000, width=2000, height=300)])
        changes = edits(result)
        next(p for p in changes if p['item_id'] == 'base')['x'] = 96
        self.assert_rejected('unsupported', result, changes)

    def test_payload_rechecked_not_trusted_from_totals(self):
        result = pack_items([item('a', weight=1.001), item('b', weight=1)])
        result['container']['max_payload_kg'] = 2
        result['totals']['placed_weight_kg'] = 0
        self.assert_rejected('payload_limit', result, edits(result))
        result['container']['max_payload_kg'] = 2.001
        changed = validate_manual_layout(result, edits(result))
        self.assertEqual(changed['totals']['placed_weight_kg'], 2.001)

    def test_unplaced_and_dangerous_goods_unchanged(self):
        source = [item('a'), item('held', is_dg=True), item('oversize', length=100000)]
        result = pack_items(source)
        changed = validate_manual_layout(result, edits(result), source_items=source)
        self.assertEqual(changed['unplaced'], result['unplaced'])
        self.assertEqual(changed['readiness'], 'manual_compliance_hold')
        self.assertEqual(changed['totals']['manual_compliance_hold_count'], 1)
        changes = edits(result)
        changes[0]['item_id'] = 'held'
        self.assert_rejected('id_mismatch', result, changes)
        # Defensive check even against an incorrectly generated base result.
        result['placed'][0]['is_dg'] = True
        self.assert_rejected('manual_compliance_hold', result, edits(result))

    def test_no_placed_cargo_and_zero_mass(self):
        result = pack_items([item('held', is_dg=True)])
        changed = validate_manual_layout(result, [])
        self.assertIsNone(changed['mass_distribution']['center_mm'])
        self.assertEqual(changed['totals']['placed_volume_m3'], 0)
        result = pack_items([item('zero', weight=0)])
        changed = validate_manual_layout(result, edits(result))
        self.assertIsNone(changed['mass_distribution']['center_mm'])

    def test_source_mismatch_rejected(self):
        source = [item('a', orientation='yaw')]
        result = pack_items(source)
        for changed_source in ([item('b')], [item('a', weight=20)], [item('a', stackable=False)],
                               [item('a', floor_only=True)]):
            self.assert_rejected('invalid_source', result, edits(result), source_items=changed_source)

    def test_expanded_csv_ids_and_source_metadata_survive(self):
        source = parse_csv('item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nBOX,Boxes,500,400,300,1,2,true,yaw\n')
        result = pack_items(source)
        changes = edits(result)
        changes[0].update(x=1000, y=0, rotation_deg=90)
        changed = validate_manual_layout(result, changes, source_items=source)
        self.assertEqual(changed['placed'][0]['source_item_id'], 'BOX')
        self.assertEqual(changed['totals']['placed_count'], 2)
        self.assertEqual(changed['totals']['placed_volume_m3'], .12)
        self.assertEqual(changed, validate_manual_layout(result, changes, source_items=source))

    def test_invalid_source_shapes_rejected(self):
        for result in (None, [], {}, {'placed': [], 'unplaced': []}):
            with self.assertRaises(ManualLayoutError) as error:
                validate_manual_layout(result, [])
            self.assertEqual(error.exception.code, 'invalid_source')
        result = pack_items([item('a')])
        for value in (float('inf'), True, 0, -1):
            broken = deepcopy(result)
            broken['container']['max_payload_kg'] = value
            self.assert_rejected('invalid_source', broken, edits(result))


if __name__ == '__main__':
    unittest.main()
