"""
ÆONIX PRISM // Phase 4 Test & Verification Suite
Verifies SPECTRA Media Intelligence, Live IPTV Streams, and Autonomous Sanctuary Mode.
"""

import sys
import unittest

sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database
from aeonix.core.spectra import get_channel_catalog, find_channel_by_query, set_playback_state, get_current_playback
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary, get_sanctuary_status, is_sanctuary_active
from aeonix.core.fast_path import match_fast_path, execute_fast_path

class TestPhase4CinemaAndSanctuary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_spectra_channel_catalog_and_search(self):
        """Test channel lineup and query matching."""
        catalog = get_channel_catalog()
        self.assertGreaterEqual(len(catalog), 3)

        # NASA / Space search
        ch_nasa = find_channel_by_query("nasa")
        self.assertIsNotNone(ch_nasa)
        self.assertEqual(ch_nasa["id"], "nasa_tv")

        # News search
        ch_news = find_channel_by_query("world news")
        self.assertIsNotNone(ch_news)
        self.assertIn(".m3u8", ch_news["stream_url"])

        # Playback tracking
        set_playback_state(True, ch_nasa)
        curr = get_current_playback()
        self.assertTrue(curr["is_playing"])
        self.assertEqual(curr["channel_id"], "nasa_tv")

        set_playback_state(False)
        curr2 = get_current_playback()
        self.assertFalse(curr2["is_playing"])

    def test_sanctuary_lockdown_cycle(self):
        """Test engagement, vault protection, and release."""
        res_eng = engage_sanctuary(actor="Aadi", reason="Unit Verification")
        self.assertEqual(res_eng["status"], "engaged")
        self.assertTrue(is_sanctuary_active())

        stat = get_sanctuary_status()
        self.assertTrue(stat["is_active"])
        self.assertEqual(stat["engaged_by"], "Aadi")

        res_rel = release_sanctuary(actor="Aadi")
        self.assertEqual(res_rel["status"], "released")
        self.assertFalse(is_sanctuary_active())

    def test_fast_path_cinema_and_sanctuary_triggers(self):
        """Test sub-50ms intent matching and payload formatting."""
        # 1. Watch NASA trigger
        match1 = match_fast_path("watch nasa")
        self.assertIsNotNone(match1)
        action1, conf1 = match1
        self.assertEqual(action1, "play_nasa")
        res1 = execute_fast_path(action1)
        self.assertIn("media_play", res1)
        self.assertEqual(res1["layout_intent"]["screen"], "cinema")
        self.assertLess(res1["latency_ms"], 50)

        # 2. Sanctuary mode trigger
        match2 = match_fast_path("sanctuary mode")
        self.assertIsNotNone(match2)
        action2, conf2 = match2
        self.assertEqual(action2, "mode_sanctuary")
        res2 = execute_fast_path(action2)
        self.assertEqual(res2["layout_intent"]["screen"], "sanctuary")
        self.assertEqual(res2["layout_intent"]["theme"], "obsidian_crimson")

        # 3. Exit sanctuary trigger
        match3 = match_fast_path("exit sanctuary")
        self.assertIsNotNone(match3)
        action3, conf3 = match3
        self.assertEqual(action3, "mode_sanctuary_release")
        res3 = execute_fast_path(action3)
        self.assertEqual(res3["layout_intent"]["screen"], "living_surface")

if __name__ == "__main__":
    unittest.main()
