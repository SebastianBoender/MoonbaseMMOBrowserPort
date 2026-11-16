"""Prevent false parity claims from truncated traces or rotation encoding."""
import copy
import json
from pathlib import Path
import unittest

from compare_driving import compare, distance

FIXTURES = Path(__file__).parent / 'fixtures/native-driving'


class DrivingComparisonTest(unittest.TestCase):
    def test_recorded_free_suspension_matches_native(self):
        reference = json.loads((FIXTURES / 'idle-com-3.json').read_text())
        browser = json.loads((FIXTURES / 'browser-experiment4-idle-3.json').read_text())
        self.assertTrue(compare(reference, browser)['pass'])

    def test_recorded_ground_impact_still_fails(self):
        reference = json.loads((FIXTURES / 'forward-90.json').read_text())
        browser = json.loads((FIXTURES / 'browser-experiment4-forward-90.json').read_text())
        result = compare(reference, browser)
        self.assertFalse(result['pass'])
        self.assertEqual(result['first_mismatch'], 24)

    def test_incomplete_or_different_scenario_is_not_a_pass(self):
        reference = json.loads((FIXTURES / 'forward-90.json').read_text())
        for mutation in ['truncate', 'input', 'timestep', 'missing_tick']:
            candidate = copy.deepcopy(reference)
            if mutation == 'truncate':
                candidate['samples'].pop()
            elif mutation == 'input':
                candidate['input'] = 'reverse'
            elif mutation == 'timestep':
                candidate['dt'] /= 2
            else:
                candidate['samples'][5][0] = 7
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compare(reference, candidate)

    def test_equivalent_axis_angle_encodings(self):
        self.assertAlmostEqual(distance('[vector(0,1,0), 270]', '[vector(0,-1,0), 90]', True), 0)
        self.assertAlmostEqual(distance('[vector(0,1,0), 179]', '[vector(0,1,0), -179]', True), 2)
        self.assertAlmostEqual(distance('[vector(0,0,0), 0]', '[vector(1,0,0), 0]', True), 0)
