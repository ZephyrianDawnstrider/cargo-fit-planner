"""Special-handling declarations are review holds, not compatibility approval."""
import math
import unittest
from optimization.packing import pack_items, parse_csv, _hold_summary
from optimization.allocation import pack_allocated
from optimization.allowances import pack_with_allowances, validate_with_allowances
from optimization.test_allocation import manifest, config
from optimization.test_manual_layout import item, edits

HEADER='item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation'
SPECIAL=',requires_temperature_control,temperature_min_c,temperature_max_c,handling_source,dg_declaration_reference'
ROW='A,A,500,400,300,10,1,true,yaw'


class SpecialHandlingTests(unittest.TestCase):
    def test_old_csv_defaults_unknown(self):
        p=parse_csv(HEADER+'\n'+ROW+'\n')[0]
        self.assertFalse(p['requires_temperature_control'])
        self.assertIsNone(p['temperature_min_c'])
        self.assertIsNone(p['temperature_max_c'])
        self.assertEqual(p['handling_source'],'')

    def test_csv_temperature_metadata_retained_and_held(self):
        source=parse_csv(HEADER+SPECIAL+'\n'+ROW+',true,-5,12,Customer declaration,\n')
        result=pack_items(source)
        self.assertEqual(result['totals']['placed_count'],0)
        cargo=result['unplaced'][0]
        self.assertEqual(cargo['reason'],'temperature_control_manual_hold')
        self.assertEqual((cargo['temperature_min_c'],cargo['temperature_max_c']),(-5,12))
        self.assertEqual(cargo['handling_source'],'Customer declaration')
        self.assertEqual(result['totals']['manual_review_hold_count'],1)
        self.assertEqual(result['totals']['manual_compliance_hold_count'],0)

    def test_unknown_or_one_sided_limits_allowed_not_assumed_safe(self):
        for low,high in ((None,None),(-5,None),(None,12),(-1e300,1e300)):
            result=pack_items([item('a',requires_temperature_control=True,temperature_min_c=low,temperature_max_c=high)])
            self.assertEqual(result['unplaced'][0]['reason'],'temperature_control_manual_hold')

    def test_invalid_declarations_rejected(self):
        variants=[dict(requires_temperature_control='true'),dict(temperature_min_c=0),
                  dict(requires_temperature_control=True,temperature_min_c=float('nan')),
                  dict(requires_temperature_control=True,temperature_max_c=float('inf')),
                  dict(requires_temperature_control=True,temperature_min_c=True),
                  dict(requires_temperature_control=True,temperature_min_c=10,temperature_max_c=9),
                  dict(handling_source='x'*201),dict(dg_declaration_reference='not DG')]
        for extra in variants:
            with self.subTest(extra=extra),self.assertRaises(ValueError):pack_items([item('a',**extra)])
        for suffix in (',,,,,',',maybe,,,,',',false,0,,,',',true,10,9,,',',true,nan,,,'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):parse_csv(HEADER+SPECIAL+'\n'+ROW+suffix+'\n')

    def test_dual_flags_dg_priority_and_exclusive_counts(self):
        source=[item('dual',is_dg=True,requires_temperature_control=True,dg_declaration_reference='Shipper DG declaration'),
                item('temp',requires_temperature_control=True),item('regular')]
        result=pack_items(source)
        self.assertEqual(result['totals']['manual_compliance_hold_count'],1)
        self.assertEqual(result['totals']['temperature_control_manual_hold_count'],1)
        self.assertEqual(result['totals']['manual_review_hold_count'],2)
        self.assertEqual(result['totals']['placed_count'],1)
        dual=next(p for p in result['unplaced'] if p['item_id']=='dual')
        self.assertEqual(dual['reason'],'manual_compliance_hold')
        self.assertEqual(dual['dg_declaration_reference'],'Shipper DG declaration')

    def test_holds_before_quotas_or_elevated_region(self):
        source=manifest();source[0]['requires_temperature_control']=True
        cfg=config(True);cfg['customers'][0]['weight_percent']=0
        cfg['customers'][0]['region']={'axis':'z','parts':2,'index':1}
        cfg['customers'][1]['region']={'axis':'z','parts':2,'index':0}
        result=pack_allocated(source,config=cfg)
        self.assertEqual(next(p for p in result['unplaced'] if p['source_item_id']=='A')['reason'],'temperature_control_manual_hold')
        self.assertEqual(result['totals']['temperature_control_manual_hold_count'],1)

    def test_all_wrappers_and_manual_roundtrip_preserve_hold_counts(self):
        source=manifest();source[0].update(requires_temperature_control=True,handling_source='Instruction')
        for allocation in (None,config(),config(True)):
            for allowances in (None,{'horizontal_gap_mm':10,'source_reference':'Fixture'}):
                with self.subTest(allocation=allocation,allowances=allowances):
                    result=pack_with_allowances(source,allocation=allocation,allowances=allowances)
                    self.assertEqual(result['totals']['placed_count'],1)
                    self.assertEqual(result['totals']['temperature_control_manual_hold_count'],1)
                    updated=validate_with_allowances(result,edits(result),source,allowances,allocation)
                    self.assertEqual(updated['totals']['manual_review_hold_count'],1)
                    self.assertEqual(updated['readiness'],'manual_compliance_hold')
                    self.assertEqual(updated['unplaced'][0]['handling_source'],'Instruction')

    def test_csv_expansion_dg_reference_and_flag(self):
        source=parse_csv(HEADER+',is_dg'+SPECIAL+'\n'+ROW+',true,true,,,Customer instruction,DG ref 22\n')
        self.assertEqual(source[0]['dg_declaration_reference'],'DG ref 22')
        self.assertEqual(pack_items(source)['unplaced'][0]['reason'],'manual_compliance_hold')

if __name__=='__main__':unittest.main()
