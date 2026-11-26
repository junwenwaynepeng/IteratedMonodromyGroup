import copy
import json
import shutil
import unittest
from pathlib import Path

from program_a import fr
from program_a.action_sources import load
from program_a.contracts import pin
from program_a.kh import cover, index
from program_a.n.engine import run

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
ACTION = load(pin(EXAMPLES / "root-swap.json"))
POOL = json.loads((EXAMPLES / "root-swap-pool.json").read_text())


class MethodTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gap"), "GAP needed for NEWTC")
    def test_newtc_and_replay(self):
        result = cover.solve(ACTION.packet, POOL)
        self.assertEqual(result["all_level_I_upper_bound"], 4)
        self.assertEqual(result["status"], "CERTIFIED_DIRECT_IMAGE_BOUND")
        broken = copy.deepcopy(result["certificate"])
        broken["transitions"].pop()
        self.assertEqual(cover.replay(ACTION.packet, broken)["status"], "FAIL")

    def test_invalid_relator(self):
        with self.assertRaisesRegex(ValueError, "invalid input relator"):
            cover.solve(ACTION.packet, dict(POOL, verified_relators_basis=[[1]]))

    def test_normal_cover(self):
        self.assertEqual(run(ACTION, {})["status"], "CERTIFIED_N_BOUND")

    def test_index_subgroup_choice(self):
        self.assertIn("FROZEN_TUPLES_VALIDATION_ENTER", index.render(ACTION.packet, []))
        self.assertIn("FRESH_EXACT_ROOT_STABILIZER_ENTER", index.render(ACTION.packet))

    def test_fr_order(self):
        script = fr.render(ACTION.packet)
        self.assertLess(
            script.index("K_FR:=BranchingSubgroup(G)"),
            script.index("ANSWER:=IsBranched(G)"),
        )
