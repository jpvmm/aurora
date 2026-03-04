from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol

from aurora.kb.contracts import KBPreparedNote
from aurora.kb.qmd_adapter import QMDBackendDiagnostic, QMDBackendResponse
from aurora.runtime.paths import get_kb_qmd_corpus_path
from aurora.runtime.settings import RuntimeSettings, load_settings


class CommandResult(Protocol):
    returncode: int
    stderr: str | None


CommandRunner = Callable[[tuple[str, ...]], CommandResult]
SettingsLoader = Callable[[], RuntimeSettings]


def _default_command_runner(argv: tuple[str, ...]) -> CommandResult:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


class QMDCliBackend:
    """Concrete QMD CLI transport for deterministic KB lifecycle mutations."""

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        settings_loader: SettingsLoader = load_settings,
    ) -> None:
        settings = settings_loader()
        self.index_name = settings.kb_qmd_index_name
        self.collection_name = settings.kb_qmd_collection_name
        self.corpus_dir = get_kb_qmd_corpus_path(self.collection_name)
        self._run_command = command_runner or _default_command_runner

    def apply(self, notes: tuple[KBPreparedNote, ...] | tuple[str, ...]) -> QMDBackendResponse:
        prepared_notes = self._normalize_prepared_notes(notes)
        if prepared_notes is None:
            return self._response(
                "state_mismatch",
                "Caminho relativo invalido no lote de ingest/update. Execute `aurora kb rebuild`.",
                path="<scope>",
            )
        write_error = self._write_notes(prepared_notes, replace_all=False)
        if write_error is not None:
            return write_error
        bootstrap_error = self._bootstrap_collection()
        if bootstrap_error is not None:
            return bootstrap_error
        return self._run_update()

    def remove(self, paths: tuple[str, ...]) -> QMDBackendResponse:
        for relative_path in paths:
            target = self._resolve_corpus_path(relative_path)
            if target is None:
                return self._response(
                    "state_mismatch",
                    "Caminho relativo invalido no lote de remocao. Execute `aurora kb rebuild`.",
                    path="<scope>",
                )
            if target.exists():
                target.unlink()

        bootstrap_error = self._bootstrap_collection()
        if bootstrap_error is not None:
            return bootstrap_error
        return self._run_update()

    def rebuild(self, notes: tuple[KBPreparedNote, ...] | tuple[str, ...]) -> QMDBackendResponse:
        prepared_notes = self._normalize_prepared_notes(notes)
        if prepared_notes is None:
            return self._response(
                "state_mismatch",
                "Caminho relativo invalido no lote de rebuild. Execute `aurora kb rebuild`.",
                path="<scope>",
            )
        write_error = self._write_notes(prepared_notes, replace_all=True)
        if write_error is not None:
            return write_error
        bootstrap_error = self._bootstrap_collection()
        if bootstrap_error is not None:
            return bootstrap_error
        return self._run_update()

    def _bootstrap_collection(self) -> QMDBackendResponse | None:
        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        command = (
            "qmd",
            "--index",
            self.index_name,
            "collection",
            "add",
            str(self.corpus_dir),
            "--name",
            self.collection_name,
            "--mask",
            "**/*.md",
        )
        try:
            result = self._run_command(command)
        except FileNotFoundError:
            return self._response(
                "backend_unavailable",
                "Comando `qmd` nao encontrado. Instale o QMD e valide com `qmd --help`.",
            )

        if result.returncode == 0:
            return None

        stderr = (result.stderr or "").lower()
        if "already exists" in stderr:
            return None

        return self._response(
            "backend_bootstrap_failed",
            (
                "Falha ao preparar colecao QMD gerenciada. "
                f"Tente `qmd --index {self.index_name} collection list` e depois `aurora kb rebuild`."
            ),
        )

    def _run_update(self) -> QMDBackendResponse:
        command = ("qmd", "--index", self.index_name, "update")
        try:
            result = self._run_command(command)
        except FileNotFoundError:
            return self._response(
                "backend_unavailable",
                "Comando `qmd` nao encontrado. Instale o QMD e valide com `qmd --help`.",
            )

        if result.returncode == 0:
            return QMDBackendResponse(ok=True, diagnostics=())

        return self._response(
            "backend_update_failed",
            (
                "Falha ao atualizar indice QMD. "
                f"Execute `qmd --index {self.index_name} update` e depois `aurora kb rebuild`."
            ),
        )

    def _response(self, category: str, recovery_hint: str, *, path: str = "<index>") -> QMDBackendResponse:
        return QMDBackendResponse(
            ok=False,
            diagnostics=(
                QMDBackendDiagnostic(
                    path=path,
                    category=category,
                    recovery_hint=recovery_hint,
                ),
            ),
        )

    def _resolve_corpus_path(self, relative_path: str) -> Path | None:
        normalized = relative_path.replace("\\", "/").strip()
        pure = PurePosixPath(normalized)
        if not normalized or pure.is_absolute() or ".." in pure.parts:
            return None
        return self.corpus_dir.joinpath(*pure.parts)

    def _normalize_prepared_notes(
        self,
        notes: tuple[KBPreparedNote, ...] | tuple[str, ...],
    ) -> tuple[KBPreparedNote, ...] | None:
        normalized: list[KBPreparedNote] = []
        for item in notes:
            if isinstance(item, KBPreparedNote):
                normalized.append(item)
                continue
            if not isinstance(item, str):
                return None
            try:
                normalized.append(
                    KBPreparedNote(
                        relative_path=item,
                        cleaned_text="",
                        cleaned_size=0,
                        templater_tags_removed=0,
                    )
                )
            except ValueError:
                return None
        return tuple(normalized)

    def _write_notes(
        self,
        notes: tuple[KBPreparedNote, ...],
        *,
        replace_all: bool,
    ) -> QMDBackendResponse | None:
        for note in notes:
            expected_size = len(note.cleaned_text.encode("utf-8"))
            if expected_size != note.cleaned_size:
                return self._response(
                    "state_mismatch",
                    (
                        "Metadata de conteudo preparada divergente (cleaned_size). "
                        "Execute `aurora kb rebuild` para reconciliar o estado."
                    ),
                    path=note.relative_path,
                )

        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        if replace_all:
            self._clear_corpus()

        for note in notes:
            target = self._resolve_corpus_path(note.relative_path)
            if target is None:
                return self._response(
                    "state_mismatch",
                    "Caminho relativo invalido no payload de backend. Execute `aurora kb rebuild`.",
                    path="<scope>",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(note.cleaned_text, encoding="utf-8")

        return None

    def _clear_corpus(self) -> None:
        if not self.corpus_dir.exists():
            return
        for path in sorted(self.corpus_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                continue
            if path.is_dir():
                path.rmdir()


__all__ = ["QMDCliBackend"]
