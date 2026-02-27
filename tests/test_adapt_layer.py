import tempfile
import unittest
from pathlib import Path

from novaadapt_core.adapt import AdaptBondCache, AdaptPersonaEngine, AdaptToggleStore


class AdaptLayerTests(unittest.TestCase):
    def test_toggle_store_set_get_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdaptToggleStore(state_path=Path(tmp) / "toggles.json")
            default_state = store.get("adapt-a")
            self.assertEqual(default_state["mode"], "ask_only")

            updated = store.set("adapt-a", "free_speak", source="test")
            self.assertEqual(updated["mode"], "free_speak")
            self.assertEqual(store.get_mode("adapt-a"), "free_speak")

            with self.assertRaises(ValueError):
                store.set("adapt-a", "invalid-mode")

    def test_bond_cache_remember_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AdaptBondCache(state_path=Path(tmp) / "bonds.json")
            remembered = cache.remember(
                "adapt-a",
                "player-a",
                verified=True,
                profile={"element": "light"},
            )
            self.assertEqual(remembered["adapt_id"], "adapt-a")
            self.assertTrue(cache.verify_cached("adapt-a", "player-a"))
            self.assertFalse(cache.verify_cached("adapt-a", "player-b"))

    def test_bond_cache_blocks_rebinding_verified_adapt(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AdaptBondCache(state_path=Path(tmp) / "bonds.json")
            _ = cache.remember("adapt-a", "player-a", verified=True, profile={"element": "light"})
            with self.assertRaises(ValueError):
                _ = cache.remember("adapt-a", "player-b", verified=True, profile={"element": "shadow"})

    def test_persona_engine_builds_expected_context(self):
        engine = AdaptPersonaEngine()
        persona = engine.build_context(
            adapt_id="adapt-a",
            toggle_mode="in_game_only",
            bond_verified=True,
            identity_profile={"element": "fire", "subclass": "light", "form_stage": "symbiosis", "bond_strength": 82},
            cached_bond={"verified": True},
        )
        self.assertEqual(persona["adapt_id"], "adapt-a")
        self.assertEqual(persona["toggle_mode"], "in_game_only")
        self.assertEqual(persona["communication_style"], "in_world")
        self.assertEqual(persona["trust_band"], "deeply_bonded")
        self.assertTrue(persona["bond_verified"])


if __name__ == "__main__":
    unittest.main()
