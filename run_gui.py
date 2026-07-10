from pathlib import Path
import sys
import traceback

from usbdj.elevated_worker import main as worker_main
from usbdj.gui import main


def _log(message: str) -> None:
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "gui-launch.log").open("a", encoding="utf-8") as file:
        file.write(message.rstrip() + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.argv.pop(1)
        raise SystemExit(worker_main())

    _log(f"starting gui exe={sys.executable} cwd={Path.cwd()}")
    try:
        main()
    except Exception:
        _log("gui crashed")
        _log(traceback.format_exc())
        raise
    finally:
        _log("gui exited")
