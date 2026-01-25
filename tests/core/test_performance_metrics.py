import unittest


class TestPerformanceMetrics(unittest.TestCase):
    def test_max_underwater_days(self) -> None:
        from core.performance_metrics import max_underwater_days

        self.assertEqual(max_underwater_days([]), 0)
        self.assertEqual(max_underwater_days([100.0]), 0)

        # Peak at 110, then underwater for 2 days (105, 106), recovery at 111 resets.
        self.assertEqual(max_underwater_days([100, 110, 105, 106, 111]), 2)

        # Underwater streak grows to 3 before recovery.
        self.assertEqual(max_underwater_days([100, 120, 119, 118, 117, 121]), 3)

        # New highs reset.
        self.assertEqual(max_underwater_days([100, 101, 102, 101, 103, 102, 104]), 1)


if __name__ == "__main__":
    unittest.main()

