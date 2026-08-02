from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_EMERGENCY_STOP_PATH = Path("runtime/agentic_micro_os/EMERGENCY_STOP")


@dataclass(frozen=True)
class EmergencyStop:
    path: Path = DEFAULT_EMERGENCY_STOP_PATH

    def is_triggered(self) -> bool:
        return self.path.exists()

    def trigger(self, reason: str = "operator emergency stop") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(reason, encoding="utf-8")

    def status(self) -> dict[str, str | bool]:
        return {
            "emergency_stop_path": str(self.path),
            "emergency_stop_triggered": self.is_triggered(),
        }
