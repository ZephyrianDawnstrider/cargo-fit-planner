"""Independent geometry and input checks for the packing MVP."""

import json
import unittest

from optimization.packing import CsvValidationError, DEMO_CSV, pack_items, parse_csv


def item(item_id, *, length=500, width=400, height=300, weight=10, stackable=True, orientation="fixed"):
    return {
        "item_id": item_id, "name": item_id, "length_mm": length, "width_mm": width,
        "height_mm": height, "weight_kg": weight, "stackable": stackable,
        "orientation": orientation,
    }


class PackingTests(unittest.TestCase):
    def test_csv_expands_quantity_with_stable_unit_ids_and_demo_is_packable(self):
        items = parse_csv(DEMO_CSV)
        self.assertEqual([x["item_id"] for x in items[:4]], ["BOX-001", "BOX-002", "BOX-003", "BOX-004"])
        result = pack_items(items)
        self.assertEqual(result["totals"]["input_count"], 5)
        self.assertEqual(result["totals"]["placed_count"] + result["totals"]["unplaced_count"], 5)
        json.dumps(result, allow_nan=False)

    def test_repeated_calls_are_deterministic(self):
        items = [item("b", length=700), item("a", length=600), item("c", length=800)]
        self.assertEqual(pack_items(items), pack_items(items))

    def test_yaw_rotation_can_make_a_door_fit(self):
        result = pack_items([item("yaw", length=1000, width=2400, orientation="yaw")])
        self.assertEqual(result["totals"]["placed_count"], 1)
        self.assertEqual(result["placed"][0]["orientation"], "yaw")
        self.assertEqual(result["placed"][0]["rotation_deg"], 90)
        self.assertLessEqual(result["placed"][0]["dy"], 2340)

    def test_payload_limit_leaves_item_unplaced(self):
        result = pack_items([item("heavy-a", weight=16000), item("heavy-b", weight=16000)])
        self.assertEqual(result["unplaced"][0]["reason"], "payload_limit")
        self.assertEqual(result["totals"]["placed_weight_kg"], 16000)

    def test_payload_boundary_uses_exact_gram_units(self):
        at_limit = pack_items([item("a", weight=14065.125), item("b", weight=14064.875)])
        self.assertEqual(at_limit["totals"]["placed_weight_kg"], 28130)
        self.assertEqual(at_limit["totals"]["unplaced_count"], 0)
        over_limit = pack_items([item("a", weight=14065.125), item("b", weight=14064.876)])
        self.assertEqual(over_limit["totals"]["placed_weight_kg"], 14065.125)
        self.assertEqual(over_limit["unplaced"][0]["reason"], "payload_limit")

    def test_direct_unit_count_limit(self):
        with self.assertRaisesRegex(ValueError, "100-unit limit"):
            pack_items([item(f"i{i}") for i in range(101)])

    def test_nonstackable_item_cannot_support_another_item(self):
        items = [item("base", length=5800, width=2300, height=1000, stackable=False),
                 item("top", length=5800, width=2300, height=1000)]
        result = pack_items(items)
        by_id = {x["item_id"]: x for x in result["placed"]}
        self.assertEqual(result["totals"]["placed_count"], 1)
        self.assertEqual(by_id["base"]["z"], 0)
        self.assertEqual(result["unplaced"][0]["item_id"], "top")

    def test_stackable_full_footprint_support_is_allowed(self):
        items = [item("base", length=5800, width=2300, height=500),
                 item("top", length=5000, width=2000, height=300)]
        result = pack_items(items)
        by_id = {x["item_id"]: x for x in result["placed"]}
        self.assertEqual(set(by_id), {"base", "top"})
        self.assertEqual(by_id["top"]["z"], by_id["base"]["dz"])
        self.assertGreaterEqual(by_id["top"]["x"], by_id["base"]["x"])
        self.assertLessEqual(by_id["top"]["x"] + by_id["top"]["dx"], by_id["base"]["x"] + by_id["base"]["dx"])
        self.assertGreaterEqual(by_id["top"]["y"], by_id["base"]["y"])
        self.assertLessEqual(by_id["top"]["y"] + by_id["top"]["dy"], by_id["base"]["y"] + by_id["base"]["dy"])
        for cargo in result["placed"]:
            if cargo["z"] > 0:
                supporters = [p for p in result["placed"] if p["stackable"]
                              and p["z"] + p["dz"] == cargo["z"]
                              and p["x"] <= cargo["x"] and cargo["x"] + cargo["dx"] <= p["x"] + p["dx"]
                              and p["y"] <= cargo["y"] and cargo["y"] + cargo["dy"] <= p["y"] + p["dy"]]
                self.assertTrue(supporters, f"{cargo['item_id']} has no single full-footprint support")

    def test_placement_is_contained_nonoverlapping_and_within_payload(self):
        result = pack_items([item(str(i), length=1500, width=1000, height=1000, weight=100) for i in range(12)])
        inner = result["container"]["inside_mm"]
        placed = result["placed"]
        for current in placed:
            self.assertGreaterEqual(current["x"], 0)
            self.assertGreaterEqual(current["y"], 0)
            self.assertGreaterEqual(current["z"], 0)
            self.assertLessEqual(current["x"] + current["dx"], inner["length"])
            self.assertLessEqual(current["y"] + current["dy"], inner["width"])
            self.assertLessEqual(current["z"] + current["dz"], inner["height"])
        for i, first in enumerate(placed):
            for second in placed[i + 1:]:
                overlaps = (first["x"] < second["x"] + second["dx"] and second["x"] < first["x"] + first["dx"]
                            and first["y"] < second["y"] + second["dy"] and second["y"] < first["y"] + first["dy"]
                            and first["z"] < second["z"] + second["dz"] and second["z"] < first["z"] + first["dz"])
                self.assertFalse(overlaps)
        self.assertLessEqual(result["totals"]["placed_weight_kg"], 28130)
        original_ids = [str(i) for i in range(12)]
        output_ids = [x["item_id"] for x in result["placed"] + result["unplaced"]]
        self.assertCountEqual(output_ids, original_ids)
        self.assertEqual(len(output_ids), len(set(output_ids)))
        self.assertEqual(result["totals"]["placed_weight_kg"], sum(x["weight_kg"] for x in result["placed"]))

    def test_fixed_orientation_and_door_height_are_enforced(self):
        result = pack_items([
            item("needs-yaw", length=1000, width=2400, orientation="fixed"),
            item("too-tall-for-door", height=2293),
        ])
        self.assertEqual(result["totals"]["placed_count"], 0)
        self.assertTrue(all(x["reason"] == "door_or_container_dimensions" for x in result["unplaced"]))

    def test_extremely_heavy_finite_item_is_unplaced_without_overflow(self):
        result = pack_items([item("astronomical", weight=1e308)])
        self.assertEqual(result["placed"], [])
        self.assertEqual(result["unplaced"][0]["reason"], "payload_limit")

    def test_invalid_csv_and_direct_items_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate value"):
            parse_csv("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\na,A,1,1,1,1,1,true,fixed\na,B,1,1,1,1,1,true,fixed\n")
        with self.assertRaisesRegex(ValueError, "finite"):
            pack_items([item("bad", weight=float("nan"))])
        for bad_dimension in (True, float("nan"), float("inf")):
            with self.subTest(bad_dimension=bad_dimension), self.assertRaises(ValueError):
                pack_items([item("bad", length=bad_dimension)])
        with self.assertRaisesRegex(ValueError, "whole number of millimetres"):
            pack_items([item("bad", length=0)])
        with self.assertRaisesRegex(ValueError, "orientation"):
            pack_items([item("bad", orientation="tip")])
        with self.assertRaisesRegex(ValueError, "orientation"):
            pack_items([item("bad", orientation=[])])
        with self.assertRaisesRegex(ValueError, "at least one cargo item"):
            parse_csv("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n")
        with self.assertRaisesRegex(ValueError, "at least one cargo item"):
            pack_items([])

    def test_csv_schema_and_measurement_validation(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        valid = "a,A,10,10,10,1,1,true,fixed"
        for quantity in ("0", "-1", "1.5"):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(ValueError, "quantity"):
                parse_csv(f"{header}\na,A,10,10,10,1,{quantity},true,fixed\n")
        for dimension in ("NaN", "Infinity", "0.5"):
            with self.subTest(dimension=dimension), self.assertRaises(ValueError):
                parse_csv(f"{header}\na,A,{dimension},10,10,1,1,true,fixed\n")
        with self.assertRaisesRegex(ValueError, "missing"):
            parse_csv("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable\n" + valid + "\n")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            parse_csv(header + ",extra\n" + valid + ",x\n")

    def test_csv_bom_and_leading_zero_quantity_are_accepted(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        rows = parse_csv("\ufeff" + header + "\na,A,10,10,10,1,0002,true,fixed\n")
        self.assertEqual([row["item_id"] for row in rows], ["a-001", "a-002"])

    def test_csv_validation_aggregates_rows_and_reports_physical_lines(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        source = (
            header + "\n"
            + 'a,"two-line\nname",0,NaN,-1,Inf,1.5,maybe,tip\n'
            + "b,B,1,1,1,1,1,maybe,tip\n"
        )
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(source)
        error = caught.exception
        self.assertGreaterEqual(len(error.errors), 8)
        self.assertTrue(all(set(entry) == {"row", "field", "message"} for entry in error.errors))
        self.assertEqual(
            {(entry["row"], entry["field"]) for entry in error.errors if entry["field"] in {"length_mm", "width_mm", "height_mm", "weight_kg", "quantity", "stackable", "orientation"}},
            {(3, "length_mm"), (3, "width_mm"), (3, "height_mm"), (3, "weight_kg"), (3, "quantity"),
             (3, "stackable"), (3, "orientation"), (4, "stackable"), (4, "orientation")},
        )
        self.assertIn("row 3 length_mm:", str(error))
        self.assertIn("whole number", str(error))

    def test_csv_header_shape_row_width_and_malformed_syntax_are_structured(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        duplicate_header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,item_id"
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(duplicate_header + "\n")
        self.assertTrue(any(error["field"] == "item_id" for error in caught.exception.errors))
        self.assertTrue(any(error["field"] == "orientation" for error in caught.exception.errors))
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + "\na,A,1,1,1,1,1,true,fixed,extra\n")
        self.assertTrue(any(error["row"] == 2 and error["field"] == "columns" for error in caught.exception.errors))
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + '\na,"unterminated')
        self.assertEqual(caught.exception.errors[0]["field"], "csv")
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + "\na,A,1,1,1,1,1,true\n")
        self.assertTrue(any(error["row"] == 2 and error["field"] == "orientation" for error in caught.exception.errors))

    def test_csv_limits_truncate_details_and_huge_quantity_does_not_escape(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + "\n" + (",,,,,,,,\n" * 10))
        self.assertEqual(len(caught.exception.errors), 20)
        self.assertTrue(caught.exception.truncated)
        self.assertIn("further errors omitted", str(caught.exception))
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + "\na,A,1,1,1,1," + ("9" * 5000) + ",true,fixed\n")
        self.assertTrue(any(error["field"] == "quantity" for error in caught.exception.errors))
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv(header + "\na,A,1,1,1,1,1,true,fixed\n" + "\n".join(
                f"i{i},I,1,1,1,1,1,true,fixed" for i in range(101)
            ))
        self.assertTrue(any(error["field"] == "rows" for error in caught.exception.errors))

    def test_csv_invalid_unicode_has_structured_error(self):
        with self.assertRaises(CsvValidationError) as caught:
            parse_csv("\ud800")
        self.assertEqual(caught.exception.errors[0]["field"], "csv")


if __name__ == "__main__":
    unittest.main()
