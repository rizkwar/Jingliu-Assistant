"""Exercise real Windows quoting and shortcut metadata in isolated workspace folders."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(sys.platform == "win32", "Windows launchers")
class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        folder = tempfile.TemporaryDirectory(prefix="Jinger launch ! & ü ", dir=artifacts)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.assertTrue(self.root.is_relative_to(artifacts.resolve()))
        for name in ("Start Jinger.cmd", "Setup Jinger.cmd"):
            shutil.copyfile(ROOT / name, self.root / name)
        (self.root / "More").mkdir()
        shutil.copyfile(ROOT / "More" / "Check Setup.cmd", self.root / "More" / "Check Setup.cmd")
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("Create-Shortcut.ps1", "ShortcutAppId.ps1", "Setup-Jinger.ps1"):
            shutil.copyfile(ROOT / "scripts" / name, scripts / name)
        python = Path(sys.executable)
        if not python.with_name("pythonw.exe").exists():
            self.skipTest("Windowed Python executable unavailable")
        target = self.root / ".venv" / "Scripts"
        target.mkdir(parents=True)
        shutil.copyfile(python, target / "python.exe")
        shutil.copyfile(python.with_name("pythonw.exe"), target / "pythonw.exe")
        (self.root / ".venv" / "pyvenv.cfg").write_text(
            f"home = {sys.base_prefix}\ninclude-system-site-packages = false\n", encoding="utf-8")
        (self.root / "launch_jinger.pyw").write_text(
            "import json,os,sys\nfrom pathlib import Path\n"
            "Path(__file__).with_name('launched.json').write_text(json.dumps({'args':sys.argv,'cwd':os.getcwd(),'pid':os.getpid(),'parent':os.getppid()}),encoding='utf-8')\n",
            encoding="utf-8",
        )
        package = self.root / "companion" / "app"
        package.mkdir(parents=True)
        (package.parent / "__init__.py").write_text("")
        (package / "__init__.py").write_text("")
        (package / "doctor.py").write_text("print('Isolated diagnostic stub; no installation performed.')\n")
        (self.root / ".env").write_text("Keep this existing secret file unchanged", encoding="utf-8")

    def powershell(self, script, *arguments):
        return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(script), *map(str, arguments)], capture_output=True, timeout=30, cwd=self.root)

    def wait_for_process(self, process_id):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, process_id)
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                kernel.CloseHandle(handle)

    def test_double_click_launcher_handles_spaces_punctuation_and_another_working_directory(self):
        command = f'cmd.exe /d /s /c ""{self.root / "Start Jinger.cmd"}""'
        result = subprocess.run(command, input=b"\n", cwd=self.root.parent, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.root / "launched.json"
        deadline = time.monotonic() + 5
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(output.exists(), "Windowed Python did not run the launch target")
        values = json.loads(output.read_text(encoding="utf-8"))
        self.wait_for_process(values["pid"])
        self.wait_for_process(values["parent"])
        self.assertEqual(Path(values["cwd"]).resolve(), self.root)
        self.assertEqual(Path(values["args"][0]).resolve(), self.root / "launch_jinger.pyw")

    def test_launchers_in_the_more_folder_run_from_the_project_folder(self):
        command = f'cmd.exe /d /s /c ""{self.root / "More" / "Check Setup.cmd"}""'
        result = subprocess.run(command, input=b"\n", cwd=self.root.parent, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"Isolated diagnostic stub", result.stdout)

    def test_setup_check_only_does_not_install_or_overwrite_env(self):
        original = (self.root / ".env").read_bytes()
        result = self.powershell(self.root / "scripts" / "Setup-Jinger.ps1", "-CheckOnly")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"Isolated diagnostic stub", result.stdout)
        self.assertEqual((self.root / ".env").read_bytes(), original)

    def test_missing_environment_reports_setup_instead_of_trying_system_python(self):
        (self.root / ".venv" / "Scripts" / "pythonw.exe").unlink()
        command = f'cmd.exe /d /s /c ""{self.root / "Start Jinger.cmd"}""'
        result = subprocess.run(command, input=b"\n", cwd=self.root.parent, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"Setup Jinger.cmd", result.stdout)
        self.assertFalse((self.root / "launched.json").exists())

    def test_setup_preserves_existing_env_and_creates_template_only_when_missing(self):
        # A local pip stub records commands; no package installer or network is invoked.
        (self.root / "pip.py").write_text("import json,sys\nfrom pathlib import Path\n"
                                         "with Path('pip-actions.jsonl').open('a') as output: output.write(json.dumps(sys.argv[1:])+'\\n')\n")
        (self.root / ".env.example").write_text("OPENROUTER_API_KEY=your_key_here\n")
        original = (self.root / ".env").read_bytes()
        script = self.root / "scripts" / "Setup-Jinger.ps1"
        result = self.powershell(script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".env").read_bytes(), original)
        commands = [json.loads(line) for line in (self.root / "pip-actions.jsonl").read_text().splitlines()]
        self.assertEqual(len(commands), 3)
        self.assertIn("https://download.pytorch.org/whl/cpu", commands[1])
        self.assertEqual(commands[2][-1], str(self.root / "requirements.txt"))
        (self.root / ".env").unlink()
        result = self.powershell(script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".env").read_bytes(), (self.root / ".env.example").read_bytes())

    def test_shortcut_target_is_direct_and_foreign_shortcut_is_not_overwritten(self):
        result = self.powershell(self.root / "scripts" / "Create-Shortcut.ps1", "-Destination", self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        shortcut = self.root / "Jingliu.lnk"
        self.assertTrue(shortcut.exists())
        inspector = self.root / "inspect.ps1"
        inspector.write_text('''param([string]$Link,[string]$OutputFile,[switch]$Foreign)
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($Link)
if ($Foreign) { $shortcut.TargetPath=Join-Path $env:SystemRoot 'notepad.exe'; $shortcut.Save() }
$item=(New-Object -ComObject Shell.Application).NameSpace((Split-Path $Link)).ParseName((Split-Path $Link -Leaf))
[IO.File]::WriteAllText($OutputFile,(@{target=$shortcut.TargetPath;arguments=$shortcut.Arguments;directory=$shortcut.WorkingDirectory;appid=$item.ExtendedProperty('System.AppUserModel.ID')}|ConvertTo-Json))
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut)
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
''', encoding="utf-8")
        output = self.root / "shortcut.json"
        result = self.powershell(inspector, "-Link", shortcut, "-OutputFile", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(output.read_text(encoding="utf-8-sig"))
        self.assertEqual(Path(values["target"]).resolve(), self.root / ".venv" / "Scripts" / "pythonw.exe")
        self.assertEqual(values["arguments"], f'"{self.root / "launch_jinger.pyw"}"')
        self.assertEqual(Path(values["directory"]).resolve(), self.root)
        self.assertEqual(values["appid"], "Jingliu.DesktopCompanion")  # Groups with the running window.
        self.powershell(inspector, "-Link", shortcut, "-OutputFile", output, "-Foreign")
        original = shortcut.read_bytes()
        result = self.powershell(self.root / "scripts" / "Create-Shortcut.ps1", "-Destination", self.root)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(shortcut.read_bytes(), original)
