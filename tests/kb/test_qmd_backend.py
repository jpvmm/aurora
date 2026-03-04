from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aurora.kb.contracts import KBPreparedNote
from aurora.kb.qmd_backend import QMDCliBackend
from aurora.runtime.settings import RuntimeSettings, save_settings


@dataclass(frozen=True)
class FakeCompletedProcess:
    returncode: int
    stderr: str = ""


class StubRunner:
    def __init__(self, *results: FakeCompletedProcess, raise_not_found: bool = False) -> None:
        self._results = list(results)
        self._raise_not_found = raise_not_found
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...]) -> FakeCompletedProcess:
        self.calls.append(argv)
        if self._raise_not_found:
            raise FileNotFoundError("qmd")
        if not self._results:
            return FakeCompletedProcess(returncode=0, stderr="")
        return self._results.pop(0)


def _configure_settings(*, config_dir: Path, vault_path: Path) -> None:
    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_qmd_index_name="aurora-test-index",
            kb_qmd_collection_name="aurora-test-collection",
        )
    )


def _prepared(path: str, text: str, *, cleaned_size: int | None = None) -> KBPreparedNote:
    payload_size = len(text.encode("utf-8")) if cleaned_size is None else cleaned_size
    return KBPreparedNote(
        relative_path=path,
        cleaned_text=text,
        cleaned_size=payload_size,
        templater_tags_removed=0,
    )


def test_apply_bootstraps_collection_then_updates_index(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(
        FakeCompletedProcess(returncode=0),
        FakeCompletedProcess(returncode=0),
    )
    backend = QMDCliBackend(command_runner=runner)

    response = backend.apply((_prepared("notes/a.md", "# nota limpa\n"),))

    assert response.ok is True
    assert response.diagnostics == ()
    assert len(runner.calls) == 2
    assert runner.calls[0][:4] == ("qmd", "--index", "aurora-test-index", "collection")
    assert runner.calls[0][4:6] == ("add", str(backend.corpus_dir))
    assert runner.calls[0][6:] == (
        "--name",
        "aurora-test-collection",
        "--mask",
        "**/*.md",
    )
    assert runner.calls[1] == ("qmd", "--index", "aurora-test-index", "update")
    assert backend.corpus_dir == config_dir / "kb-qmd-corpus" / "aurora-test-collection"
    assert (backend.corpus_dir / "notes" / "a.md").read_text(encoding="utf-8") == "# nota limpa\n"


def test_apply_tolerates_duplicate_collection_bootstrap_error(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(
        FakeCompletedProcess(returncode=1, stderr="Collection already exists"),
        FakeCompletedProcess(returncode=0),
    )
    backend = QMDCliBackend(command_runner=runner)

    response = backend.apply((_prepared("notes/a.md", "texto"),))

    assert response.ok is True
    assert response.diagnostics == ()


def test_remove_deletes_from_managed_corpus_then_updates(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(
        FakeCompletedProcess(returncode=0),
        FakeCompletedProcess(returncode=0),
    )
    backend = QMDCliBackend(command_runner=runner)
    note_path = backend.corpus_dir / "notes" / "obsolete.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("body", encoding="utf-8")

    response = backend.remove(("notes/obsolete.md",))

    assert response.ok is True
    assert response.diagnostics == ()
    assert note_path.exists() is False
    assert runner.calls[-1] == ("qmd", "--index", "aurora-test-index", "update")


def test_rebuild_replaces_managed_corpus_before_update(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(
        FakeCompletedProcess(returncode=0),
        FakeCompletedProcess(returncode=0),
    )
    backend = QMDCliBackend(command_runner=runner)

    stale_file = backend.corpus_dir / "notes" / "stale.md"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    response = backend.rebuild((_prepared("notes/fresh.md", "fresh body"),))

    assert response.ok is True
    assert stale_file.exists() is False
    assert (backend.corpus_dir / "notes" / "fresh.md").read_text(encoding="utf-8") == "fresh body"
    assert runner.calls[-1] == ("qmd", "--index", "aurora-test-index", "update")


def test_maps_missing_qmd_binary_to_typed_diagnostic(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    backend = QMDCliBackend(command_runner=StubRunner(raise_not_found=True))

    response = backend.apply((_prepared("notes/a.md", "A"),))

    assert response.ok is False
    assert response.diagnostics[0].path == "<index>"
    assert response.diagnostics[0].category == "backend_unavailable"
    assert "qmd" in response.diagnostics[0].recovery_hint.lower()


def test_maps_update_failure_without_leaking_note_content(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(
        FakeCompletedProcess(returncode=0),
        FakeCompletedProcess(
            returncode=1,
            stderr="failed while indexing note body: segredo super sensivel",
        ),
    )
    backend = QMDCliBackend(command_runner=runner)

    response = backend.apply((_prepared("notes/a.md", "segredo super sensivel"),))

    assert response.ok is False
    assert response.diagnostics[0].category == "backend_update_failed"
    assert "segredo super sensivel" not in response.diagnostics[0].recovery_hint


def test_rejects_prepared_payload_with_mismatched_cleaned_size(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    runner = StubRunner(FakeCompletedProcess(returncode=0), FakeCompletedProcess(returncode=0))
    backend = QMDCliBackend(command_runner=runner)

    response = backend.apply((_prepared("notes/a.md", "abc", cleaned_size=99),))

    assert response.ok is False
    assert response.diagnostics[0].category == "state_mismatch"
    assert runner.calls == []
