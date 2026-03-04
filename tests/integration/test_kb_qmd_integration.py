from __future__ import annotations

import importlib

import pytest
from typer.testing import CliRunner

RUNNER = CliRunner()


def _write_note(env, relative_path: str, content: str) -> None:
    target = env.vault_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _invoke_kb(command: list[str]) -> str:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, command, prog_name="aurora")
    assert result.exit_code == 0
    return result.output.lower()


@pytest.mark.integration
def test_real_qmd_lifecycle_ingest_update_delete_rebuild(qmd_integration_env) -> None:
    env = qmd_integration_env
    _write_note(env, "notes/alpha.md", "alpha-v1 body")
    _write_note(env, "notes/beta.md", "beta-v1 body")

    ingest_output = _invoke_kb(["kb", "ingest", str(env.vault_path)])
    assert "operacao: ingest" in ingest_output
    assert "totais:" in ingest_output
    assert "alpha-v1 body" not in ingest_output
    assert "beta-v1 body" not in ingest_output
    assert env.collection_entries() == ("notes/alpha.md", "notes/beta.md")

    _write_note(env, "notes/alpha.md", "alpha-v2 body")
    _write_note(env, "notes/gamma.md", "gamma-v1 body")
    (env.vault_path / "notes" / "beta.md").unlink()

    update_output = _invoke_kb(["kb", "update"])
    assert "operacao: update" in update_output
    assert "totais:" in update_output
    assert "alpha-v2 body" not in update_output
    assert "gamma-v1 body" not in update_output
    assert env.collection_entries() == ("notes/alpha.md", "notes/gamma.md")
    assert env.collection_get("notes/alpha.md").returncode == 0
    assert env.collection_get("notes/gamma.md").returncode == 0
    assert env.collection_get("notes/beta.md").returncode != 0

    delete_output = _invoke_kb(["kb", "delete"])
    assert "operacao: delete" in delete_output
    assert "index-only" in delete_output
    assert env.collection_entries() == ()

    _write_note(env, "notes/rebuild.md", "rebuild-v1 body")
    rebuild_output = _invoke_kb(["kb", "rebuild"])
    assert "operacao: rebuild" in rebuild_output
    assert "totais:" in rebuild_output
    assert "rebuild-v1 body" not in rebuild_output
    assert env.collection_entries() == ("notes/rebuild.md",)
    assert env.collection_get("notes/rebuild.md").returncode == 0
