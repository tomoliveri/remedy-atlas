import json
import unittest

import harness  # noqa: F401  (sets WS_HOME, sys.path)
from workstead.cli import wait_for_work


class WaitForWork(unittest.TestCase):
    def run_wait(self, answers, minutes):
        t = [0.0]
        slept = []
        seq = iter(answers)

        def once():
            code, payload = next(seq)
            print(json.dumps(payload))
            return code

        def sleep(s):
            slept.append(s)
            t[0] += s

        code = wait_for_work(once, minutes, sleep=sleep, clock=lambda: t[0])
        return code, slept

    def test_waits_through_idle_until_work(self):
        code, slept = self.run_wait([(10, {"status": "idle", "retry_after": 60}),
                                     (20, {"status": "finished", "retry_after": 90}),
                                     (0, {"status": "work"})], minutes=8)
        self.assertEqual(code, 0)
        self.assertEqual(slept, [60, 90])

    def test_gives_up_at_the_deadline(self):
        code, slept = self.run_wait([(10, {"status": "idle", "retry_after": 300})] * 3, minutes=8)
        self.assertEqual(code, 10)
        self.assertEqual(slept, [300, 180])

    def test_no_wait_and_stop_return_at_once(self):
        self.assertEqual(self.run_wait([(10, {"status": "idle", "retry_after": 60})], minutes=0), (10, []))
        self.assertEqual(self.run_wait([(50, {"status": "stopped"})], minutes=8), (50, []))


if __name__ == "__main__":
    unittest.main()
