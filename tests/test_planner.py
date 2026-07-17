import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from usbdj.models import Filesystem, FormatMode, FormatterEngine
from usbdj.planner import create_format_plan
import usbdj.windows_backend as windows_backend
from usbdj.windows_backend import build_diskpart_script


class PlannerTests(unittest.TestCase):
    def assertSamePath(self, actual: Path, expected: Path) -> None:
        if actual.exists() and expected.exists():
            self.assertTrue(actual.samefile(expected), f"{actual} != {expected}")
            return
        self.assertEqual(
            actual.resolve().as_posix().lower(),
            expected.resolve().as_posix().lower(),
        )

    def test_legacy_uses_windows_native_at_32_gib(self) -> None:
        plan = create_format_plan(FormatMode.LEGACY, 32 * 1024**3)

        self.assertEqual(plan.engine, FormatterEngine.WINDOWS_NATIVE)
        self.assertEqual(plan.filesystem.value, "FAT32")
        self.assertEqual(plan.partition_style, "MBR")

    def test_legacy_uses_large_fat32_helper_above_32_gib(self) -> None:
        plan = create_format_plan(FormatMode.LEGACY, 33 * 1024**3)

        self.assertEqual(plan.engine, FormatterEngine.LARGE_FAT32_HELPER)
        self.assertIsNotNone(plan.warning)

    def test_modern_uses_exfat_windows_native(self) -> None:
        plan = create_format_plan(FormatMode.MODERN, 128 * 1024**3)

        self.assertEqual(plan.engine, FormatterEngine.WINDOWS_NATIVE)
        self.assertEqual(plan.filesystem.value, "exFAT")
        self.assertEqual(plan.partition_style, "MBR")

    def test_diskpart_script_assigns_requested_letter(self) -> None:
        plan = create_format_plan(FormatMode.LEGACY, 16 * 1024**3)
        script = build_diskpart_script(3, plan, "Z")

        self.assertIn("select disk 3", script)
        self.assertIn("convert mbr", script)
        self.assertIn('format fs=FAT32 quick label="CDJ_USB" unit=32768', script)
        self.assertIn("assign letter=Z", script)
        self.assertNotIn("online disk", script)
        self.assertLess(script.index("format fs=FAT32"), script.index("assign letter=Z"))

    def test_diskpart_script_leaves_format_to_helper_when_needed(self) -> None:
        plan = create_format_plan(FormatMode.LEGACY, 64 * 1024**3)
        script = build_diskpart_script(3, plan, "Z")

        self.assertNotIn("format fs=", script)
        self.assertIn("assign letter=Z", script)

    def test_choose_drive_letter_reuses_existing_letter(self) -> None:
        original = windows_backend._run_powershell
        windows_backend._run_powershell = lambda _script: "E"
        try:
            self.assertEqual(windows_backend.choose_drive_letter(2), "E")
        finally:
            windows_backend._run_powershell = original

    def test_choose_drive_letter_falls_back_when_no_existing_letter(self) -> None:
        original = windows_backend._run_powershell

        def fake_run(script: str) -> str:
            if "Get-Partition" in script:
                return ""
            return "C,D,E"

        windows_backend._run_powershell = fake_run
        try:
            self.assertEqual(windows_backend.choose_drive_letter(2), "Z")
        finally:
            windows_backend._run_powershell = original

    def test_release_disk_volumes_logs_powershell_output(self) -> None:
        original = windows_backend._run_powershell
        messages: list[str] = []
        original_append_log = windows_backend._append_log

        windows_backend._run_powershell = lambda _script: "Liberando volume E:"
        windows_backend._append_log = lambda _path, message: messages.append(message)
        try:
            windows_backend.release_disk_volumes(2)
        finally:
            windows_backend._run_powershell = original
            windows_backend._append_log = original_append_log

        self.assertEqual(messages, ["Liberando volume E:"])

    def test_advanced_can_override_modern_to_fat32(self) -> None:
        plan = create_format_plan(
            FormatMode.MODERN,
            16 * 1024**3,
            filesystem=Filesystem.FAT32,
            partition_style="GPT",
            allocation_unit_size=64 * 1024,
            label="TESTE",
        )

        self.assertEqual(plan.filesystem, Filesystem.FAT32)
        self.assertEqual(plan.partition_style, "GPT")
        self.assertEqual(plan.allocation_unit_size, 64 * 1024)
        self.assertEqual(plan.label, "TESTE")

    def test_friendly_access_denied_error(self) -> None:
        message = windows_backend._friendly_process_error(
            "O DiskPart encontrou um erro: Acesso negado.",
            "",
            ["diskpart"],
        )

        self.assertIn("acesso negado", message.lower())
        self.assertIn("pendrive", message.lower())

    def test_default_fat32_helper_uses_project_tools_in_development(self) -> None:
        expected = Path(windows_backend.__file__).resolve().parents[1] / "tools" / "fat32format.exe"

        self.assertEqual(windows_backend.default_fat32_helper_path(), expected)

    def test_default_fat32_helper_prefers_env_var(self) -> None:
        original_env = windows_backend.os.environ.get(windows_backend.FAT32_HELPER_ENV)
        with TemporaryDirectory() as temp_dir:
            helper = Path(temp_dir) / "fat32format.exe"
            helper.write_bytes(b"")
            windows_backend.os.environ[windows_backend.FAT32_HELPER_ENV] = str(helper)
            try:
                self.assertSamePath(windows_backend.default_fat32_helper_path(), helper)
                self.assertSamePath(windows_backend.require_fat32_helper(), helper)
            finally:
                if original_env is None:
                    windows_backend.os.environ.pop(windows_backend.FAT32_HELPER_ENV, None)
                else:
                    windows_backend.os.environ[windows_backend.FAT32_HELPER_ENV] = original_env

    def test_require_fat32_helper_reports_missing_candidates(self) -> None:
        missing = Path("missing-fat32format.exe")

        with self.assertRaises(windows_backend.BackendError) as ctx:
            windows_backend.require_fat32_helper(missing)

        self.assertIn(str(missing), str(ctx.exception))
        self.assertIn("USBDJ_FAT32_HELPER", str(ctx.exception))

    def test_default_fat32_helper_prefers_bundled_tool_when_frozen(self) -> None:
        original_meipass = getattr(windows_backend.sys, "_MEIPASS", None)
        had_meipass = hasattr(windows_backend.sys, "_MEIPASS")
        original_frozen = getattr(windows_backend.sys, "frozen", None)
        had_frozen = hasattr(windows_backend.sys, "frozen")
        original_executable = windows_backend.sys.executable
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            helper = temp_path / "tools" / "fat32format.exe"
            helper.parent.mkdir()
            helper.write_bytes(b"")
            windows_backend.sys._MEIPASS = str(temp_path)  # type: ignore[attr-defined]
            windows_backend.sys.frozen = True  # type: ignore[attr-defined]
            windows_backend.sys.executable = str(temp_path / "USB-DJ-Formatter.exe")
            try:
                self.assertSamePath(windows_backend.default_fat32_helper_path(), helper)
            finally:
                if had_meipass:
                    windows_backend.sys._MEIPASS = original_meipass  # type: ignore[attr-defined]
                else:
                    delattr(windows_backend.sys, "_MEIPASS")
                if had_frozen:
                    windows_backend.sys.frozen = original_frozen  # type: ignore[attr-defined]
                else:
                    delattr(windows_backend.sys, "frozen")
                windows_backend.sys.executable = original_executable

    def test_default_fat32_helper_accepts_helper_next_to_frozen_exe(self) -> None:
        original_meipass = getattr(windows_backend.sys, "_MEIPASS", None)
        had_meipass = hasattr(windows_backend.sys, "_MEIPASS")
        original_frozen = getattr(windows_backend.sys, "frozen", None)
        had_frozen = hasattr(windows_backend.sys, "frozen")
        original_executable = windows_backend.sys.executable
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            helper = temp_path / "fat32format.exe"
            helper.write_bytes(b"")
            windows_backend.sys._MEIPASS = str(temp_path / "_MEI123")  # type: ignore[attr-defined]
            windows_backend.sys.frozen = True  # type: ignore[attr-defined]
            windows_backend.sys.executable = str(temp_path / "USB-DJ-Formatter.exe")
            try:
                self.assertSamePath(windows_backend.default_fat32_helper_path(), helper)
            finally:
                if had_meipass:
                    windows_backend.sys._MEIPASS = original_meipass  # type: ignore[attr-defined]
                else:
                    delattr(windows_backend.sys, "_MEIPASS")
                if had_frozen:
                    windows_backend.sys.frozen = original_frozen  # type: ignore[attr-defined]
                else:
                    delattr(windows_backend.sys, "frozen")
                windows_backend.sys.executable = original_executable


if __name__ == "__main__":
    unittest.main()
