import unittest

from usbdj.models import Filesystem, FormatMode, FormatterEngine
from usbdj.planner import create_format_plan
import usbdj.windows_backend as windows_backend
from usbdj.windows_backend import build_diskpart_script


class PlannerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
