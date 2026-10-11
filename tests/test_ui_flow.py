import unittest
from unittest.mock import Mock

from aram_demo.lcu import ClientState
from aram_demo.models import Augment
from aram_demo.ui import DemoApp


class ClientFlowTests(unittest.TestCase):
    def app(self):
        app = DemoApp.__new__(DemoApp)
        app.mode, app.generation, app.selected_id = 'client', 1, 222
        app.game_id, app.last_phase, app.last_match_id = 222, 'ChampSelect', None
        app._render_candidates, app.select_hero, app.status = Mock(), Mock(), Mock()
        return app

    def test_confirmed_champion_survives_game_entry_and_transient_lookup_failure(self):
        app = self.app()
        app._apply_client_state(ClientState('GameStart'), None, False)
        self.assertEqual(app.game_id, 222)
        app._apply_client_state(ClientState('InProgress'), None, False)
        self.assertEqual(app.game_id, 222)
        self.assertEqual(app.candidate_ids, [222])

    def test_confirmation_clears_at_lobby_and_cannot_leak_to_next_game(self):
        app = self.app()
        app._apply_client_state(ClientState('Lobby'), None, False)
        self.assertIsNone(app.game_id)
        app._apply_client_state(ClientState('GameStart'), None, False)
        self.assertIsNone(app.game_id)

    def test_different_match_id_invalidates_previous_champion(self):
        app = self.app()
        app.last_phase, app.last_match_id = 'InProgress', 123
        app._apply_client_state(ClientState('InProgress', match_id=456), None, False)
        self.assertIsNone(app.game_id)

    def test_delayed_capture_keeps_context_from_f6_press(self):
        app = self.app()
        app.scanning = False
        app.augments = [Augment(1, '测试', 0, 1)]
        app.root, app.recognizer, app.hide_overlay = Mock(), Mock(), Mock()
        app._background = Mock()
        original = app.context()
        app.scan()
        scheduled = app.root.after.call_args.args[1]
        app.selected_id, app.generation = 99, 2
        scheduled()
        self.assertEqual(app._background.call_args.kwargs.get('context'), original)
        self.assertFalse(app.context().accepts(app._background.call_args.kwargs['context']))
