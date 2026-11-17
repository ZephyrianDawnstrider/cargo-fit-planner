from copy import deepcopy
import unittest
from optimization.allowances import pack_with_allowances, validate_with_allowances
from optimization.packing import pack_items
from optimization.test_manual_layout import item, edits


def settings(**values):
    return {'dimension_tolerance_mm':10, 'horizontal_gap_mm':20, 'wall_clearance_mm':30,
            'roof_clearance_mm':40, 'door_clearance_mm':50, 'source_reference':'Measured loading instruction', **values}


def profile(**changes):
    value={'name':'Test equipment','inside_mm':{'length':1100,'width':500,'height':500},
           'door_mm':{'width':500,'height':500},'max_payload_kg':100,
           'dimensions_source':{'kind':'user_measurement','reference':'Fixture'}}
    value.update(changes)
    return value


class AllowanceTests(unittest.TestCase):
    def test_default_identical(self):
        source=[item('a')]
        self.assertEqual(pack_with_allowances(source),pack_items(source))

    def test_gross_mass_envelope_and_gap(self):
        source=[item('a'),item('b')]; old=deepcopy(source)
        result=pack_with_allowances(source,'custom_dry',profile(),allowances=settings())
        self.assertEqual(source,old)
        self.assertEqual(result['totals']['placed_count'],2)
        a,b=result['placed']
        self.assertEqual((a['x'],b['x']),(30,560))
        self.assertEqual(a['dx'],500)
        self.assertEqual(a['planning_envelope_mm'],{'dx':510,'dy':410,'dz':310})
        self.assertEqual(result['mass_distribution']['center_mm']['x'],545)
        self.assertEqual(result['totals']['placed_volume_m3'],0.12)
        self.assertEqual(result['container']['inside_mm']['length'],1100)

    def test_manual_roundtrip_and_input_immutability(self):
        source=[item('a'),item('b')]; cfg=settings()
        result=pack_with_allowances(source,allowances=cfg); old=deepcopy(result)
        moved=edits(result)
        for p in moved: p['x']+=100
        updated=validate_with_allowances(result,moved,source,cfg)
        self.assertEqual(result,old)
        self.assertEqual(updated['placed'][0]['x'],130)
        self.assertEqual(updated['placed'][0]['dx'],500)

    def test_gap_infringement_rejected_even_without_gross_overlap(self):
        source=[item('a'),item('b')];cfg=settings()
        result=pack_with_allowances(source,'custom_dry',profile(),allowances=cfg)
        moved=edits(result); moved[1]['x']=540
        with self.assertRaises(ValueError): validate_with_allowances(result,moved,source,cfg)

    def test_wall_infringement(self):
        source=[item('a')];cfg=settings();result=pack_with_allowances(source,allowances=cfg)
        moved=edits(result);moved[0]['x']=29
        with self.assertRaisesRegex(ValueError, "at least 30 mm from the side/end walls"):
            validate_with_allowances(result,moved,source,cfg)

    def test_all_positive_modes_disallow_stacking(self):
        for field in ('dimension_tolerance_mm','horizontal_gap_mm','wall_clearance_mm','roof_clearance_mm','door_clearance_mm'):
            cfg={field:1,'source_reference':'Fixture'}
            source=[item('a'),item('b')]
            result=pack_with_allowances(source,'custom_dry',profile(inside_mm={'length':510,'width':410,'height':1000},door_mm={'width':410,'height':900}),allowances=cfg)
            self.assertLessEqual(result['totals']['placed_count'],1)

    def test_rotation_envelope(self):
        source=[item('a',orientation='yaw')];cfg=settings()
        result=pack_with_allowances(source,allowances=cfg)
        moved=edits(result);moved[0]['rotation_deg']=90
        updated=validate_with_allowances(result,moved,source,cfg)
        self.assertEqual(updated['placed'][0]['planning_envelope_mm'],{'dx':410,'dy':510,'dz':310})
        self.assertEqual(updated['placed'][0]['dx'],400)

    def test_door_deduction_once_and_no_gap_charged_to_door(self):
        cfg={'door_clearance_mm':10,'horizontal_gap_mm':20,'source_reference':'Fixture'}
        result=pack_with_allowances([item('a',width=490)],'custom_dry',profile(),allowances=cfg)
        self.assertEqual(result['totals']['placed_count'],1)
        result=pack_with_allowances([item('a',width=491)],'custom_dry',profile(),allowances=cfg)
        self.assertEqual(result['totals']['placed_count'],0)

    def test_gap_not_required_at_outer_wall(self):
        cfg={'horizontal_gap_mm':20,'source_reference':'Fixture'}
        result=pack_with_allowances([item('a',length=1100,width=500)],'custom_dry',profile(),allowances=cfg)
        self.assertEqual(result['totals']['placed_count'],1)

    def test_bad_config_and_combination(self):
        for cfg in ({'horizontal_gap_mm':1},{'wall_clearance_mm':True},{'roof_clearance_mm':101},{'unknown':0}):
            with self.subTest(cfg=cfg),self.assertRaises(ValueError):pack_with_allowances([item('a')],allowances=cfg)
        with self.assertRaisesRegex(ValueError,'allocations'):
            pack_with_allowances([item('a')],allocation={},allowances=settings())

    def test_source_or_settings_change_rejected(self):
        source=[item('a')];cfg=settings();result=pack_with_allowances(source,allowances=cfg)
        with self.assertRaises(ValueError):validate_with_allowances(result,edits(result),source,settings(roof_clearance_mm=50))
        with self.assertRaises(ValueError):validate_with_allowances(result,edits(result),source,None)
        source[0]['weight_kg']=99
        with self.assertRaises(ValueError):validate_with_allowances(result,edits(result),source,cfg)

    def test_manual_boundary_uses_envelope_not_measured_box(self):
        source=[item('a')];cfg=settings()
        result=pack_with_allowances(source,'custom_dry',profile(),allowances=cfg)
        moved=edits(result);moved[0]['x']=560
        validate_with_allowances(result,moved,source,cfg)
        moved[0]['x']=561
        with self.assertRaises(ValueError):validate_with_allowances(result,moved,source,cfg)

    def test_roof_and_dimension_tolerance_hold_tall_cargo(self):
        cfg={'roof_clearance_mm':10,'dimension_tolerance_mm':10,'source_reference':'Fixture'}
        result=pack_with_allowances([item('a',height=480)],'custom_dry',profile(),allowances=cfg)
        self.assertEqual(result['totals']['placed_count'],1)
        result=pack_with_allowances([item('a',height=481)],'custom_dry',profile(),allowances=cfg)
        self.assertEqual(result['totals']['placed_count'],0)

    def test_zero_allowances_preserve_customer_allocations(self):
        from optimization.test_allocation import manifest, config
        from optimization.allocation import pack_allocated
        source=manifest();allocation=config()
        result=pack_with_allowances(source,allocation=allocation,allowances={'horizontal_gap_mm':0})
        self.assertEqual(result,pack_allocated(source,config=allocation))
        updated=validate_with_allowances(result,edits(result),source,allocation=allocation)
        self.assertEqual(updated['allocation'],result['allocation'])

    def test_dg_and_original_flags_preserved(self):
        source=[item('a',is_dg=True),item('b')]
        result=pack_with_allowances(source,allowances=settings())
        self.assertEqual(result['unplaced'][0]['reason'],'manual_compliance_hold')
        self.assertEqual(result['unplaced'][0]['length_mm'],500)
        self.assertTrue(result['placed'][0]['stackable'])
        self.assertTrue(result['placed'][0]['planning_floor_only'])

if __name__=='__main__':unittest.main()
