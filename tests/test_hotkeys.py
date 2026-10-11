import unittest
from unittest.mock import Mock, patch

from aram_demo.hotkeys import Hotkeys


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(Hotkeys, 'configure'), 'Configurable hotkeys are not implemented')

    def test_default_toggle_and_custom_bindings_are_normalized(self):
        manager = Hotkeys(lambda: None, lambda: None, lambda: None, on_toggle=lambda: None)
        self.assertEqual(manager.bindings['toggle'], 'F8')
        manager.configure({'scan': 'shift+f6', 'refresh': 'F7', 'toggle': 'ctrl+alt+h'})
        self.assertEqual(manager.bindings, {'scan': 'Shift+F6', 'refresh': 'F7', 'toggle': 'Ctrl+Alt+H'})

    def test_invalid_or_duplicate_bindings_leave_previous_settings_intact(self):
        manager = Hotkeys(lambda: None, lambda: None, lambda: None)
        original = dict(manager.bindings)
        for changed in ({'toggle': 'F6'}, {'toggle': 'H'}, {'toggle': 'Alt+F4'}, {'toggle': ''}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                manager.configure(changed)
            self.assertEqual(manager.bindings, original)

    def test_register_conflict_restores_previous_bindings_on_same_thread(self):
        manager = Hotkeys(lambda: None, lambda: None, lambda: None)
        native = Mock()
        native.RegisterHotKey.return_value = 1
        manager._register(native, manager.bindings)
        original = dict(manager.bindings)
        native.RegisterHotKey.side_effect = [1, 1, 0, 1, 1, 1]
        with self.assertRaisesRegex(ValueError, 'F9'):
            manager._register(native, {**original, 'toggle': 'F9'})
        self.assertEqual(manager.bindings, original)
        self.assertEqual(manager.registered, {1, 2, 3})

    def test_timed_out_request_cannot_apply_later(self):
        manager = Hotkeys(lambda: None, lambda: None, lambda: None)
        manager.thread = Mock()
        manager.thread.is_alive.return_value = True
        original = dict(manager.bindings)
        with patch('threading.Event.wait', return_value=False):
            with self.assertRaisesRegex(ValueError, '暂未响应'):
                manager.configure({'toggle': 'F9'})
        native = Mock()
        manager._apply_command(native, *manager.commands.get_nowait())
        native.RegisterHotKey.assert_not_called()
        self.assertEqual(manager.bindings, original)

