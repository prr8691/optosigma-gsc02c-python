import unittest

from optosigma_gsc02c import SimulatedGSC02C


class SimulatedStageTests(unittest.TestCase):
    def setUp(self):
        self.stage = SimulatedGSC02C(initial_position_mm=40.0)
        self.stage.connect()

    def tearDown(self):
        self.stage.close()

    def test_relative_move(self):
        self.stage.move_relative_mm(1.5)
        self.assertAlmostEqual(self.stage.get_position_mm(), 41.5)

    def test_absolute_move(self):
        self.stage.move_absolute_mm(12.0)
        self.assertAlmostEqual(self.stage.get_position_mm(), 12.0)

    def test_85_mm_limit(self):
        with self.assertRaises(ValueError):
            self.stage.move_absolute_mm(85.001)

    def test_home_negative(self):
        self.stage.home("-")
        self.assertAlmostEqual(self.stage.get_position_mm(), 0.0)


if __name__ == "__main__":
    unittest.main()
