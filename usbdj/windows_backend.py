from __future__ import annotations

import json
import locale
import shutil
import subprocess
import tempfile
from pathlib import Path

from usbdj.models import (
    DiskInfo,
    FormatMode,
    FormatPlan,
    FormatResult,
    FormatterEngine,
    VolumeValidation,
)
from usbdj.planner import create_format_plan


class BackendError(RuntimeError):
    pass


def _subprocess_window_kwargs() -> dict[str, object]:
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run_powershell(script: str) -> str:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        **_subprocess_window_kwargs(),
    )
    if result.returncode != 0:
        raise BackendError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def is_windows_admin() -> bool:
    script = (
        "$principal = New-Object Security.Principal.WindowsPrincipal("
        "[Security.Principal.WindowsIdentity]::GetCurrent()); "
        "$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
    )
    try:
        return _run_powershell(script).strip().lower() == "true"
    except BackendError:
        return False


def list_removable_disks() -> list[DiskInfo]:
    script = r"""
$disks = Get-Disk | Where-Object {
  $_.BusType -eq 'USB' -and $_.Number -ne (Get-Partition | Where-Object DriveLetter -eq $env:SystemDrive[0]).DiskNumber
}
$disks | Select-Object Number,FriendlyName,Size,BusType,IsBoot,IsSystem,NumberOfPartitions |
  ConvertTo-Json -Compress
"""
    output = _run_powershell(script)
    if not output:
        return []
    data = json.loads(output)
    if isinstance(data, dict):
        data = [data]

    disks: list[DiskInfo] = []
    for item in data:
        if item.get("IsBoot") or item.get("IsSystem"):
            continue
        disks.append(
            DiskInfo(
                number=int(item["Number"]),
                friendly_name=str(item.get("FriendlyName") or "USB"),
                size_bytes=int(item["Size"]),
                bus_type=str(item.get("BusType") or "USB"),
                is_removable=True,
                partitions=int(item.get("NumberOfPartitions") or 0),
            )
        )
    return disks


def find_available_drive_letter() -> str:
    output = _run_powershell(
        "(Get-Volume | Where-Object DriveLetter | "
        "ForEach-Object { $_.DriveLetter }) -join ','"
    )
    used = {letter.strip().upper() for letter in output.split(",") if letter.strip()}
    for letter in "ZYXWVUTSRQPONMLKJIHGFED":
        if letter not in used:
            return letter
    raise BackendError("Nenhuma letra de unidade livre encontrada.")


def find_existing_drive_letter(disk_number: int) -> str | None:
    script = (
        f"Get-Partition -DiskNumber {disk_number} | "
        "Where-Object DriveLetter | "
        "Select-Object -First 1 -ExpandProperty DriveLetter"
    )
    try:
        output = _run_powershell(script).strip()
    except BackendError:
        return None
    if not output:
        return None
    return output[0].upper()


def release_disk_volumes(disk_number: int, log_path: Path | None = None) -> None:
    script = rf"""
$parts = Get-Partition -DiskNumber {disk_number} | Where-Object DriveLetter
foreach ($part in $parts) {{
  $letter = $part.DriveLetter
  Write-Output "Liberando volume $letter`:"
  Dismount-Volume -DriveLetter $letter -Force -ErrorAction SilentlyContinue
  Remove-PartitionAccessPath -DiskNumber {disk_number} -PartitionNumber $part.PartitionNumber -AccessPath "$letter`:\" -ErrorAction SilentlyContinue
}}
"""
    try:
        output = _run_powershell(script)
    except BackendError as exc:
        _append_log(log_path, f"Aviso ao liberar volumes: {exc}")
        return
    if output:
        _append_log(log_path, output)


def choose_drive_letter(disk_number: int) -> str:
    existing = find_existing_drive_letter(disk_number)
    if existing:
        return existing
    return find_available_drive_letter()


def build_diskpart_script(disk_number: int, plan: FormatPlan, drive_letter: str) -> str:
    if disk_number < 0:
        raise ValueError("disk_number invalido")
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        raise ValueError("drive_letter invalida")

    lines = [
        f"select disk {disk_number}",
        "attributes disk clear readonly noerr",
        "clean",
        f"convert {plan.partition_style.lower()}",
        "create partition primary",
    ]
    if plan.engine == FormatterEngine.WINDOWS_NATIVE:
        lines.append(_diskpart_format_command(plan))
    lines.append(f"assign letter={drive_letter.upper()}")
    return "\n".join(lines) + "\n"


def _diskpart_format_command(plan: FormatPlan) -> str:
    label = plan.label.replace('"', "")[:32]
    parts = [
        "format",
        f"fs={plan.filesystem.value}",
        "quick",
        f'label="{label}"',
    ]
    if plan.allocation_unit_size:
        parts.append(f"unit={plan.allocation_unit_size}")
    return " ".join(parts)


def prepare_disk(
    disk: DiskInfo,
    mode: FormatMode,
    *,
    fat32_helper: Path | None = None,
    dry_run: bool = True,
    log_path: Path | None = None,
    plan_override: FormatPlan | None = None,
) -> FormatResult | FormatPlan:
    plan = plan_override or create_format_plan(mode, disk.size_bytes)
    drive_letter = choose_drive_letter(disk.number)
    diskpart_script = build_diskpart_script(disk.number, plan, drive_letter)

    if dry_run:
        return plan

    if not is_windows_admin():
        raise BackendError(
            "O Windows pediu permissao para preparar o pendrive. "
            "Feche o app e abra novamente aceitando a permissao do Windows."
        )

    if not disk.is_removable or disk.bus_type.upper() != "USB":
        raise BackendError("Por seguranca, apenas discos USB removiveis podem ser formatados.")

    _append_log(log_path, f"Preparando disco {disk.number}: {disk.friendly_name}")
    _append_log(log_path, f"Plano: {plan}")
    _append_log(log_path, f"Letra de unidade escolhida: {drive_letter.upper()}:")
    release_disk_volumes(disk.number, log_path)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        suffix="-usbdj-diskpart.txt",
        delete=False,
    )
    script_path = Path(handle.name)
    try:
        handle.write(diskpart_script)
        handle.close()
        _append_log(log_path, f"Executando diskpart com letra {drive_letter}:")
        _append_log(log_path, diskpart_script)
        _run_checked(["diskpart", "/s", str(script_path)], log_path)
    finally:
        handle.close()
        try:
            script_path.unlink()
        except OSError:
            pass

    if plan.engine == FormatterEngine.WINDOWS_NATIVE:
        _append_log(log_path, "Formatacao nativa concluida pelo diskpart.")
    else:
        helper = fat32_helper or Path("tools") / "fat32format.exe"
        _format_with_large_fat32_helper(helper, plan, drive_letter, log_path)

    validation = validate_volume(drive_letter, plan)
    _append_log(log_path, validation.message)
    if not validation.is_valid:
        raise BackendError(validation.message)

    return FormatResult(plan=plan, drive_letter=drive_letter, validation=validation)


def _format_with_windows(
    plan: FormatPlan,
    drive_letter: str,
    log_path: Path | None = None,
) -> None:
    allocation = ""
    if plan.allocation_unit_size:
        allocation = f"-AllocationUnitSize {plan.allocation_unit_size}"
    _append_log(log_path, f"Formatando {drive_letter.upper()}: como {plan.filesystem.value}")
    script = (
        f"Format-Volume -DriveLetter {drive_letter.upper()} -FileSystem {plan.filesystem.value} "
        f"-NewFileSystemLabel '{plan.label}' {allocation} -Confirm:$false -Force"
    )
    _run_powershell(script)
    _append_log(log_path, "Formatacao nativa concluida.")


def _format_with_large_fat32_helper(
    helper: Path,
    plan: FormatPlan,
    drive_letter: str,
    log_path: Path | None = None,
) -> None:
    helper_path = Path(helper)
    if not helper_path.exists():
        raise BackendError(
            f"Helper FAT32 grande nao encontrado: {helper_path}. "
            "Adicione uma ferramenta validada antes de formatar FAT32 acima de 32 GiB."
        )
    resolved = shutil.which(str(helper_path)) or str(helper_path)
    _append_log(log_path, f"Executando helper FAT32 grande em {drive_letter.upper()}:")
    _run_checked([resolved, f"{drive_letter.upper()}:"], log_path)
    _run_powershell(
        f"Set-Volume -DriveLetter {drive_letter.upper()} "
        f"-NewFileSystemLabel '{plan.label}'"
    )
    _append_log(log_path, "Helper FAT32 grande concluido.")


def validate_volume(drive_letter: str, plan: FormatPlan) -> VolumeValidation:
    script = (
        f"$vol = Get-Volume -DriveLetter {drive_letter.upper()}; "
        "$part = Get-Partition -DriveLetter $vol.DriveLetter; "
        "$disk = Get-Disk -Number $part.DiskNumber; "
        "[PSCustomObject]@{"
        "DriveLetter=$vol.DriveLetter;"
        "FileSystem=$vol.FileSystem;"
        "Label=$vol.FileSystemLabel;"
        "Size=$vol.Size;"
        "PartitionStyle=$disk.PartitionStyle"
        "} | ConvertTo-Json -Compress"
    )
    data = json.loads(_run_powershell(script))
    filesystem = str(data.get("FileSystem") or "")
    label = str(data.get("Label") or "")
    partition_style = str(data.get("PartitionStyle") or "")
    size = int(data.get("Size") or 0)
    expected_fs = plan.filesystem.value.lower()

    is_valid = (
        filesystem.lower() == expected_fs
        and label == plan.label
        and partition_style.upper() == plan.partition_style.upper()
    )
    message = (
        f"Validacao {'OK' if is_valid else 'falhou'}: "
        f"{drive_letter.upper()}: {filesystem}, {partition_style}, label={label}, size={size}"
    )
    return VolumeValidation(
        drive_letter=drive_letter.upper(),
        filesystem=filesystem,
        label=label,
        size_bytes=size,
        is_valid=is_valid,
        message=message,
    )


def _run_checked(command: list[str], log_path: Path | None = None) -> None:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        **_subprocess_window_kwargs(),
    )
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if stdout:
        _append_log(log_path, stdout)
    if stderr:
        _append_log(log_path, stderr)
    if result.returncode != 0:
        raise BackendError(_friendly_process_error(stdout, stderr, command))


def _decode_process_output(output: bytes) -> str:
    if not output:
        return ""
    encodings = ["utf-8", "cp850", locale.getpreferredencoding(False), "cp1252"]
    for encoding in encodings:
        try:
            return output.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return output.decode("utf-8", errors="replace").strip()


def _friendly_process_error(stdout: str, stderr: str, command: list[str]) -> str:
    combined = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)
    normalized = combined.lower()
    if "acesso negado" in normalized or "access is denied" in normalized:
        return (
            "O Windows bloqueou a limpeza do pendrive (acesso negado). "
            "Feche janelas do Explorer ou programas usando o pendrive, remova e conecte de novo, "
            "e tente novamente."
        )
    if "write protected" in normalized or "protegido contra grava" in normalized:
        return "O pendrive parece estar protegido contra gravacao."
    if combined:
        return combined
    return "Falha ao executar: " + " ".join(command)


def _append_log(log_path: Path | None, message: str) -> None:
    if not log_path:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip() + "\n")
