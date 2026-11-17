from copy import deepcopy
import unittest
from optimization.allowances import pack_with_allowances, validate_with_allowances
from optimization.test_allocation import manifest, config
from optimization.test_manual_layout import edits


def profile():
    return {'name':'Measured box','inside_mm':{'length':1200,'width':600,'height':400},
            'door_mm':{'width':600,'height':400},'max_payload_kg':100,
            'dimensions_source':{'kind':'user_measurement','reference':'Fixture'}}


def settings(**overrides):
    return dict(dimension_tolerance_mm=10,horizontal_gap_mm=20,wall_clearance_mm=10,
                source_reference='Customer instruction',**overrides)


class CombinedAllowanceTests(unittest.TestCase):
    def pack(self, source=None, allocation=None, allowances=None):
        return pack_with_allowances(source or manifest(),'custom_dry',profile(),
                                    allocation if allocation is not None else config(True),
                                    allowances if allowances is not None else settings())

    def test_regions_original_boundaries_global_wall(self):
        result=self.pack()
        self.assertEqual(result['totals']['placed_count'],2)
        a,b=result['placed']
        self.assertEqual((a['x'],b['x']),(10,600))
        self.assertEqual(result['allocation']['customers'][0]['bounds_mm']['x'],[0,600])
        self.assertEqual(result['allocation']['customers'][0]['planning_envelope_bounds_mm']['x'],[10,580])
        self.assertEqual(result['allocation']['customers'][1]['planning_envelope_bounds_mm']['x'],[600,1190])
        self.assertIn('empty',result['allowances']['allocation_notice'])
        self.assertEqual(result['mass_distribution']['center_mm']['x'],555)

    def test_quota_measured_not_envelope_and_original_denominator(self):
        allocation=config(True)
        for customer in allocation['customers']:customer['volume_percent']=25
        result=self.pack(allocation=allocation,allowances={'dimension_tolerance_mm':100,'source_reference':'Fixture'})
        self.assertEqual(result['totals']['placed_count'],2)
        for customer in result['allocation']['customers']:
            self.assertAlmostEqual(customer['volume_limit_m3'],0.072)
            self.assertAlmostEqual(customer['placed_volume_m3'],0.06)
            self.assertGreater(customer['placed_envelope_volume_m3'],customer['volume_limit_m3'])
        self.assertEqual(result['totals']['placed_weight_kg'],20)

    def test_adjacent_boundary_and_outer_edge_manual_exact(self):
        result=self.pack();before=deepcopy(result);moves=edits(result)
        moves[0]['x']=70; moves[1]['x']=600
        updated=validate_with_allowances(result,moves,manifest(),settings(),config(True))
        self.assertEqual(updated['placed'][0]['x']+updated['placed'][0]['planning_envelope_mm']['dx']+20,
                         updated['placed'][1]['x'])
        moves[0]['x']=71
        with self.assertRaises(ValueError):validate_with_allowances(result,moves,manifest(),settings(),config(True))
        moves[0]['x']=70;moves[1]['x']=680
        validate_with_allowances(result,moves,manifest(),settings(),config(True))
        moves[1]['x']=681
        with self.assertRaises(ValueError):validate_with_allowances(result,moves,manifest(),settings(),config(True))
        self.assertEqual(result,before)

    def test_shared_space_quota_and_global_gap(self):
        allocation=config();allocation['customers'][0]['weight_percent']=0
        result=self.pack(allocation=allocation)
        self.assertEqual(result['totals']['placed_count'],1)
        self.assertEqual(result['unplaced'][0]['reason'],'customer_weight_quota')
        result=self.pack(allocation=config())
        validate_with_allowances(result,edits(result),manifest(),settings(),config())
        a,b=result['placed'];self.assertGreaterEqual(b['x']-a['x']-a['planning_envelope_mm']['dx'],20)

    def test_elevated_and_dg_holds_preserved(self):
        allocation=config(True)
        for index,c in enumerate(allocation['customers']):c['region']={'axis':'z','parts':2,'index':index}
        source=manifest();source[0]['is_dg']=True
        result=self.pack(source,allocation)
        self.assertEqual({p['reason'] for p in result['unplaced']},
                         {'manual_compliance_hold','allocation_elevated_region_unsupported'})
        self.assertEqual(result['totals']['placed_count'],0)

    def test_tolerance_envelope_cannot_cross_region_even_if_measured_fits(self):
        result=self.pack(allowances={'dimension_tolerance_mm':100,'source_reference':'Fixture'})
        moves=edits(result);moves[0]['x']=1
        with self.assertRaises(ValueError):
            validate_with_allowances(result,moves,manifest(),{'dimension_tolerance_mm':100,'source_reference':'Fixture'},config(True))

    def test_positive_no_stack_and_small_region_hold(self):
        allocation=config(True)
        source=manifest(quantity=2)
        result=self.pack(source,allocation)
        self.assertTrue(all(p['z']==0 and p['supported_cargo_kg']==0 for p in result['placed']))
        self.assertEqual(result['totals']['unplaced_count'],1)

    def test_y_regions_gap(self):
        allocation=config(True)
        for index,c in enumerate(allocation['customers']):c['region']={'axis':'y','parts':2,'index':index}
        source=manifest()
        for p in source:p['width_mm']=200
        result=self.pack(source,allocation)
        self.assertEqual(result['totals']['placed_count'],2)
        self.assertEqual([p['y'] for p in result['placed']],[10,300])
        validate_with_allowances(result,edits(result),source,settings(),allocation)

if __name__=='__main__':unittest.main()
