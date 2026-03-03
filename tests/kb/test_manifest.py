from __future__ import annotations

import json

import pytest

from aurora.kb.manifest import (
    KBManifest,
    KBManifestNoteRecord,
    KBManifestStateError,
    load_kb_manifest,
    save_kb_manifest,
)
from aurora.runtime.paths import get_kb_manifest_path


def test_load_manifest_returns_none_when_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    assert load_kb_manifest() is None


def test_save_and_load_manifest_round_trip_is_deterministic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "zeta/note.md": KBManifestNoteRecord(
                size=42,
                mtime_ns=1700000000000000000,
                sha256=None,
                indexed_at="2026-03-03T22:55:00Z",
                cleaned_size=40,
                templater_tags_removed=1,
            ),
            "alpha/note.md": KBManifestNoteRecord(
                size=12,
                mtime_ns=1700000000000000001,
                sha256="abc123",
                indexed_at="2026-03-03T22:56:00Z",
                cleaned_size=12,
                templater_tags_removed=0,
            ),
        },
    )

    saved = save_kb_manifest(manifest)
    loaded = load_kb_manifest()

    assert loaded == saved

    payload = json.loads(get_kb_manifest_path().read_text(encoding="utf-8"))
    assert list(payload.keys()) == sorted(payload.keys())
    assert list(payload["notes"].keys()) == ["alpha/note.md", "zeta/note.md"]
    assert payload["notes"]["alpha/note.md"]["cleaned_size"] == 12


def test_load_manifest_rejects_invalid_json_with_rebuild_guidance(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    manifest_path = get_kb_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not-json}", encoding="utf-8")

    with pytest.raises(KBManifestStateError) as error:
        load_kb_manifest()

    message = str(error.value)
    assert "aurora kb rebuild" in message
    assert str(manifest_path) in message


def test_load_manifest_rejects_incompatible_schema_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    manifest_path = get_kb_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "vault_root": "/vault",
                "notes": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(KBManifestStateError) as error:
        load_kb_manifest()

    assert "schema_version" in str(error.value)
    assert "aurora kb rebuild" in str(error.value)


def test_manifest_validation_rejects_invalid_note_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    manifest_path = get_kb_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "vault_root": "/vault",
                "notes": {
                    "../escape.md": {
                        "size": 1,
                        "mtime_ns": 1,
                        "sha256": None,
                        "indexed_at": "2026-03-03T22:57:00Z",
                        "cleaned_size": 1,
                        "templater_tags_removed": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(KBManifestStateError) as error:
        load_kb_manifest()

    assert "vault-relative" in str(error.value)
