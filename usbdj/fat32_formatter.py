from __future__ import annotations

import ctypes
import math
import random
import struct
from dataclasses import dataclass


FAT32_MIN_CLUSTERS = 65525
FAT32_MEDIA_FIXED = 0xF8
FAT32_EOC = 0x0FFFFFFF


class Fat32FormatError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fat32Layout:
    total_sectors: int
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    fat_size_sectors: int
    cluster_count: int
    root_cluster: int

    @property
    def fat_start_sector(self) -> int:
        return self.reserved_sectors

    @property
    def data_start_sector(self) -> int:
        return self.reserved_sectors + self.fat_count * self.fat_size_sectors

    @property
    def root_dir_sector(self) -> int:
        return self.data_start_sector + (
            (self.root_cluster - 2) * self.sectors_per_cluster
        )


def create_fat32_layout(
    total_bytes: int,
    *,
    bytes_per_sector: int = 512,
    allocation_unit_size: int | None = 32768,
) -> Fat32Layout:
    if total_bytes <= 0:
        raise Fat32FormatError("Tamanho do volume invalido para FAT32.")
    if bytes_per_sector not in {512, 1024, 2048, 4096}:
        raise Fat32FormatError(f"Setor logico nao suportado: {bytes_per_sector}.")

    cluster_bytes = allocation_unit_size or 32768
    if cluster_bytes < bytes_per_sector or cluster_bytes % bytes_per_sector != 0:
        raise Fat32FormatError("Cluster FAT32 invalido para o setor logico do disco.")
    sectors_per_cluster = cluster_bytes // bytes_per_sector
    if sectors_per_cluster & (sectors_per_cluster - 1):
        raise Fat32FormatError("Cluster FAT32 precisa ser potencia de dois.")
    if sectors_per_cluster > 128:
        raise Fat32FormatError("Cluster FAT32 acima de 64 KiB nao e suportado.")

    total_sectors = total_bytes // bytes_per_sector
    reserved_sectors = 32
    fat_count = 2
    root_cluster = 2
    fat_size = 1

    while True:
        data_sectors = total_sectors - reserved_sectors - fat_count * fat_size
        if data_sectors <= 0:
            raise Fat32FormatError("Volume pequeno demais para FAT32.")
        cluster_count = data_sectors // sectors_per_cluster
        required_fat_size = math.ceil((cluster_count + 2) * 4 / bytes_per_sector)
        if required_fat_size == fat_size:
            break
        fat_size = required_fat_size

    if cluster_count < FAT32_MIN_CLUSTERS:
        raise Fat32FormatError("Volume nao tem clusters suficientes para FAT32.")
    if total_sectors > 0xFFFFFFFF:
        raise Fat32FormatError("Volume FAT32 acima de 2 TiB nao e suportado.")

    return Fat32Layout(
        total_sectors=total_sectors,
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size,
        cluster_count=cluster_count,
        root_cluster=root_cluster,
    )


def build_boot_sector(layout: Fat32Layout, label: str, serial: int | None = None) -> bytes:
    sector = bytearray(layout.bytes_per_sector)
    volume_label = _fat_label(label)
    serial = random.getrandbits(32) if serial is None else serial & 0xFFFFFFFF

    sector[0:3] = b"\xEB\x58\x90"
    sector[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", sector, 11, layout.bytes_per_sector)
    sector[13] = layout.sectors_per_cluster
    struct.pack_into("<H", sector, 14, layout.reserved_sectors)
    sector[16] = layout.fat_count
    struct.pack_into("<H", sector, 17, 0)
    struct.pack_into("<H", sector, 19, 0)
    sector[21] = FAT32_MEDIA_FIXED
    struct.pack_into("<H", sector, 22, 0)
    struct.pack_into("<H", sector, 24, 63)
    struct.pack_into("<H", sector, 26, 255)
    struct.pack_into("<I", sector, 28, 0)
    struct.pack_into("<I", sector, 32, layout.total_sectors)
    struct.pack_into("<I", sector, 36, layout.fat_size_sectors)
    struct.pack_into("<H", sector, 40, 0)
    struct.pack_into("<H", sector, 42, 0)
    struct.pack_into("<I", sector, 44, layout.root_cluster)
    struct.pack_into("<H", sector, 48, 1)
    struct.pack_into("<H", sector, 50, 6)
    sector[64] = 0x80
    sector[66] = 0x29
    struct.pack_into("<I", sector, 67, serial)
    sector[71:82] = volume_label
    sector[82:90] = b"FAT32   "
    sector[-2:] = b"\x55\xAA"
    return bytes(sector)


def build_fsinfo_sector(layout: Fat32Layout) -> bytes:
    sector = bytearray(layout.bytes_per_sector)
    struct.pack_into("<I", sector, 0, 0x41615252)
    struct.pack_into("<I", sector, 484, 0x61417272)
    struct.pack_into("<I", sector, 488, layout.cluster_count - 1)
    struct.pack_into("<I", sector, 492, 3)
    struct.pack_into("<I", sector, 508, 0xAA550000)
    return bytes(sector)


def build_fat_header(layout: Fat32Layout) -> bytes:
    sector = bytearray(layout.bytes_per_sector)
    struct.pack_into("<I", sector, 0, 0x0FFFFF00 | FAT32_MEDIA_FIXED)
    struct.pack_into("<I", sector, 4, 0xFFFFFFFF)
    struct.pack_into("<I", sector, 8, FAT32_EOC)
    return bytes(sector)


def build_root_directory_cluster(layout: Fat32Layout, label: str) -> bytes:
    cluster = bytearray(layout.bytes_per_sector * layout.sectors_per_cluster)
    cluster[0:11] = _fat_label(label)
    cluster[11] = 0x08
    return bytes(cluster)


def format_fat32_volume(
    drive_letter: str,
    *,
    total_bytes: int,
    bytes_per_sector: int,
    allocation_unit_size: int | None,
    label: str,
) -> Fat32Layout:
    layout = create_fat32_layout(
        total_bytes,
        bytes_per_sector=bytes_per_sector,
        allocation_unit_size=allocation_unit_size,
    )
    _write_fat32_volume(drive_letter, layout, label)
    return layout


def _write_fat32_volume(drive_letter: str, layout: Fat32Layout, label: str) -> None:
    volume = _RawVolume(drive_letter)
    try:
        volume.lock()
        volume.dismount()
        zero = bytes(layout.bytes_per_sector)
        boot = build_boot_sector(layout, label)
        fsinfo = build_fsinfo_sector(layout)
        fat_header = build_fat_header(layout)
        root_dir = build_root_directory_cluster(layout, label)

        volume.write_sector(0, boot)
        volume.write_sector(1, fsinfo)
        volume.write_sector(2, zero)
        volume.write_sector(6, boot)
        volume.write_sector(7, fsinfo)
        volume.write_sector(8, zero)

        for fat_index in range(layout.fat_count):
            fat_start = layout.fat_start_sector + fat_index * layout.fat_size_sectors
            volume.write_sector(fat_start, fat_header)
            volume.zero_sectors(fat_start + 1, layout.fat_size_sectors - 1, zero)

        volume.write_at(layout.root_dir_sector * layout.bytes_per_sector, root_dir)
    finally:
        volume.close()


def _fat_label(label: str) -> bytes:
    cleaned = "".join(char for char in label.upper() if char not in '"*+,./:;<=>?[\\]|')
    return cleaned.encode("ascii", errors="replace")[:11].ljust(11, b" ")


class _RawVolume:
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    FSCTL_LOCK_VOLUME = 0x00090018
    FSCTL_DISMOUNT_VOLUME = 0x00090020
    FSCTL_UNLOCK_VOLUME = 0x0009001C
    FILE_BEGIN = 0

    def __init__(self, drive_letter: str) -> None:
        self.drive_letter = drive_letter.upper()[0]
        path = f"\\\\.\\{self.drive_letter}:"
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        self.kernel32.CreateFileW.restype = ctypes.c_void_p
        self.kernel32.DeviceIoControl.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,
        ]
        self.kernel32.DeviceIoControl.restype = ctypes.c_int
        self.kernel32.SetFilePointerEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_longlong),
            ctypes.c_ulong,
        ]
        self.kernel32.SetFilePointerEx.restype = ctypes.c_int
        self.kernel32.WriteFile.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,
        ]
        self.kernel32.WriteFile.restype = ctypes.c_int
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int
        self.handle = self.kernel32.CreateFileW(
            path,
            self.GENERIC_READ | self.GENERIC_WRITE,
            self.FILE_SHARE_READ | self.FILE_SHARE_WRITE,
            None,
            self.OPEN_EXISTING,
            0,
            None,
        )
        if self.handle == self.INVALID_HANDLE_VALUE:
            raise Fat32FormatError(f"Nao foi possivel abrir o volume {self.drive_letter}:")

    def lock(self) -> None:
        self._device_io(self.FSCTL_LOCK_VOLUME, "bloquear")

    def dismount(self) -> None:
        self._device_io(self.FSCTL_DISMOUNT_VOLUME, "desmontar")

    def write_sector(self, sector: int, data: bytes) -> None:
        self._seek(sector * len(data))
        self._write(data)

    def write_at(self, offset: int, data: bytes) -> None:
        self._seek(offset)
        self._write(data)

    def zero_sectors(self, start_sector: int, count: int, zero_sector: bytes) -> None:
        if count <= 0:
            return
        chunk = zero_sector * min(count, 256)
        remaining = count
        sector = start_sector
        while remaining:
            sectors_now = min(remaining, 256)
            self._seek(sector * len(zero_sector))
            self._write(chunk[: sectors_now * len(zero_sector)])
            sector += sectors_now
            remaining -= sectors_now

    def close(self) -> None:
        if self.handle and self.handle != self.INVALID_HANDLE_VALUE:
            self._device_io(self.FSCTL_UNLOCK_VOLUME, "liberar", raise_on_error=False)
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def _seek(self, offset: int) -> None:
        new_position = ctypes.c_longlong()
        ok = self.kernel32.SetFilePointerEx(
            self.handle,
            ctypes.c_longlong(offset),
            ctypes.byref(new_position),
            self.FILE_BEGIN,
        )
        if not ok:
            raise Fat32FormatError("Falha ao posicionar escrita FAT32 no volume.")

    def _write(self, data: bytes) -> None:
        written = ctypes.c_ulong()
        buffer = ctypes.create_string_buffer(data)
        ok = self.kernel32.WriteFile(
            self.handle,
            buffer,
            len(data),
            ctypes.byref(written),
            None,
        )
        if not ok or written.value != len(data):
            raise Fat32FormatError("Falha ao escrever estruturas FAT32 no volume.")

    def _device_io(self, code: int, action: str, *, raise_on_error: bool = True) -> None:
        returned = ctypes.c_ulong()
        ok = self.kernel32.DeviceIoControl(
            self.handle,
            code,
            None,
            0,
            None,
            0,
            ctypes.byref(returned),
            None,
        )
        if not ok and raise_on_error:
            raise Fat32FormatError(f"Falha ao {action} o volume {self.drive_letter}:")
