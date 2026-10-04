"""Independent geometry and input checks for the packing MVP."""

import json
import unittest
from unittest.mock import patch

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
        self.assertLessEqual(result["placed"][0]["dy"], 2350)

    def test_payload_limit_leaves_item_unplaced(self):
        result = pack_items([item("heavy-a", weight=16000), item("heavy-b", weight=16000)])
        self.assertEqual(result["unplaced"][0]["reason"], "payload_limit")
        self.assertEqual(result["totals"]["placed_weight_kg"], 16000)

    def test_payload_boundary_uses_exact_gram_units(self):
        at_limit = pack_items([item("a", weight=14100.125), item("b", weight=14099.875)])
        self.assertEqual(at_limit["totals"]["placed_weight_kg"], 28200)
        self.assertEqual(at_limit["totals"]["unplaced_count"], 0)
        over_limit = pack_items([item("a", weight=14100.125), item("b", weight=14099.876)])
        self.assertEqual(over_limit["totals"]["placed_weight_kg"], 14100.125)
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
        self.assertLessEqual(result["totals"]["placed_weight_kg"], 28200)
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

    def test_csv_bounds_user_controlled_labels(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation"
        for field, value in (("item_id", "X" * 65), ("name", "N" * 121)):
            row = {"item_id": "a", "name": "A", "length_mm": "10", "width_mm": "10", "height_mm": "10", "weight_kg": "1", "quantity": "1", "stackable": "true", "orientation": "fixed"}
            row[field] = value
            with self.subTest(field=field), self.assertRaises(CsvValidationError) as caught:
                parse_csv(header + "\n" + ",".join(row[key] for key in header.split(",")) + "\n")
            self.assertTrue(any(error["field"] == field for error in caught.exception.errors))

    def test_candidate_budget_is_global_and_reports_remaining_units(self):
        rows = parse_csv(DEMO_CSV)
        with patch("optimization.packing.MAX_CANDIDATE_CHECKS_PER_PACK", 1):
            result = pack_items(rows)
        self.assertEqual(result["totals"]["input_count"], 5)
        self.assertEqual(result["totals"]["placed_count"] + result["totals"]["unplaced_count"], 5)
        self.assertEqual(result["placed"][0]["item_id"], "CRATE-001")
        self.assertTrue(all(item["reason"] == "search_budget_exhausted" for item in result["unplaced"]))

    def test_dimension_reason_survives_budget_exhaustion(self):
        with patch("optimization.packing.MAX_CANDIDATE_CHECKS_PER_PACK", 0):
            result = pack_items([item("too-long", length=6000), item("fits")])
        reasons = {entry["item_id"]: entry["reason"] for entry in result["unplaced"]}
        self.assertEqual(reasons["too-long"], "door_or_container_dimensions")
        self.assertEqual(reasons["fits"], "search_budget_exhausted")

    def test_previous_per_orientation_candidate_bound_is_preserved(self):
        with patch("optimization.packing.MAX_CANDIDATE_CHECKS_PER_ORIENTATION", 1):
            result = pack_items([item("a"), item("b")])
        self.assertEqual(result["totals"]["placed_count"], 1)
        self.assertEqual(result["unplaced"][0]["reason"], "no_feasible_space_found_by_heuristic")

    def test_named_container_profiles_flow_through_geometry_and_payload(self):
        long_item = item("long", length=6000, width=500, height=500)
        small = pack_items([long_item], "20std")
        standard40 = pack_items([long_item], "40std")
        self.assertEqual(small["container"]["id"], "20std")
        self.assertEqual(small["unplaced"][0]["reason"], "door_or_container_dimensions")
        self.assertEqual(standard40["placed"][0]["item_id"], "long")
        self.assertEqual(standard40["container"]["inside_mm"]["length"], 12032)
        self.assertEqual(standard40["container"]["status"], "supported_packing")

        high = pack_items([item("tall", length=1000, width=500, height=2500)], "40hc")
        dry40 = pack_items([item("tall", length=1000, width=500, height=2500)], "40std")
        self.assertEqual(high["totals"]["placed_count"], 1)
        self.assertEqual(dry40["unplaced"][0]["reason"], "door_or_container_dimensions")
        self.assertEqual(pack_items([item("payload", weight=28500)], "20std")["unplaced"][0]["reason"], "payload_limit")
        self.assertEqual(pack_items([item("payload", weight=28500)], "40std")["totals"]["placed_count"], 1)

    def test_exact_door_width_fits_but_one_mm_over_does_not(self):
        exact = pack_items([item("exact", length=1000, width=2350, height=100)])
        over = pack_items([item("over", length=1000, width=2351, height=100)])
        self.assertEqual(exact["totals"]["placed_count"], 1)
        self.assertEqual(over["unplaced"][0]["reason"], "door_or_container_dimensions")

    def test_floor_only_placement_stays_on_floor_and_can_independently_support(self):
        result = pack_items([
            item("a-floor", length=1000, width=1000, height=300, stackable=True),
            {**item("b-floor-only", length=500, width=500, height=200), "floor_only": True},
            {**item("c-top", length=500, width=500, height=100), "floor_only": False},
        ])
        by_id = {cargo["item_id"]: cargo for cargo in result["placed"]}
        self.assertEqual(by_id["b-floor-only"]["z"], 0)

        floor_support = pack_items([
            {**item("a-floor-base", length=5896, width=2350, height=300, stackable=True), "floor_only": True},
            item("b-top", length=500, width=500, height=100),
        ])
        by_id = {cargo["item_id"]: cargo for cargo in floor_support["placed"]}
        self.assertEqual(by_id["a-floor-base"]["z"], 0)
        self.assertEqual(by_id["b-top"]["z"], by_id["a-floor-base"]["dz"])

    def test_floor_only_no_floor_space_has_explicit_heuristic_reason(self):
        result = pack_items([
            item("base", length=5896, width=2350, height=1000),
            {**item("floor-only", length=1000, width=1000, height=100), "floor_only": True},
        ])
        self.assertEqual(result["unplaced"][0]["item_id"], "floor-only")
        self.assertEqual(result["unplaced"][0]["reason"], "floor_only_no_floor_space")

    def test_legacy_csv_defaults_optional_cargo_metadata(self):
        legacy = parse_csv(DEMO_CSV)
        self.assertEqual(legacy[0]["load_unit_type"], "carton_crate")
        self.assertFalse(legacy[0]["floor_only"])
        self.assertFalse(legacy[0]["is_dg"])
        self.assertEqual(legacy[0]["un_number"], "")

    def test_load_unit_types_optional_flags_and_manual_dg_hold_expand(self):
        header = ("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,"
                  "load_unit_type,floor_only,is_dg,un_number,imdg_class,packing_group")
        source = (header + "\nDANGER,Drums,100,100,100,2.5,2,true,yaw,drum_roll,false,true,UN1993,3,II\n"
                  "PAL,Pallet,1000,800,1200,50,1,false,fixed,palletized,true,false,,,\n")
        items = parse_csv(source)
        self.assertEqual([row["load_unit_type"] for row in items], ["drum_roll", "drum_roll", "palletized"])
        self.assertEqual([row["un_number"] for row in items[:2]], ["UN1993", "UN1993"])
        result = pack_items(items, "40std")
        held = [row for row in result["unplaced"] if row["reason"] == "manual_compliance_hold"]
        self.assertEqual(len(held), 2)
        self.assertTrue(all(row["is_dg"] and row["imdg_class"] == "3" and row["packing_group"] == "II" for row in held))
        self.assertTrue(all(row["load_unit_type"] == "palletized" for row in result["placed"]))
        self.assertEqual(result["readiness"], "manual_compliance_hold")
        self.assertEqual(result["totals"]["manual_compliance_hold_count"], 2)
        self.assertEqual(result["totals"]["input_count"], 3)

    def test_dg_hold_precedes_payload_and_dimension_reasons(self):
        dg = {**item("dg", length=100000, width=50000, height=10000, weight=1e308), "is_dg": True, "un_number": "UN0001"}
        result = pack_items([dg])
        self.assertEqual(result["placed"], [])
        self.assertEqual(result["unplaced"][0]["reason"], "manual_compliance_hold")
        self.assertEqual(result["readiness"], "manual_compliance_hold")

    def test_dg_metadata_without_flag_is_rejected_in_csv_and_direct_items(self):
        header = ("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,"
                  "is_dg,un_number")
        with self.assertRaisesRegex(ValueError, "requires is_dg=true"):
            parse_csv(header + "\na,A,10,10,10,1,1,true,fixed,false,UN0001\n")
        with self.assertRaisesRegex(ValueError, "requires is_dg=true"):
            pack_items([{**item("a"), "un_number": "UN0001"}])

    def test_optional_columns_validate_explicit_boolean_and_load_unit_type(self):
        header = ("item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,"
                  "floor_only,is_dg,load_unit_type")
        with self.assertRaisesRegex(ValueError, "floor_only"):
            parse_csv(header + "\na,A,10,10,10,1,1,true,fixed,,false,carton_crate\n")
        with self.assertRaisesRegex(ValueError, "load_unit_type"):
            parse_csv(header + "\na,A,10,10,10,1,1,true,fixed,false,false,reefer\n")

    def test_custom_measured_dry_container_is_bounded_and_unverified(self):
        profile = {
            "name": "My measured box", "inside_mm": {"length": 6000, "width": 2400, "height": 2500},
            "door_mm": {"width": 2300, "height": 2200}, "max_payload_kg": 20000,
            "dimensions_source": {"kind": "equipment_plate", "reference": "Unit plate noted 2026-10-04"},
        }
        result = pack_items([item("a", length=1000, width=500, height=100)], "custom_dry", custom_profile=profile)
        self.assertEqual(result["container"]["id"], "custom_dry")
        self.assertEqual(result["container"]["status"], "unverified_measured")
        self.assertEqual(result["container"]["dimensions_source"], profile["dimensions_source"])
        self.assertEqual(result["placed"][0]["item_id"], "a")
        self.assertEqual(pack_items([item("heavy", weight=20000.001)], "custom_dry", custom_profile=profile)["unplaced"][0]["reason"], "payload_limit")
        for invalid in (
            {**profile, "door_mm": {"width": 2401, "height": 2200}},
            {**profile, "inside_mm": {"length": -1, "width": 2400, "height": 2500}},
            {**profile, "dimensions_source": {"kind": "made_up", "reference": "x"}},
            {**profile, "dimensions_source": {"kind": "user_measurement", "reference": ""}},
            {**profile, "family": "trailer"},
            {**profile, "max_payload_kg": 1_000_001},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pack_items([item("a")], "custom_dry", custom_profile=invalid)
        with self.assertRaisesRegex(ValueError, "required"):
            pack_items([item("a")], "custom_dry")
        with self.assertRaisesRegex(ValueError, "only be supplied"):
            pack_items([item("a")], "20std", custom_profile=profile)

    def test_unknown_container_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported container_id"):
            pack_items([item("a")], "reefer")


if __name__ == "__main__":
    unittest.main()
