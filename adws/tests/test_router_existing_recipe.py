"""Tunza-shaped asks are an existing factory recipe, not needs_human.

Bare publish stays forbidden. A new ADW with a checkable gate still builds.
No keys, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "adws"))

from builder_modules.router import route  # noqa: E402

B73E_PROMPT = (
    "Build a tunza workflow, for making thigns related to tunza or wokr related to it"
)


class RouterExistingRecipeTest(unittest.TestCase):
    def test_tunza_prompt_is_existing_recipe_not_needs_human(self):
        decision = route(B73E_PROMPT)
        self.assertNotEqual(decision["route"], "needs_human", decision)
        self.assertEqual(decision["route"], "existing_recipe", decision)
        self.assertIn("just tunza", decision["reason"])
        self.assertEqual(decision["questions"], [])

    def test_bare_git_push_is_still_forbidden_target(self):
        decision = route("please git push and deploy to production")
        self.assertEqual(decision["route"], "forbidden_target", decision)

    def test_research_learn_with_gate_is_still_build(self):
        decision = route(
            "Build a new factory ADW: research.learn. It must gate citations verified."
        )
        self.assertEqual(decision["route"], "build", decision)
        self.assertNotEqual(decision["route"], "forbidden_target", decision)

    def test_higgsfield_without_gate_is_not_an_existing_recipe(self):
        decision = route("Build a higgsfield model workflow")
        self.assertNotEqual(decision["route"], "existing_recipe", decision)
        self.assertEqual(decision["route"], "needs_human", decision)


if __name__ == "__main__":
    unittest.main()
