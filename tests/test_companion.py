import importlib
import unittest
from unittest.mock import patch

from aram_demo.lcu import ClientState, Credentials, LCUClient


class CompanionTests(unittest.TestCase):
    def tracker(self):
        return importlib.import_module('aram_demo.companion_state').SessionTracker()

    def test_startup_normal_aram_ranked_and_unknown_mode_stay_hidden(self):
        tracker = self.tracker()
        for state in [ClientState(), ClientState('Lobby'),
                      ClientState('ChampSelect', 222, [99], queue_id=450),
                      ClientState('InProgress', 99, queue_id=420)]:
            self.assertEqual(tracker.update(state).stage, 'hidden')

    def test_mayhem_lobby_select_game_and_exit_switch_automatically(self):
        tracker = self.tracker()
        self.assertEqual(tracker.update(ClientState('Lobby', queue_id=2400)).stage, 'lobby')
        selected = tracker.update(ClientState('ChampSelect', 222, [99, 86], queue_id=2400))
        self.assertEqual((selected.stage, selected.champion_id, selected.candidate_ids), ('select', 222, [99, 86]))
        game = tracker.update(ClientState('InProgress', queue_id=2400, match_id=1))
        self.assertEqual((game.stage, game.champion_id), ('game', 222))
        self.assertGreater(game.revision, selected.revision)
        self.assertEqual(tracker.update(ClientState('EndOfGame')).stage, 'hidden')
        self.assertEqual(tracker.update(ClientState('InProgress', queue_id=2400, match_id=2)).champion_id, None)

    def test_verified_tencent_custom_mayhem_queue_shows_select_and_retains_hero_in_game(self):
        tracker = self.tracker()
        self.assertEqual(tracker.update(ClientState('Lobby', queue_id=3270)).stage, 'lobby')
        selected = tracker.update(ClientState('ChampSelect', 222, queue_id=3270))
        self.assertEqual((selected.stage, selected.champion_id), ('select', 222))
        game = tracker.update(ClientState('InProgress', queue_id=3270))
        self.assertEqual((game.stage, game.champion_id), ('game', 222))
        self.assertEqual(tracker.update(ClientState('Lobby', queue_id=450)).stage, 'hidden')

    def test_transient_secondary_failure_retains_known_mode_but_wrong_queue_does_not(self):
        tracker = self.tracker()
        tracker.update(ClientState('ChampSelect', 222, queue_id=2400))
        self.assertEqual(tracker.update(ClientState('InProgress')).champion_id, 222)
        other = tracker.update(ClientState('InProgress', 99, queue_id=450))
        self.assertEqual(other.stage, 'hidden')
        self.assertIsNone(other.champion_id)

    def test_new_match_invalidates_champion_and_recognition_even_if_queue_unchanged(self):
        tracker = self.tracker()
        before = tracker.update(ClientState('InProgress', 222, match_id=1, queue_id=2400))
        after = tracker.update(ClientState('InProgress', match_id=2))
        self.assertEqual(after.stage, 'hidden')
        self.assertIsNone(after.champion_id)
        self.assertGreater(after.revision, before.revision)

    def test_lcu_reads_queue_before_champ_select(self):
        from aram_demo import lcu
        responses = ['ChampSelect', {'gameData': {'queue': {'id': 2400}, 'gameId': 1}},
                     {'localPlayerCellId': 2, 'myTeam': [{'cellId': 2, 'championId': 222}]}]
        with patch.object(lcu, 'discover', return_value=Credentials(4567, 'test')), \
             patch.object(lcu, 'local_json', side_effect=responses):
            state = LCUClient().read_state()
        self.assertEqual((state.queue_id, state.champion_id), (2400, 222))

    def test_lcu_lobby_fallback_reads_game_config(self):
        from aram_demo import lcu
        responses = ['Lobby', {}, {'gameConfig': {'queueId': 2400}}]
        with patch.object(lcu, 'discover', return_value=Credentials(4567, 'test')), \
             patch.object(lcu, 'local_json', side_effect=responses):
            self.assertEqual(LCUClient().read_state().queue_id, 2400)

    def test_popup_prefers_client_right_and_clamps_inside_monitor(self):
        place = importlib.import_module('aram_demo.windows').panel_position
        self.assertEqual(place((100, 100, 1300, 800), (0, 0, 1920, 1040), 300, 560), (1312, 100))
        x, y = place((0, 0, 1920, 1080), (0, 0, 1920, 1040), 300, 560)
        self.assertGreaterEqual(x, 0)
        self.assertLessEqual(x + 300, 1920)
        self.assertLessEqual(y + 560, 1040)

    def test_letters_match_verified_opgg_badges(self):
        from aram_demo.models import augment_label
        self.assertEqual([augment_label(i) for i in range(6)], list('SABCDE'))
        self.assertEqual(augment_label(6), '第7档')
