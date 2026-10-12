"""Run the existing assertion-based tests with the stdlib unittest runner."""
import runpy
from pathlib import Path
import unittest


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name in ('test_abab_skill.py', 'test_abab_state.py', 'test_hyprland_ui_testing_skill.py'):
        namespace = runpy.run_path(str(Path(__file__).with_name(name)))
        for key, value in namespace.items():
            if key.startswith('test_') and callable(value):
                suite.addTest(unittest.FunctionTestCase(value, description=f'{name}:{key}'))
    return suite
