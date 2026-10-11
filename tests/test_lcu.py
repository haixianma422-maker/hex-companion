import importlib
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class ClientTests(unittest.TestCase):
    def test_replays_folder_is_rejected_but_install_root_and_client_folder_are_valid(self):
        module = self.module()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / 'Replays').mkdir()
            with self.assertRaises(ValueError):
                module.validate_install_path(root)
            (root / 'LeagueClient').mkdir()
            (root / 'LeagueClient' / 'LeagueClient.exe').touch()
            module.validate_install_path(root)
            module.validate_install_path(root / 'LeagueClient')
            module.validate_install_path('')

    def test_running_client_without_readable_credentials_reports_connection_problem(self):
        module = self.module()
        with patch.object(module, 'discover', return_value=None), \
             patch.object(module.subprocess, 'run', return_value=SimpleNamespace(stdout='[{"Name":"LeagueClientUx.exe","CommandLine":null}]')):
            state = module.LCUClient().read_state()
        self.assertEqual(state.phase, 'Disconnected')
        self.assertIn('管理员', state.message)
        self.assertIn('已运行', state.message)

    def test_missing_summoner_identity_never_selects_first_teammate(self):
        module = self.module()
        responses = ['InProgress', {'gameData': {'gameId': 123, 'teamOne': [
            {'championId': 99}, {'championId': 222}]}}, {}]
        with patch.object(module, 'discover', return_value=module.Credentials(4567, 'test')), \
             patch.object(module, 'local_json', side_effect=responses):
            state = module.LCUClient().read_state()
        self.assertIsNone(state.champion_id)

    def test_secondary_lcu_failure_preserves_phase_for_live_fallback(self):
        module = self.module()
        with patch.object(module, 'discover', return_value=module.Credentials(4567, 'test')), \
             patch.object(module, 'local_json', side_effect=['InProgress', OSError('unavailable')]):
            state = module.LCUClient().read_state()
        self.assertEqual(state.phase, 'InProgress')
        self.assertIsNone(state.champion_id)

    def test_missing_live_identity_never_selects_player_without_name(self):
        module = self.module()
        from aram_demo.models import Champion
        with patch.object(module, 'local_json', side_effect=[None, [{'rawChampionName': 'Lux'}]]):
            self.assertIsNone(module.live_champion_id([Champion(99, '光辉女郎', 'lux', 3, 160)]))

    def module(self):
        try:
            return importlib.import_module('aram_demo.lcu')
        except ImportError:
            self.fail('Missing implementation: lcu')

    def test_self_is_selected_by_cell_not_first_teammate(self):
        state = self.module().parse_session({'localPlayerCellId': 2, 'myTeam': [
            {'cellId': 1, 'championId': 99}, {'cellId': 2, 'championId': 222}],
            'benchChampions': [{'championId': 86}, {'championId': 86}, {'championId': 0}]})
        self.assertEqual(state.champion_id, 222)
        self.assertEqual(state.candidate_ids, [86])

    def test_missing_bench_does_not_turn_teammates_into_selectable_heroes(self):
        state = self.module().parse_session({'localPlayerCellId': 1,
            'myTeam': [{'cellId': 1, 'championId': 222}, {'cellId': 2, 'championId': 99}]})
        self.assertEqual(state.candidate_ids, [])
        self.assertEqual(state.champion_id, 222)

    def test_unknown_identity_is_not_replaced_with_jinx(self):
        state = self.module().parse_session({'localPlayerCellId': 7,
            'myTeam': [{'cellId': 7, 'championId': 99999}]})
        self.assertEqual(state.champion_id, 99999)
        self.assertIsNone(self.module().parse_session({}).champion_id)

    def test_lockfile_validates_local_port_and_protocol(self):
        module = self.module()
        info = module.parse_lockfile('LeagueClient:100:4567:private-token:https')
        self.assertEqual(info.port, 4567)
        self.assertNotIn('private-token', repr(info))
        with self.assertRaises(ValueError):
            module.parse_lockfile('LeagueClient:100:99999:secret:https')
        with self.assertRaises(ValueError):
            module.parse_lockfile('LeagueClient:100:4567:secret:file')


if __name__ == '__main__':
    unittest.main()
