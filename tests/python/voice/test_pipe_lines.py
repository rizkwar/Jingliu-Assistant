import io
import sys
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QProcess

from companion.voice.pipes import lines
from tests.qt_test_support import application

ROOT = Path(__file__).resolve().parents[3]
# An engine-like child: commands are read on a thread while the main thread loads a native library.
CHILD = r'''
import sys, threading, time
sys.path.insert(0, %r)
from companion.voice.pipes import lines
received = []
def read():
    for line in lines(sys.stdin):
        received.append(line)
threading.Thread(target=read, daemon=True).start()
time.sleep(0.3)  # The reader is waiting on the pipe now.
import numpy  # Loading native code froze here with a blocking read pending.
while len(received) < 2:
    time.sleep(0.02)
print("ok", repr(received), flush=True)
''' % str(ROOT)


class PipeLinesTests(unittest.TestCase):
    def test_in_memory_streams_pass_through(self):
        self.assertEqual(list(lines(io.StringIO("a\nb\n"))), ["a\n", "b\n"])

    @unittest.skipUnless(sys.platform == "win32", "Windows pipes")
    def test_an_engine_keeps_loading_libraries_while_waiting_for_commands(self):
        application()
        process = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(["-u", "-c", CHILD])
        process.start()
        self.assertTrue(process.waitForStarted(10000))
        process.write(b'{"action": "first"}\n{"act')  # A command split across writes.
        process.waitForBytesWritten(2000)
        time.sleep(0.2)
        process.write(b'ion": "second"}\n')
        process.waitForBytesWritten(2000)
        finished = process.waitForFinished(30000)
        output = bytes(process.readAllStandardOutput()).decode()
        if not finished:
            process.kill()
            process.waitForFinished(2000)
        self.assertTrue(finished, "the child froze while loading a library")
        self.assertTrue(output.startswith("ok"), output)
        self.assertIn('"action": "first"', output)
        self.assertIn('"action": "second"', output)  # Joined from two writes into one line.


if __name__ == "__main__":
    unittest.main()
