from __future__ import annotations

from usbdj.models import Filesystem, FormatMode, FormatPlan, FormatterEngine
from usbdj.presets import LEGACY_PRESET, MODERN_PRESET

FAT32_NATIVE_LIMIT_BYTES = 32 * 1024**3
_DEFAULT_ALLOCATION = object()


def create_format_plan(
    mode: FormatMode,
    size_bytes: int,
    *,
    filesystem: Filesystem | None = None,
    partition_style: str | None = None,
    allocation_unit_size: int | None | object = _DEFAULT_ALLOCATION,
    label: str | None = None,
) -> FormatPlan:
    if size_bytes <= 0:
        raise ValueError("size_bytes precisa ser maior que zero")

    allocation_was_overridden = allocation_unit_size is not _DEFAULT_ALLOCATION

    if mode == FormatMode.LEGACY:
        selected_filesystem = filesystem or Filesystem.FAT32
        if selected_filesystem == Filesystem.FAT32:
            engine = (
                FormatterEngine.WINDOWS_NATIVE
                if size_bytes <= FAT32_NATIVE_LIMIT_BYTES
                else FormatterEngine.LARGE_FAT32_INTERNAL
            )
        else:
            engine = FormatterEngine.WINDOWS_NATIVE
        warning = None
        if engine == FormatterEngine.LARGE_FAT32_INTERNAL:
            warning = (
                "FAT32 acima de 32 GiB sera formatado pelo backend interno."
            )
        return FormatPlan(
            mode=mode,
            filesystem=selected_filesystem,
            engine=engine,
            partition_style=partition_style or LEGACY_PRESET.partition_style,
            allocation_unit_size=(
                allocation_unit_size  # type: ignore[arg-type]
                if allocation_was_overridden
                else LEGACY_PRESET.allocation_unit_size
            ),
            label=label or LEGACY_PRESET.label,
            warning=warning,
        )

    if mode == FormatMode.MODERN:
        selected_filesystem = filesystem or MODERN_PRESET.filesystem
        if selected_filesystem == Filesystem.FAT32 and size_bytes > FAT32_NATIVE_LIMIT_BYTES:
            engine = FormatterEngine.LARGE_FAT32_INTERNAL
            warning = "FAT32 acima de 32 GiB sera formatado pelo backend interno."
        else:
            engine = FormatterEngine.WINDOWS_NATIVE
            warning = None
        return FormatPlan(
            mode=mode,
            filesystem=selected_filesystem,
            engine=engine,
            partition_style=partition_style or MODERN_PRESET.partition_style,
            allocation_unit_size=(
                allocation_unit_size  # type: ignore[arg-type]
                if allocation_was_overridden
                else MODERN_PRESET.allocation_unit_size
            ),
            label=label or MODERN_PRESET.label,
            warning=warning,
        )

    raise ValueError(f"Modo desconhecido: {mode}")
