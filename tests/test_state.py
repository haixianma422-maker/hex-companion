import importlib
import unittest


class StateTests(unittest.TestCase):
    def context(self):
        try:
            return importlib.import_module('aram_demo.state').RequestContext
        except ImportError:
            self.fail('Missing implementation: request context')

    def test_old_hero_mode_or_generation_cannot_replace_current_data(self):
        cls = self.context()
        current = cls('demo', 222, 3)
        self.assertTrue(current.accepts(cls('demo', 222, 3)))
        self.assertFalse(current.accepts(cls('demo', 99, 3)))
        self.assertFalse(current.accepts(cls('client', 222, 3)))
        self.assertFalse(current.accepts(cls('demo', 222, 2)))

    def test_demo_candidates_do_not_depend_on_client_connection(self):
        try:
            state = importlib.import_module('aram_demo.state')
        except ImportError:
            self.fail('Missing implementation: demo state')
        from aram_demo.lcu import ClientState
        self.assertEqual(state.demo_candidates(ClientState()), [222, 99, 86])


if __name__ == '__main__':
    unittest.main()
