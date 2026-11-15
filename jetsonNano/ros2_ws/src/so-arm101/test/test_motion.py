import unittest

from so_arm101.motion import targets_at, within_limits


class MotionTest(unittest.TestCase):
    def test_all_targets_stay_within_configured_displacement(self):
        starts = [2048, 2200]
        amplitudes = [200, 240]
        for sample in range(1001):
            targets = targets_at(starts, amplitudes, 0.08, sample / 100)
            for start, amplitude, target in zip(starts, amplitudes, targets):
                self.assertLessEqual(abs(target - start), amplitude)

    def test_refuses_start_near_raw_tick_limit(self):
        self.assertFalse(within_limits([300, 2048], [200, 240], 128, 3967))
        self.assertTrue(within_limits([2048, 2048], [200, 240], 128, 3967))


if __name__ == "__main__":
    unittest.main()
