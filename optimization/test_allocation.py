from copy import deepcopy
import unittest

from optimization.allocation import pack_allocated, validate_allocation
from optimization.packing import pack_items, parse_csv
from optimization.manual_layout import validate_manual_layout


def manifest(weight=10, quantity=1):
    return parse_csv('item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n'
                     f'A,A,500,400,300,{weight},{quantity},true,yaw\nB,B,500,400,300,{weight},1,true,yaw\n')


def customer(ident, source, percent=50, region=None):
    return dict(id=ident, source_item_ids=[source], weight_percent=percent, volume_percent=percent, region=region)


def config(regions=False):
    return {'customers': [customer('Alice', 'A', region={'axis':'x','parts':2,'index':0} if regions else None),
                          customer('Bob', 'B', region={'axis':'x','parts':2,'index':1} if regions else None)]}


class AllocationTests(unittest.TestCase):
    def test_no_config_unchanged(self):
        self.assertEqual(pack_allocated(manifest()), pack_items(manifest()))

    def test_shared_quantity_and_original_measurements(self):
        source = manifest(quantity=3)
        before = deepcopy(source)
        result = pack_allocated(source, config=config())
        self.assertEqual(source, before)
        self.assertEqual(result['totals']['placed_count'], 4)
        self.assertEqual([p['customer_id'] for p in result['placed']].count('Alice'), 3)
        self.assertTrue(all(p['weight_kg'] == 10 and p['length_mm'] == 500 for p in result['placed']))

    def test_reserved_regions_and_mass_offset(self):
        result = pack_allocated(manifest(), config=config(True))
        by = {p['customer_id']: p for p in result['placed']}
        self.assertEqual(by['Bob']['x'], 2948)
        self.assertEqual(result['mass_distribution']['center_mm']['x'], 1724)
        self.assertEqual(result['container']['id'], '20std')

    def test_weight_and_volume_caps(self):
        cfg = config()
        cfg['customers'][0]['weight_percent'] = 0
        cfg['customers'][1]['volume_percent'] = 0
        result = pack_allocated(manifest(), config=cfg)
        self.assertEqual(result['totals']['placed_count'], 0)
        self.assertEqual({p['reason'] for p in result['unplaced']}, {'customer_weight_quota', 'customer_volume_quota'})

    def test_weight_cap_applies_quantity_group(self):
        cfg = config()
        cfg['customers'][0]['weight_percent'] = 1
        result = pack_allocated(manifest(weight=200, quantity=2), config=cfg)
        self.assertEqual(sum(p['customer_id']=='Alice' for p in result['placed']), 1)
        self.assertEqual(result['unplaced'][0]['reason'], 'customer_weight_quota')

    def test_elevated_z_hold(self):
        cfg = config(True)
        for i, c in enumerate(cfg['customers']):
            c['region'] = {'axis': 'z', 'parts': 2, 'index': i}
        result = pack_allocated(manifest(), config=cfg)
        self.assertEqual(result['totals']['placed_count'], 1)
        self.assertEqual(result['unplaced'][0]['reason'], 'allocation_elevated_region_unsupported')

    def test_manual_leaving_region_rejected(self):
        cfg = config(True)
        result = pack_allocated(manifest(), config=cfg)
        original = deepcopy(result)
        result['placed'][0]['x'] = 3000
        with self.assertRaisesRegex(ValueError, 'reserved region'):
            validate_allocation(result, cfg)
        self.assertEqual(original['placed'][0]['x'], 0)

    def test_manual_roundtrip(self):
        source, cfg = manifest(), config(True)
        result = pack_allocated(source, config=cfg)
        moves = [dict(item_id=p['item_id'], x=int(p['x'])+10, y=int(p['y']), z=int(p['z']), rotation_deg=p['rotation_deg']) for p in result['placed']]
        updated = validate_manual_layout(result, moves, source_items=source)
        final = validate_allocation(updated, cfg)
        self.assertEqual(final['placed'][0]['customer_id'], 'Alice')
        self.assertEqual(final['allocation']['customers'][0]['placed_count'], 1)

    def test_bad_config_rejected(self):
        variants = []
        for key,value in [('weight_percent',51),('volume_percent',float('nan')),('id','Bob'),('source_item_ids',['B']),('source_item_ids',['unknown'])]:
            cfg = config(); cfg['customers'][0][key] = value; variants.append(cfg)
        cfg = config(); cfg['customers'] = cfg['customers'][:1]; variants.append(cfg)
        cfg = config(True); cfg['customers'][0]['region']=None; variants.append(cfg)
        cfg = config(True); cfg['customers'][1]['region']['index']=0; variants.append(cfg)
        cfg = config(); cfg['wall_clearance_mm']=1; variants.append(cfg)
        cfg = config(); cfg['dimension_tolerance_mm']=True; variants.append(cfg)
        for cfg in variants:
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                pack_allocated(manifest(), config=cfg)

    def test_dg_hold_preserved(self):
        source = manifest(); source[0]['is_dg'] = True
        result = pack_allocated(source, config=config())
        self.assertEqual(result['readiness'], 'manual_compliance_hold')
        self.assertEqual(result['totals']['manual_compliance_hold_count'], 1)

    def test_y_region_respects_real_door(self):
        source = manifest(); source[0].update(width_mm=1200, orientation='fixed')
        cfg = config(True)
        for i,c in enumerate(cfg['customers']): c['region']={'axis':'y','parts':2,'index':i}
        result=pack_allocated(source, config=cfg)
        self.assertEqual(result['unplaced'][0]['source_item_id'], 'A')

    def test_custom_partition_rounding_and_payload(self):
        profile={'name':'Measured box','inside_mm':{'length':1001,'width':800,'height':600},
                 'door_mm':{'width':800,'height':600},'max_payload_kg':20,
                 'dimensions_source':{'kind':'user_measurement','reference':'Test fixture'}}
        result=pack_allocated(manifest(), 'custom_dry', profile, config(True))
        self.assertEqual(result['totals']['placed_count'],2)
        self.assertEqual(result['allocation']['customers'][0]['bounds_mm']['x'],[0,500])
        self.assertEqual(result['allocation']['customers'][1]['bounds_mm']['x'],[500,1001])
        self.assertEqual(result['totals']['placed_weight_kg'],20)

    def test_missing_parsed_source_rejected(self):
        source=manifest(); del source[0]['source_item_id']
        with self.assertRaisesRegex(ValueError,'source_item_id'):
            pack_allocated(source,config=config())

    def test_no_backfill_is_reported(self):
        source=manifest(); source[0]['length_mm']=100000
        result=pack_allocated(source,config=config())
        self.assertIn('not backfilled',result['allocation']['notice'])

    def test_tiny_fractional_weight_cap_floored(self):
        cfg=config(); cfg['customers'][0]['weight_percent']=0.000001
        result=pack_allocated(manifest(), config=cfg)
        self.assertEqual(result['allocation']['customers'][0]['weight_limit_kg'],0)

if __name__ == '__main__': unittest.main()
