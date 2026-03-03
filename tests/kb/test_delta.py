from __future__ import annotations

from aurora.kb.delta import KBDelta, KBScanFingerprint, classify_kb_delta
from aurora.kb.manifest import KBManifest, KBManifestNoteRecord


def _note(*, size: int, mtime_ns: int, sha256: str | None = None) -> KBManifestNoteRecord:
    return KBManifestNoteRecord(
        size=size,
        mtime_ns=mtime_ns,
        sha256=sha256,
        indexed_at="2026-03-03T23:00:00Z",
        cleaned_size=size,
        templater_tags_removed=0,
    )


def test_classify_delta_detects_added_updated_removed_and_unchanged() -> None:
    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "notes/keep.md": _note(size=10, mtime_ns=100),
            "notes/change.md": _note(size=11, mtime_ns=101),
            "notes/remove.md": _note(size=12, mtime_ns=102),
        },
    )

    delta = classify_kb_delta(
        scan_notes=(
            KBScanFingerprint(path="notes/keep.md", size=10, mtime_ns=100),
            KBScanFingerprint(path="notes/change.md", size=11, mtime_ns=999),
            KBScanFingerprint(path="notes/add.md", size=9, mtime_ns=500),
        ),
        manifest=manifest,
    )

    assert delta == KBDelta(
        added=("notes/add.md",),
        updated=("notes/change.md",),
        removed=("notes/remove.md",),
        unchanged=("notes/keep.md",),
        divergence_reasons=(),
    )


def test_strict_hash_mode_refines_metadata_changes() -> None:
    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "notes/hash.md": _note(size=10, mtime_ns=100, sha256="same-hash"),
        },
    )
    scan = (
        KBScanFingerprint(
            path="notes/hash.md",
            size=99,
            mtime_ns=999,
            sha256="same-hash",
        ),
    )

    regular = classify_kb_delta(scan_notes=scan, manifest=manifest, strict_hash=False)
    strict = classify_kb_delta(scan_notes=scan, manifest=manifest, strict_hash=True)

    assert regular.updated == ("notes/hash.md",)
    assert strict.updated == ()
    assert strict.unchanged == ("notes/hash.md",)


def test_scope_filtering_applies_to_update_comparison() -> None:
    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "notes/in-scope.md": _note(size=10, mtime_ns=100),
            "notes/out-of-scope.md": _note(size=10, mtime_ns=100),
        },
    )

    delta = classify_kb_delta(
        scan_notes=(
            KBScanFingerprint(path="notes/in-scope.md", size=10, mtime_ns=100),
            KBScanFingerprint(path="notes/new-out.md", size=10, mtime_ns=100),
        ),
        manifest=manifest,
        scoped_paths=("notes/in-scope.md",),
    )

    assert delta.added == ()
    assert delta.updated == ()
    assert delta.removed == ()
    assert delta.unchanged == ("notes/in-scope.md",)


def test_divergence_flags_conflicting_normalized_scan_paths() -> None:
    manifest = KBManifest(vault_root="/vault", notes={})

    delta = classify_kb_delta(
        scan_notes=(
            KBScanFingerprint(path="notes/a.md", size=1, mtime_ns=1),
            KBScanFingerprint(path="notes/./a.md", size=2, mtime_ns=2),
        ),
        manifest=manifest,
    )

    assert delta.divergence_detected is True
    assert any("notes/a.md" in reason for reason in delta.divergence_reasons)


def test_divergence_flags_invalid_manifest_paths() -> None:
    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "../escape.md": _note(size=1, mtime_ns=1),
            "notes/ok.md": _note(size=1, mtime_ns=1),
        },
    )

    delta = classify_kb_delta(
        scan_notes=(KBScanFingerprint(path="notes/ok.md", size=1, mtime_ns=1),),
        manifest=manifest,
    )

    assert delta.divergence_detected is True
    assert any("../escape.md" in reason for reason in delta.divergence_reasons)
