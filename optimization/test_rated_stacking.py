"""Declared ratings constrain static supported gross mass, not certification."""
import unittest
from optimization.packing import pack_items, parse_csv, _stacking_violation
from optimization.manual_layout import validate_manual_layout, ManualLayoutError
from optimization.test_manual_layout import item, edits


def rated(ident, limit=100, **kw):
    return item(ident,max_supported_load_kg=limit,stacking_rating_source='User-reported package label',**kw)


def at(cargo,x=0,y=0,z=0):
    return dict(cargo,x=x,y=y,z=z,dx=cargo['length_mm'],dy=cargo['width_mm'],dz=cargo['height_mm'])


class RatedStackingTests(unittest.TestCase):
    def test_unknown_and_zero_never_support(self):
        for capacity in (None,0):
            result=pack_items([item('base',length=5896,width=2350,height=400,max_supported_load_kg=capacity),item('top',weight=0)])
            self.assertEqual(result['totals']['placed_count'],1)

    def test_exact_rating_and_overage(self):
        for weight, count in ((10,2),(10.001,1)):
            result=pack_items([rated('base',10,length=5896,width=2350,height=400),item('top',weight=weight)])
            self.assertEqual(result['totals']['placed_count'],count)

    def test_cumulative_descendants(self):
        boxes=[at(rated('base',19),z=0),at(rated('middle',100),z=300),at(item('top'),z=600)]
        self.assertEqual(_stacking_violation(boxes)[0],'support_load_limit')
        boxes[0]['max_supported_load_kg']=20
        self.assertIsNone(_stacking_violation(list(reversed(boxes))))

    def test_siblings_and_grandchild(self):
        boxes=[at(rated('base',29,length=1000,width=1000)),
               at(rated('left',100),z=300),at(item('right'),x=500,z=300),at(item('top'),z=600)]
        self.assertEqual(_stacking_violation(boxes)[2],['base'])
        boxes[0]['max_supported_load_kg']=30
        self.assertIsNone(_stacking_violation(boxes))

    def test_engine_respects_ancestor_capacity(self):
        source=[rated('base',19,length=5896,width=2350,height=400),
                rated('middle',100,length=5896,width=2350,height=300),
                item('top',length=5896,width=2350,height=200)]
        result=pack_items(source)
        self.assertEqual(result['totals']['placed_count'],2)
        self.assertEqual(result['unplaced'][0]['item_id'],'top')
        self.assertEqual(result['placed'][0]['supported_cargo_kg'],10)

    def test_manual_cumulative_violation(self):
        source=[rated('base',19,length=1000,width=1000),rated('middle'),item('top')]
        result=pack_items(source)
        changes=[dict(item_id=p['item_id'],x=0,y=0,z={'base':0,'middle':300,'top':600}[p['item_id']],rotation_deg=0) for p in result['placed']]
        with self.assertRaises(ManualLayoutError) as ctx:validate_manual_layout(result,changes,source_items=source)
        self.assertEqual(ctx.exception.code,'support_load_limit')

    def test_csv_blank_unknown_and_source_required(self):
        header='item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,max_supported_load_kg,stacking_rating_source\n'
        row='a,A,100,100,100,1,2,true,yaw'
        self.assertIsNone(parse_csv(header+row+',,\n')[0]['max_supported_load_kg'])
        parsed=parse_csv(header+row+',5,label\n')
        self.assertEqual([p['max_supported_load_kg'] for p in parsed],[5,5])
        for tail in (',5,',',-1,label',',nan,label',',inf,label',',1.0001,label'):
            with self.assertRaises(ValueError):parse_csv(header+row+tail+'\n')

    def test_direct_inputs_require_provenance_and_finite_rating(self):
        for extra in ({'max_supported_load_kg':1}, {'max_supported_load_kg':float('inf')},
                      {'max_supported_load_kg':True}, {'stacking_rating_source':'x'*201}):
            with self.assertRaises(ValueError):pack_items([item('a',**extra)])

    def test_floor_only_base_can_support_but_fixed_and_floor_top_rules_hold(self):
        source=[rated('base',100,length=5896,width=2350,height=400,floor_only=True),item('top',floor_only=True)]
        self.assertEqual(pack_items(source)['totals']['placed_count'],1)
        source[1]['floor_only']=False
        result=pack_items(source)
        self.assertEqual(result['totals']['placed_count'],2)
        changes=edits(result);changes[0]['rotation_deg']=90
        with self.assertRaises(ManualLayoutError):validate_manual_layout(result,changes,source_items=source)

if __name__=='__main__':unittest.main()
