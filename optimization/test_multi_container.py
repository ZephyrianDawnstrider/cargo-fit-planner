from copy import deepcopy
from unittest.mock import patch
import unittest
from .multi_container import pack_multiple
from . import multi_container
from .packing import pack_items, parse_csv
from .test_manual_layout import item


def equipment(payload=100):
    return {'name':'Measured fixture','inside_mm':{'length':1000,'width':1000,'height':1000},
            'door_mm':{'width':1000,'height':1000},'max_payload_kg':payload,
            'dimensions_source':{'kind':'user_measurement','reference':'Fixture'}}


def box(ident,**kwargs):
    defaults=dict(length=900,width=900,height=900)
    defaults.update(kwargs)
    return item(ident,**defaults)


class MultiContainerTests(unittest.TestCase):
    def pack(self,source,**kwargs):
        return pack_multiple(source,'custom_dry',custom_profile=equipment(),**kwargs)

    def test_count_conservation_unique_ids_and_no_duplicate_unplaced(self):
        source=[box(str(i)) for i in range(4)];before=deepcopy(source)
        result=self.pack(source,max_containers=3)
        self.assertEqual(source,before)
        self.assertEqual(result['totals']['placed_count'],3)
        self.assertEqual(result['totals']['unplaced_count'],1)
        ids=[p['item_id'] for load in result['loads'] for p in load['placed']]+[p['item_id'] for p in result['unplaced']]
        self.assertCountEqual(ids,[p['item_id'] for p in source]);self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(result['planning']['stop_reason'],'container_limit_reached')
        for index,load in enumerate(result['loads'],1):
            self.assertEqual(load['unplaced'],[]);self.assertEqual(load['load_number'],index)
            self.assertEqual(load['totals']['input_count'],len(load['placed']))
            self.assertTrue(all(p['load_number']==index for p in load['placed']))

    def test_holds_once_never_retried(self):
        source=[box('a'),box('b'),box('dg',is_dg=True),box('temp',requires_temperature_control=True)]
        with patch.object(multi_container,'pack_items',wraps=pack_items) as call:
            result=self.pack(source)
        self.assertEqual(call.call_count,2)
        self.assertEqual([p['item_id'] for p in call.call_args_list[1].args[0]],['b'])
        self.assertEqual(result['totals']['manual_review_hold_count'],2)
        self.assertTrue(all(load['totals']['manual_review_hold_count']==0 for load in result['loads']))
        self.assertEqual(result['readiness'],'manual_compliance_hold')

    def test_impossible_removed_before_retry(self):
        source=[box('a'),box('b'),box('large',length=2000),box('heavy',weight=101)]
        with patch.object(multi_container,'pack_items',wraps=pack_items) as call:result=self.pack(source)
        self.assertEqual(call.call_count,2)
        self.assertEqual([p['item_id'] for p in call.call_args_list[1].args[0]],['b'])
        self.assertEqual({p['reason'] for p in result['unplaced']},{'payload_limit','door_or_container_dimensions'})

    def test_no_empty_containers_all_hold_or_impossible(self):
        result=self.pack([box('dg',is_dg=True),box('large',length=2000)],max_containers=5)
        self.assertEqual(result['loads'],[]);self.assertEqual(result['totals']['unplaced_count'],2)
        self.assertEqual(result['container']['name'],'Measured fixture')

    def test_no_progress_stops_without_empty_load(self):
        with patch('optimization.packing._candidate',return_value=(None,False)) as candidate:
            result=self.pack([box('a')],max_containers=5)
        self.assertEqual(candidate.call_count,1);self.assertEqual(result['loads'],[])
        self.assertEqual(result['planning']['stop_reason'],'no_progress')

    def test_shared_budget_not_reset_across_loads(self):
        seen=[]
        def spend(item,placed,budget,container):
            seen.append(id(budget))
            if not budget[0]:return None,True
            budget[0]-=1
            if placed:return None,False
            return {'x':0,'y':0,'z':0,'dx':900,'dy':900,'dz':900,'orientation':'fixed'},False
        with patch.object(multi_container,'MAX_CANDIDATE_CHECKS_PER_PACK',3),patch('optimization.packing._candidate',side_effect=spend):
            result=self.pack([box('a'),box('b')],max_containers=5)
        self.assertEqual(len(set(seen)),1)
        self.assertEqual(len(result['loads']),2)
        self.assertEqual(result['planning']['candidate_checks_used'],3)

    def test_budget_exhaustion_stops_and_preserves_units(self):
        with patch.object(multi_container,'MAX_CANDIDATE_CHECKS_PER_PACK',0):
            result=self.pack([box('a'),box('b')],max_containers=5)
        self.assertEqual(result['loads'],[])
        self.assertEqual(result['planning']['stop_reason'],'candidate_budget_exhausted')
        self.assertEqual(result['totals']['unplaced_count'],2)

    def test_internal_budget_hook_fail_closed(self):
        for budget in ([100001],[-1],[True],[],[1,2],1):
            with self.subTest(budget=budget),self.assertRaises(ValueError):pack_items([box('a')],_candidate_budget=budget)

    def test_custom_payload_is_per_container(self):
        source=[box('a',length=100,width=100,height=100,weight=70),box('b',length=100,width=100,height=100,weight=70)]
        result=self.pack(source)
        self.assertEqual(len(result['loads']),2);self.assertEqual(result['totals']['placed_weight_kg'],140)
        self.assertEqual([l['totals']['placed_weight_kg'] for l in result['loads']],[70,70])

    def test_positive_allowances_and_measured_mass(self):
        source=[box('a'),box('b')]
        result=self.pack(source,allowances={'dimension_tolerance_mm':10,'wall_clearance_mm':20,'source_reference':'Fixture'})
        self.assertEqual(len(result['loads']),2)
        for load in result['loads']:
            p=load['placed'][0]
            self.assertEqual((p['x'],p['y'],p['z']),(20,20,0))
            self.assertEqual(p['dx'],900);self.assertEqual(p['planning_envelope_mm']['dx'],910)
            self.assertEqual(load['mass_distribution']['center_mm']['x'],470)
        self.assertAlmostEqual(result['totals']['placed_volume_m3'],1.458)

    def test_rated_stacking_preserved_and_capacity_not_reused_across_loads(self):
        source=[box('base',height=500,max_supported_load_kg=10,stacking_rating_source='Fixture'),
                box('middle',height=300),box('top',height=200)]
        result=self.pack(source)
        self.assertEqual(len(result['loads']),2)
        self.assertEqual(result['loads'][0]['placed'][0]['supported_cargo_kg'],10)
        self.assertEqual(result['loads'][1]['placed'][0]['supported_cargo_kg'],0)

    def test_input_limits_profiles_allocations(self):
        for count in (0,6,True,2.0,'2'):
            with self.assertRaises(ValueError):self.pack([box('a')],max_containers=count)
        with self.assertRaises(ValueError):self.pack([box(str(i)) for i in range(101)])
        with self.assertRaises(ValueError):self.pack([box('a')],allocation={})
        with self.assertRaises(ValueError):pack_multiple([box('a')],'unknown')
        with self.assertRaises(ValueError):self.pack([box('a')],allowances={'horizontal_gap_mm':1})

    def test_expanded_csv_ids_stay_stable(self):
        source=parse_csv('item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nA,A,900,900,900,10,3,true,yaw\n')
        result=self.pack(source,max_containers=3)
        self.assertEqual([l['placed'][0]['item_id'] for l in result['loads']],['A-001','A-002','A-003'])

if __name__=='__main__':unittest.main()
