from __future__ import annotations

from dataclasses import dataclass


HERMES_REPO_URL = "https://github.com/nousresearch/hermes-agent"
DEFAULT_EXTERNAL_PATH = "external_repos/hermes-agent"


@dataclass(frozen=True)
class RepoFetchPlan:
    repo_url: str = HERMES_REPO_URL
    target_path: str = DEFAULT_EXTERNAL_PATH
    command: str = f"git clone --depth 1 {HERMES_REPO_URL} {DEFAULT_EXTERNAL_PATH}"
    execute_code_after_clone: bool = False
    stage_external_repo: bool = False
    preserve_license_notice: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_url": self.repo_url,
            "target_path": self.target_path,
            "command": self.command,
            "execute_code_after_clone": self.execute_code_after_clone,
            "stage_external_repo": self.stage_external_repo,
            "preserve_license_notice": self.preserve_license_notice,
        }
