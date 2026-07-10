from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FormatMode(str, Enum):
    LEGACY = "legacy"
    MODERN = "modern"


class Filesystem(str, Enum):
    FAT32 = "FAT32"
    EXFAT = "exFAT"


class FormatterEngine(str, Enum):
    WINDOWS_NATIVE = "windows_native"
    LARGE_FAT32_HELPER = "large_fat32_helper"


@dataclass(frozen=True)
class DiskInfo:
    number: int
    friendly_name: str
    size_bytes: int
    bus_type: str
    is_removable: bool
    partitions: int = 0

    @property
    def size_gb(self) -> float:
        return self.size_bytes / 1_000_000_000


@dataclass(frozen=True)
class FormatPreset:
    mode: FormatMode
    filesystem: Filesystem
    partition_style: str
    allocation_unit_size: int | None
    label: str


@dataclass(frozen=True)
class FormatPlan:
    mode: FormatMode
    filesystem: Filesystem
    engine: FormatterEngine
    partition_style: str
    allocation_unit_size: int | None
    label: str
    warning: str | None = None


@dataclass(frozen=True)
class VolumeValidation:
    drive_letter: str
    filesystem: str
    label: str
    size_bytes: int
    is_valid: bool
    message: str


@dataclass(frozen=True)
class FormatResult:
    plan: FormatPlan
    drive_letter: str
    validation: VolumeValidation
