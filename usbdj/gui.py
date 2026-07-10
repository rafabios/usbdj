from __future__ import annotations

import tkinter as tk
import json
import sys
from pathlib import Path
from datetime import datetime
from tkinter import messagebox, ttk

from usbdj.elevation import run_worker_with_windows_permission
from usbdj.models import DiskInfo, Filesystem, FormatMode
from usbdj.planner import create_format_plan
from usbdj.presets import SUPPORTED_HINTS
from usbdj.windows_backend import (
    BackendError,
    is_windows_admin,
    list_removable_disks,
    prepare_disk,
)


class UsbDjApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("USB DJ Formatter")
        self._set_app_icon()
        self.geometry("640x620")
        self.resizable(False, False)
        self.lift()
        self.attributes("-topmost", True)
        self.after(800, lambda: self.attributes("-topmost", False))
        self.disks: list[DiskInfo] = []
        self.mode = tk.StringVar(value=FormatMode.LEGACY.value)
        self.disk_var = tk.StringVar()
        self.status = tk.StringVar(value="Conecte um pendrive e clique em Atualizar.")
        self.advanced_visible = False
        self.advanced_filesystem = tk.StringVar(value="AUTO")
        self.advanced_partition_style = tk.StringVar(value="MBR")
        self.advanced_cluster = tk.StringVar(value="AUTO")
        self.advanced_label = tk.StringVar(value="CDJ_USB")
        self.current_log_path: Path | None = None
        self.log_text: tk.Text | None = None

        self._build()
        self.refresh_disks()

    def _set_app_icon(self) -> None:
        icon_path = resource_path("assets/dj.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="Preparar pendrive para CDJ/XDJ", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")

        device_row = ttk.Frame(outer)
        device_row.pack(fill="x", pady=(18, 10))
        ttk.Label(device_row, text="Pendrive").pack(anchor="w")
        combo = ttk.Combobox(device_row, textvariable=self.disk_var, state="readonly", width=70)
        combo.pack(side="left", fill="x", expand=True, pady=(4, 0))
        ttk.Button(device_row, text="Atualizar", command=self.refresh_disks).pack(side="left", padx=(8, 0), pady=(4, 0))

        modes = ttk.LabelFrame(outer, text="Compatibilidade")
        modes.pack(fill="x", pady=10)
        ttk.Radiobutton(
            modes,
            text="CDJs antigos / modo legado (FAT32)",
            variable=self.mode,
            value=FormatMode.LEGACY.value,
            command=self.update_mode_hint,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Radiobutton(
            modes,
            text="CDJs novos / modo atual (exFAT)",
            variable=self.mode,
            value=FormatMode.MODERN.value,
            command=self.update_mode_hint,
        ).pack(anchor="w", padx=12, pady=(4, 10))

        self.hint = ttk.Label(outer, text="", wraplength=560)
        self.hint.pack(anchor="w", pady=(4, 12))

        self.advanced_button = ttk.Button(outer, text="Avancado", command=self.toggle_advanced)
        self.advanced_button.pack(anchor="w")
        self.advanced_frame = ttk.LabelFrame(outer, text="Opcoes avancadas")
        self._build_advanced_panel(self.advanced_frame)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(18, 8))
        ttk.Button(actions, text="Simular", command=self.simulate).pack(side="left")
        self.prepare_button = ttk.Button(actions, text="Preparar pendrive", command=self.prepare_selected_disk)
        self.prepare_button.pack(side="right")

        status = ttk.Label(outer, textvariable=self.status, wraplength=560)
        status.pack(anchor="w", pady=(18, 0))

        log_frame = ttk.LabelFrame(outer, text="Log")
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.log_text = tk.Text(log_frame, height=6, wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        warning = ttk.Label(
            outer,
            text="Atencao: preparar o pendrive apaga todos os dados do dispositivo selecionado.",
            foreground="#a33",
            wraplength=560,
        )
        warning.pack(anchor="w", side="bottom")

        self.combo = combo
        self.update_mode_hint()
        self.update_permission_hint()

    def _build_advanced_panel(self, parent: ttk.LabelFrame) -> None:
        row1 = ttk.Frame(parent)
        row1.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(row1, text="Formato").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            row1,
            textvariable=self.advanced_filesystem,
            values=["AUTO", Filesystem.FAT32.value, Filesystem.EXFAT.value],
            state="readonly",
            width=12,
        ).grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Label(row1, text="Particao").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            row1,
            textvariable=self.advanced_partition_style,
            values=["MBR", "GPT"],
            state="readonly",
            width=10,
        ).grid(row=1, column=1, sticky="w", padx=(0, 12))
        ttk.Label(row1, text="Cluster").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            row1,
            textvariable=self.advanced_cluster,
            values=["AUTO", "16 KB", "32 KB", "64 KB", "128 KB"],
            state="readonly",
            width=10,
        ).grid(row=1, column=2, sticky="w")

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", padx=12, pady=(4, 10))
        ttk.Label(row2, text="Nome do pendrive").pack(anchor="w")
        ttk.Entry(row2, textvariable=self.advanced_label, width=24).pack(anchor="w")

    def refresh_disks(self) -> None:
        try:
            self.disks = list_removable_disks()
        except BackendError as exc:
            self.disks = []
            messagebox.showerror("Erro ao listar discos", str(exc))

        values = [
            f"Disco {d.number} - {d.friendly_name} - {d.size_gb:.1f} GB"
            for d in self.disks
        ]
        self.combo["values"] = values
        if values:
            self.disk_var.set(values[0])
            self.status.set("Pendrive detectado. Use Simular para revisar o plano.")
        else:
            self.disk_var.set("")
            self.status.set("Nenhum pendrive USB removivel encontrado.")

    def update_permission_hint(self) -> None:
        if is_windows_admin():
            return
        self.status.set("A permissao do Windows sera pedida ao preparar o pendrive.")

    def update_mode_hint(self) -> None:
        mode = FormatMode(self.mode.get())
        devices = ", ".join(SUPPORTED_HINTS[mode])
        self.hint.configure(text=f"Indicado para: {devices}.")

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.pack(fill="x", pady=(8, 8), after=self.advanced_button)
        else:
            self.advanced_frame.pack_forget()

    def selected_disk(self) -> DiskInfo | None:
        selected = self.disk_var.get()
        for disk in self.disks:
            if selected.startswith(f"Disco {disk.number} "):
                return disk
        return None

    def simulate(self) -> None:
        disk = self.selected_disk()
        if not disk:
            messagebox.showinfo("Pendrive", "Selecione um pendrive primeiro.")
            return
        plan = create_format_plan(
            FormatMode(self.mode.get()),
            disk.size_bytes,
            **self.advanced_plan_kwargs(),
        )
        cluster = plan.allocation_unit_size or "automatico"
        message = (
            f"Disco: {disk.number} - {disk.friendly_name}\n"
            f"Tamanho: {disk.size_gb:.1f} GB\n"
            f"Formato: {plan.filesystem.value}\n"
            f"Particao: {plan.partition_style}\n"
            f"Cluster: {cluster}\n"
            f"Backend: {plan.engine.value}"
        )
        if plan.warning:
            message += f"\n\n{plan.warning}"
        messagebox.showinfo("Plano de formatacao", message)

    def prepare_selected_disk(self) -> None:
        disk = self.selected_disk()
        if not disk:
            messagebox.showinfo("Pendrive", "Selecione um pendrive primeiro.")
            return

        mode = FormatMode(self.mode.get())
        plan = create_format_plan(mode, disk.size_bytes, **self.advanced_plan_kwargs())
        cluster = plan.allocation_unit_size or "automatico"
        warning = (
            f"O disco {disk.number} ({disk.friendly_name}, {disk.size_gb:.1f} GB) sera apagado.\n\n"
            f"Formato: {plan.filesystem.value}\n"
            f"Particao: {plan.partition_style}\n"
            f"Cluster: {cluster}\n"
            f"Backend: {plan.engine.value}\n\n"
            "Digite FORMATAR para confirmar."
        )
        confirmation = ConfirmDialog(self, warning).value
        if confirmation != "FORMATAR":
            self.status.set("Operacao cancelada.")
            return

        log_path = self._new_log_path()
        self.current_log_path = log_path
        self._set_log_text("Aguardando inicio da formatacao...\n")
        self.prepare_button.configure(state="disabled")
        self.status.set("Preparando pendrive. Nao remova o dispositivo.")
        self.update_idletasks()
        if not is_windows_admin():
            result_path = self._new_result_path()
            worker_args = [
                "--disk",
                str(disk.number),
                "--mode",
                mode.value,
                "--log",
                str(log_path),
                "--result",
                str(result_path),
            ]
            worker_args.extend(self.advanced_worker_args())
            started = run_worker_with_windows_permission(
                worker_args
            )
            if not started:
                self.prepare_button.configure(state="normal")
                self.status.set("Permissao do Windows cancelada.")
                return
            self.status.set("Aguardando permissao do Windows e preparo do pendrive.")
            self._watch_log(log_path)
            self._wait_for_worker_result(result_path, log_path)
            return

        try:
            self._watch_log(log_path)
            result = prepare_disk(
                disk,
                mode,
                dry_run=False,
                log_path=log_path,
                plan_override=plan,
            )
        except BackendError as exc:
            self.status.set("Falha ao preparar pendrive.")
            messagebox.showerror("Erro", f"{exc}\n\nLog: {log_path}")
        except Exception as exc:
            self.status.set("Falha inesperada ao preparar pendrive.")
            messagebox.showerror("Erro inesperado", f"{exc}\n\nLog: {log_path}")
        else:
            self.status.set(f"Pendrive pronto em {result.drive_letter}:.")
            messagebox.showinfo(
                "Pendrive pronto",
                f"Pendrive preparado e validado em {result.drive_letter}:.\n\nLog: {log_path}",
            )
            self.refresh_disks()
        finally:
            self.prepare_button.configure(state="normal")

    def _new_log_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path.cwd() / "logs" / f"usbdj-{stamp}.log"

    def _new_result_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path.cwd() / "logs" / f"usbdj-result-{stamp}.json"

    def advanced_plan_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if not self.advanced_visible:
            return kwargs
        filesystem = self.advanced_filesystem.get()
        if filesystem != "AUTO":
            kwargs["filesystem"] = Filesystem(filesystem)
        kwargs["partition_style"] = self.advanced_partition_style.get()
        cluster = self._cluster_value()
        if cluster is not None:
            kwargs["allocation_unit_size"] = cluster
        label = self.advanced_label.get().strip()
        if label:
            kwargs["label"] = label[:32]
        return kwargs

    def advanced_worker_args(self) -> list[str]:
        if not self.advanced_visible:
            return []
        args: list[str] = [
            "--partition-style",
            self.advanced_partition_style.get(),
        ]
        filesystem = self.advanced_filesystem.get()
        if filesystem != "AUTO":
            args.extend(["--filesystem", filesystem])
        cluster = self._cluster_value()
        if cluster is not None:
            args.extend(["--allocation-unit-size", str(cluster)])
        label = self.advanced_label.get().strip()
        if label:
            args.extend(["--label", label[:32]])
        return args

    def _cluster_value(self) -> int | None:
        value = self.advanced_cluster.get()
        if value == "AUTO":
            return None
        return int(value.split()[0]) * 1024

    def _wait_for_worker_result(self, result_path: Path, log_path: Path, attempts: int = 0) -> None:
        self._refresh_log(log_path)
        if result_path.exists():
            self.prepare_button.configure(state="normal")
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.status.set("Nao foi possivel ler o resultado.")
                messagebox.showerror("Erro", f"{exc}\n\nLog: {log_path}")
                return
            if data.get("ok"):
                drive_letter = data.get("drive_letter", "")
                self.status.set(f"Pendrive pronto em {drive_letter}:.")
                messagebox.showinfo(
                    "Pendrive pronto",
                    f"Pendrive preparado e validado em {drive_letter}:.\n\nLog: {log_path}",
                )
                self.refresh_disks()
            else:
                self.status.set("Falha ao preparar pendrive.")
                messagebox.showerror("Erro", f"{data.get('message')}\n\nLog: {log_path}")
            return

        if attempts >= 600:
            self.prepare_button.configure(state="normal")
            self.status.set("Tempo limite aguardando preparo do pendrive.")
            messagebox.showerror("Tempo limite", f"Nao recebi resultado do processo elevado.\n\nLog: {log_path}")
            return

        self.after(500, lambda: self._wait_for_worker_result(result_path, log_path, attempts + 1))

    def _watch_log(self, log_path: Path) -> None:
        self.current_log_path = log_path
        self._refresh_log(log_path)

    def _refresh_log(self, log_path: Path) -> None:
        if self.log_text is None:
            return
        if not log_path.exists():
            return
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self._set_log_text(text)

    def _set_log_text(self, text: str) -> None:
        if self.log_text is None:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


class ConfirmDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, message: str) -> None:
        super().__init__(parent)
        self.title("Confirmar formatacao")
        self.resizable(False, False)
        self.value = ""
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, wraplength=460).pack(anchor="w")
        self.entry = ttk.Entry(frame, width=28)
        self.entry.pack(anchor="w", pady=(14, 10))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancelar", command=self.cancel).pack(side="left")
        ttk.Button(buttons, text="Confirmar", command=self.confirm).pack(side="right")

        self.entry.focus_set()
        self.bind("<Return>", lambda _event: self.confirm())
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        parent.wait_window(self)

    def confirm(self) -> None:
        self.value = self.entry.get().strip()
        self.destroy()

    def cancel(self) -> None:
        self.value = ""
        self.destroy()


def main() -> None:
    app = UsbDjApp()
    app.mainloop()


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return base / relative_path


if __name__ == "__main__":
    main()
