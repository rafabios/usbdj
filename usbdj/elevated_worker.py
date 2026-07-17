from __future__ import annotations

import argparse
import json
from pathlib import Path

from usbdj.models import Filesystem, FormatMode
from usbdj.planner import create_format_plan
from usbdj.windows_backend import BackendError, list_removable_disks, prepare_disk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk", type=int, required=True)
    parser.add_argument("--mode", choices=[mode.value for mode in FormatMode], required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--filesystem", choices=[fs.value for fs in Filesystem])
    parser.add_argument("--partition-style", choices=["MBR", "GPT"])
    parser.add_argument("--allocation-unit-size", type=int)
    parser.add_argument("--label")
    parser.add_argument("--fat32-helper", type=Path)
    args = parser.parse_args()

    result_data: dict[str, object]
    try:
        disks = list_removable_disks()
        disk = next((item for item in disks if item.number == args.disk), None)
        if disk is None:
            raise BackendError(f"Disco USB {args.disk} nao encontrado.")
        plan_kwargs = {
            "filesystem": Filesystem(args.filesystem) if args.filesystem else None,
            "partition_style": args.partition_style,
            "label": args.label,
        }
        if args.allocation_unit_size is not None:
            plan_kwargs["allocation_unit_size"] = args.allocation_unit_size
        plan = create_format_plan(FormatMode(args.mode), disk.size_bytes, **plan_kwargs)
        result = prepare_disk(
            disk,
            FormatMode(args.mode),
            fat32_helper=args.fat32_helper,
            dry_run=False,
            log_path=args.log,
            plan_override=plan,
        )
        result_data = {
            "ok": True,
            "drive_letter": result.drive_letter,
            "message": result.validation.message,
        }
    except Exception as exc:
        result_data = {
            "ok": False,
            "message": str(exc),
        }

    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result_data, ensure_ascii=False), encoding="utf-8")
    return 0 if result_data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
