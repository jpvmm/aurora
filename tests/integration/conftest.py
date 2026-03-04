from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from aurora.runtime.settings import RuntimeSettings, save_settings


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\].*?\x07")


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value)


@dataclass(frozen=True)
class QMDIntegrationEnv:
    config_dir: Path
    vault_path: Path
    index_name: str
    collection_name: str

    def run_qmd(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ("qmd", "--index", self.index_name, *args),
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            cleaned_out = _strip_ansi(result.stdout)
            cleaned_err = _strip_ansi(result.stderr)
            raise AssertionError(
                "QMD command failed: "
                f"qmd --index {self.index_name} {' '.join(args)}\n"
                f"stdout:\n{cleaned_out}\n"
                f"stderr:\n{cleaned_err}"
            )
        return result

    def collection_entries(self) -> tuple[str, ...]:
        result = self.run_qmd("ls", self.collection_name, check=False)
        output = _strip_ansi(f"{result.stdout}\n{result.stderr}")
        collection_prefix = f"qmd://{self.collection_name}/"
        entries: list[str] = []
        for line in output.splitlines():
            index = line.find(collection_prefix)
            if index == -1:
                continue
            relative = line[index + len(collection_prefix) :].strip()
            if relative:
                entries.append(relative)
        return tuple(sorted(entries))

    def collection_get(self, relative_path: str) -> subprocess.CompletedProcess[str]:
        return self.run_qmd("get", f"{self.collection_name}/{relative_path}", check=False)


@pytest.fixture
def qmd_integration_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> QMDIntegrationEnv:
    if shutil.which("qmd") is None:
        pytest.skip("qmd CLI not available for integration test run")

    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    vault_path.mkdir(parents=True, exist_ok=True)
    index_name = f"aurora-kb-int-{uuid4().hex[:12]}"
    collection_name = f"aurora-kb-coll-{uuid4().hex[:12]}"

    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_include=("notes/*.md",),
            kb_exclude=(),
            kb_default_excludes=(),
            kb_qmd_index_name=index_name,
            kb_qmd_collection_name=collection_name,
        )
    )

    env = QMDIntegrationEnv(
        config_dir=config_dir,
        vault_path=vault_path,
        index_name=index_name,
        collection_name=collection_name,
    )
    yield env

    env.run_qmd("collection", "remove", collection_name, check=False)
