import json
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent
from companion.voice.speech import SpeechController
from tests.qt_test_support import application


class PlaybackTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.speech = SpeechController()
        self.speech._active_id = 'current'
        self.levels, self.resets = [], []
        self.speech.playback_level.connect(lambda level: self.levels.append((level, time.monotonic())))
        self.speech.playback_reset.connect(lambda: self.resets.append(time.monotonic()))

    def tearDown(self):
        self.speech.shutdown()
        self.speech.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def receive(self, **event):
        payload = json.dumps({'id': 'current', 'type': 'playback', **event}).encode() + b'\n'
        with patch.object(self.speech.process, 'readAllStandardOutput', return_value=payload):
            self.speech._read()

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.002)
        self.app.processEvents()

    def test_level_is_delivered_at_dac_time_instead_of_receipt(self):
        at = time.monotonic() + .06
        self.receive(level=.7, at=at)
        self.assertEqual(self.levels, [])
        self.wait(.12)
        self.assertEqual(len(self.levels), 1)
        self.assertEqual(self.levels[0][0], .7)
        self.assertGreaterEqual(self.levels[0][1], at - .001)

    def test_stop_invalidates_scheduled_and_late_old_job_updates(self):
        self.receive(level=.8, at=time.monotonic() + .06)
        self.speech.stop()
        self.speech._active_id = 'replacement'
        self.receive(level=.9, at=time.monotonic())  # Still tagged with old ID.
        self.wait(.12)
        self.assertEqual(self.levels, [])
        self.assertTrue(self.resets)

    def test_done_clears_pending_levels_before_next_phrase(self):
        self.receive(level=.8, at=time.monotonic() + .06)
        self.receive(type='done')
        self.wait(.12)
        self.assertEqual(self.levels, [])
        self.assertTrue(self.resets)

    def test_malformed_obsolete_and_far_future_telemetry_is_ignored(self):
        now = time.monotonic()
        for level, at in [(float('nan'), now), (.5, float('inf')), (True, now),
                          (-1, now), (2, now), (.5, now-5), (.5, now+5)]:
            self.receive(level=level, at=at)
        self.assertEqual(self.levels, [])
        self.assertFalse(self.speech._levels)

    def test_lost_telemetry_returns_to_rest(self):
        self.receive(level=.6, at=time.monotonic())
        self.wait(.3)
        self.assertEqual(self.levels[0][0], .6)
        self.assertTrue(self.resets)

    def test_blocked_ui_drops_obsolete_frames(self):
        self.receive(level=.8, at=time.monotonic() - .4)
        self.assertEqual(self.levels, [])
        self.assertTrue(self.resets)
