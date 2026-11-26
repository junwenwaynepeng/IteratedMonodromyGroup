import unittest
from unittest.mock import patch

from program_a import subgroup_pool as pools
from program_a.kh import cover, index
from program_a.shared.exact import Action
from test_methods import ACTION, POOL


class PoolTests(unittest.TestCase):
    def test_complete_image_is_usable_by_both_backends(self):
        packet = ACTION.packet
        pool = pools.prepare(packet, POOL)
        self.assertEqual(pool["subgroup_label"], "H")
        rows = pools.pool_rows(packet, pool)
        self.assertEqual(rows, [{"parent_word": [1, 1], "sections": [[], []]}])
        self.assertIn("FROZEN_TUPLES_VALIDATION_ENTER", index.render(packet, rows))
        self.assertEqual(cover.solve(packet, pool)["all_level_I_upper_bound"], 4)

    def test_limit_keeps_original_pool(self):
        with self.assertRaises(pools.ConstructionLimit):
            pools.schreier_rows(Action(ACTION.packet), max_quotient=1)
        with patch.object(
            pools, "schreier_rows", side_effect=pools.ConstructionLimit("root quotient")
        ):
            prepared = pools.prepare(ACTION.packet, POOL)
        self.assertEqual(prepared["subgroup_label"], "K")
        self.assertEqual(prepared["tuple_generators"], POOL["tuple_generators"])
        self.assertEqual(
            prepared["verified_relators_basis"], POOL["verified_relators_basis"]
        )

    def test_wrong_action_rejected_before_solving(self):
        prepared = pools.prepare(ACTION.packet, POOL)
        with self.assertRaisesRegex(ValueError, "action mismatch"):
            pools.pool_rows(dict(ACTION.packet, map_id="different"), prepared)
