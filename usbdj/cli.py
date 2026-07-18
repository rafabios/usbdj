from __future__ import annotations

import argparse
from pathlib import Path

from usbdj.models import FormatMode
from usbdj.planner import create_format_plan
from usbdj.windows_backend import (
    BackendError,
    list_removable_disks,
    prepare_disk,
)


def _format_gb(size_bytes: int) -> str:
    return f"{size_bytes / 1_000_000_000:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(prog="usbdj")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lista pendrives USB detectados")

    plan_cmd = sub.add_parser("plan", help="Mostra qual backend sera usado")
    plan_cmd.add_argument("--mode", choices=[m.value for m in FormatMode], required=True)
    plan_cmd.add_argument("--size-gb", type=float, required=True)

    format_cmd = sub.add_parser("format", help="Prepara um disco USB selecionado")
    format_cmd.add_argument("--disk", type=int, required=True)
    format_cmd.add_argument("--mode", choices=[m.value for m in FormatMode], required=True)
    format_cmd.add_argument("--execute", action="store_true")
    format_cmd.add_argument("--confirm", default="")
    format_cmd.add_argument("--log", type=Path, default=Path("logs/usbdj-cli.log"))

    args = parser.parse_args()

    if args.command == "list":
        disks = list_removable_disks()
        if not disks:
            print("Nenhum disco USB removivel encontrado.")
            return 0
        for disk in disks:
            print(
                f"Disco {disk.number}: {disk.friendly_name} - "
                f"{_format_gb(disk.size_bytes)} - {disk.bus_type}"
            )
        return 0

    if args.command == "plan":
        plan = create_format_plan(
            FormatMode(args.mode),
            int(args.size_gb * 1_000_000_000),
        )
        print(f"Modo: {plan.mode.value}")
        print(f"Filesystem: {plan.filesystem.value}")
        print(f"Engine: {plan.engine.value}")
        print(f"Particao: {plan.partition_style}")
        print(f"Cluster: {plan.allocation_unit_size or 'automatico'}")
        if plan.warning:
            print(f"Aviso: {plan.warning}")
        return 0

    if args.command == "format":
        disks = list_removable_disks()
        disk = next((item for item in disks if item.number == args.disk), None)
        if not disk:
            print(f"Disco USB {args.disk} nao encontrado.")
            return 2

        plan = create_format_plan(FormatMode(args.mode), disk.size_bytes)
        print(f"Disco: {disk.number} - {disk.friendly_name} - {_format_gb(disk.size_bytes)}")
        print(f"Formato: {plan.filesystem.value}")
        print(f"Engine: {plan.engine.value}")
        if not args.execute:
            print("Simulacao apenas. Adicione --execute --confirm FORMATAR para executar.")
            return 0
        if args.confirm != "FORMATAR":
            print("Confirmacao invalida. Use --confirm FORMATAR.")
            return 2
        try:
            result = prepare_disk(
                disk,
                FormatMode(args.mode),
                dry_run=False,
                log_path=args.log,
            )
        except BackendError as exc:
            print(f"Erro: {exc}")
            print(f"Log: {args.log}")
            return 1
        print(f"Pendrive pronto em {result.drive_letter}:")
        print(result.validation.message)
        print(f"Log: {args.log}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
