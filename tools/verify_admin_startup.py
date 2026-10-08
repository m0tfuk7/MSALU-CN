"""Offline checks for automatic GUI elevation: python -m tools.verify_admin_startup."""

import subprocess
import unittest
from unittest.mock import patch

from src import main as entry


class AdminStartupTests(unittest.TestCase):
    def setUp(self):
        self.platform = patch.object(entry.sys, "platform", "win32")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.windll = patch.object(entry.ctypes, "windll")
        self.api = self.windll.start()
        self.addCleanup(self.windll.stop)
        self.api.shell32.IsUserAnAdmin.return_value = 0
        self.api.shell32.ShellExecuteW.return_value = 42

    def test_already_admin_does_not_relaunch(self):
        self.api.shell32.IsUserAnAdmin.return_value = 1
        self.assertTrue(entry._ensure_admin())
        self.api.shell32.ShellExecuteW.assert_not_called()

    def test_source_preserves_interpreter_args_and_working_directory(self):
        args = ["-X", "utf8", r"C:\项目 空格\run_gui.py", "--name", 'a "b"']
        with patch.object(entry.sys, "frozen", False, create=True), \
                patch.object(entry.sys, "orig_argv", ["pythonw", *args]), \
                patch.object(entry.sys, "executable", r"C:\venv space\pythonw.exe"):
            self.assertFalse(entry._ensure_admin())
        self.api.shell32.ShellExecuteW.assert_called_once_with(
            None, "runas", r"C:\venv space\pythonw.exe",
            subprocess.list2cmdline(args), entry.os.getcwd(), 1)

    def test_module_entry_is_preserved(self):
        with patch.object(entry.sys, "frozen", False, create=True), \
                patch.object(entry.sys, "orig_argv", ["python", "-m", "src.main"]):
            self.assertFalse(entry._ensure_admin())
        self.assertEqual(self.api.shell32.ShellExecuteW.call_args.args[3], "-m src.main")

    def test_frozen_tool_preserves_arguments_without_python_script(self):
        args = ["--tool", "tools.routeRecorder", "--new_map", "map with spaces"]
        with patch.object(entry.sys, "frozen", True, create=True), \
                patch.object(entry.sys, "argv", ["app.exe", *args]):
            self.assertFalse(entry._ensure_admin())
        self.assertEqual(self.api.shell32.ShellExecuteW.call_args.args[3],
                         subprocess.list2cmdline(args))

    def test_cancel_and_launch_errors_notify_and_raise(self):
        with patch("src.utils.logger.logger") as logger:
            for result in (None, 0, 2, 5, 31, 32):
                with self.subTest(result=result):
                    self.api.shell32.ShellExecuteW.return_value = result
                    with self.assertRaises(PermissionError):
                        entry._ensure_admin()
            self.assertEqual(logger.error.call_count, 6)
            self.assertEqual(self.api.user32.MessageBoxW.call_count, 6)

    def test_parent_exits_before_gui_or_tools_start(self):
        with patch.object(entry, "_ensure_admin", return_value=False), \
                patch.object(entry, "_run_tool") as run_tool, \
                patch.object(entry.sys, "argv", ["app.exe", "--tool", "tools.diagnose"]):
            self.assertIsNone(entry.main())
        run_tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
