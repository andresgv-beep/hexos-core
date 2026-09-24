import unittest
from hexos.agent.chat_backend.live import LiveGeneration


class MetricsTest(unittest.TestCase):
    def test_weighted_decode_only(self):
        live = LiveGeneration('test', True)
        live.update(dict(decode_sample=dict(tokens=100, milliseconds=2000)))
        live.update(dict(phase='tool'))
        live.update(dict(decode_sample=dict(tokens=50, milliseconds=3000)))
        self.assertEqual(live.snapshot()['tokens_per_second'], 30)
        self.assertNotIn('decode_sample', live.snapshot())

    def test_invalid_and_new_turn(self):
        live = LiveGeneration('test', True)
        for ms in (None, 0, -1, float('nan'), float('inf')):
            live.update(dict(decode_sample=dict(tokens=20, milliseconds=ms)))
        self.assertNotIn('tokens_per_second', live.snapshot())
        live.update(dict(decode_sample=dict(tokens=20, milliseconds=1000)))
        self.assertNotIn('tokens_per_second', LiveGeneration('next', True).snapshot())


if __name__ == '__main__':
    unittest.main()
