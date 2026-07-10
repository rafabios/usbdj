from __future__ import annotations

from usbdj.models import Filesystem, FormatMode, FormatPreset


LEGACY_PRESET = FormatPreset(
    mode=FormatMode.LEGACY,
    filesystem=Filesystem.FAT32,
    partition_style="MBR",
    allocation_unit_size=32 * 1024,
    label="CDJ_USB",
)

MODERN_PRESET = FormatPreset(
    mode=FormatMode.MODERN,
    filesystem=Filesystem.EXFAT,
    partition_style="MBR",
    allocation_unit_size=None,
    label="CDJ_USB",
)


SUPPORTED_HINTS = {
    FormatMode.LEGACY: [
        "CDJ-350",
        "CDJ-850",
        "CDJ-900",
        "CDJ-2000",
        "CDJ-2000NXS",
        "XDJ-AERO",
        "XDJ-R1",
        "XDJ-RX",
    ],
    FormatMode.MODERN: [
        "CDJ-3000",
        "CDJ-3000X",
        "XDJ-1000MK2",
        "XDJ-RX2",
        "XDJ-RR",
        "XDJ-XZ",
        "XDJ-RX3",
        "OPUS-QUAD",
        "OMNIS-DUO",
        "XDJ-AZ",
    ],
}
