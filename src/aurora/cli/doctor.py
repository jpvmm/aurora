"""aurora doctor — runtime + privacy + full-stack diagnostics.

Per plan 05-02 (D-08, D-09, D-10, D-11, D-12):
- Extends the original runtime/policy checks with:
  QMD binary + version, KB collection + embeddings, memory index, disk space,
  Python version, required packages.
- Each check returns DoctorIssue | None with pt-BR message + recovery commands.
- Doctor NEVER auto-fixes (D-10) — it only reports.
- Supports --json for structured output.
"""
from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

import typer

from aurora.cli.config import mask_sensitive
from aurora.kb.manifest import load_kb_manifest
from aurora.privacy.policy import Phase1PolicyError
from aurora.runtime.errors import RuntimeDiagnosticError
from aurora.runtime.llama_client import validate_runtime
from aurora.runtime.paths import get_settings_path
from aurora.runtime.settings import RuntimeSettings, load_settings


@dataclass(frozen=True)
class DoctorIssue:
    category: str
    message: str
    commands: tuple[str, ...]


doctor_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Diagnostico de runtime local e privacidade.",
)


@doctor_app.callback()
def doctor_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", help="Renderiza resposta estruturada em JSON."
    ),
) -> None:
    """Executa diagnostico do runtime local."""
    if ctx.invoked_subcommand is not None:
        return
    run_doctor_checks(json_output=json_output)


def run_doctor_checks(*, json_output: bool = False) -> None:
    try:
        settings = load_settings()
    except Phase1PolicyError:
        policy_issue = DoctorIssue(
            category="policy_mismatch",
            message="Endpoint configurado viola a politica local-only.",
            commands=(
                "aurora model set --endpoint http://127.0.0.1:8080",
                "aurora config show",
            ),
        )
        if json_output:
            # Emit with a minimal settings snapshot because load_settings failed
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "checks": {
                            "endpoint": "",
                            "model": "",
                            "local_only": True,
                            "telemetry_enabled": False,
                        },
                        "issues": [
                            {
                                "category": policy_issue.category,
                                "message": policy_issue.message,
                                "recovery_commands": list(policy_issue.commands),
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise typer.Exit(code=1)
        _print_issues([policy_issue])
        raise typer.Exit(code=1)

    issues: list[DoctorIssue] = []

    # Existing policy check
    if not settings.local_only:
        issues.append(
            DoctorIssue(
                category="policy_mismatch",
                message="A configuracao atual desativou local-only para esta fase.",
                commands=(
                    "aurora model set --endpoint http://127.0.0.1:8080",
                    "aurora config show",
                ),
            )
        )

    # Existing runtime validation
    try:
        validate_runtime(settings.endpoint_url, settings.model_id)
    except RuntimeDiagnosticError as error:
        issues.append(
            DoctorIssue(
                category=error.category,
                message=error.message,
                commands=error.recovery_commands,
            )
        )

    # New full-stack checks (per D-08)
    _append_if_issue(issues, _check_python_version())
    _append_if_issue(issues, _check_qmd_binary())
    _append_if_issue(issues, _check_qmd_version())
    _append_if_issue(issues, _check_kb_collection(settings))
    _append_if_issue(issues, _check_kb_embeddings(settings))
    _append_if_issue(issues, _check_memory_index(settings))
    _append_if_issue(issues, _check_disk_space())
    issues.extend(_check_required_packages())

    if json_output:
        _print_json_report(settings=settings, issues=issues)
        if issues:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    typer.echo("Diagnostico Aurora")
    typer.echo(f"- endpoint: {mask_sensitive(settings.endpoint_url)}")
    typer.echo(f"- model: {settings.model_id}")
    typer.echo(f"- local-only: {'ativado' if settings.local_only else 'desativado'}")
    typer.echo(f"- telemetria: {'ativada' if settings.telemetry_enabled else 'desativada'}")

    if issues:
        _print_issues(issues)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Runtime local pronto. Nenhum problema encontrado.")


# ---------------------------------------------------------------------------
# Individual check functions (D-08)
# Each returns DoctorIssue | None. Never auto-fix (D-10).
# ---------------------------------------------------------------------------


def _check_python_version() -> DoctorIssue | None:
    if sys.version_info < (3, 13):
        return DoctorIssue(
            category="python_version",
            message=(
                f"Python {sys.version_info.major}.{sys.version_info.minor} detectado. "
                "Aurora requer Python 3.13 ou superior."
            ),
            commands=("Instale Python 3.13+",),
        )
    return None


def _check_qmd_binary() -> DoctorIssue | None:
    if shutil.which("qmd") is None:
        return DoctorIssue(
            category="qmd_missing",
            message="QMD nao encontrado no PATH.",
            commands=("pip install qmd",),
        )
    return None


def _check_qmd_version() -> DoctorIssue | None:
    if shutil.which("qmd") is None:
        # Already reported by _check_qmd_binary
        return None
    try:
        result = subprocess.run(
            ["qmd", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        return DoctorIssue(
            category="qmd_version",
            message=f"QMD instalado mas nao responde a --version: {error}.",
            commands=("pip install --upgrade qmd",),
        )
    if result.returncode != 0:
        return DoctorIssue(
            category="qmd_version",
            message="QMD instalado mas nao responde a --version.",
            commands=("pip install --upgrade qmd",),
        )
    return None


def _check_kb_collection(settings: RuntimeSettings) -> DoctorIssue | None:
    try:
        manifest = load_kb_manifest()
    except Exception as error:
        return DoctorIssue(
            category="kb_manifest_error",
            message=f"Erro ao ler manifesto KB: {error}.",
            commands=("aurora config kb rebuild",),
        )

    if manifest is None:
        return DoctorIssue(
            category="kb_no_manifest",
            message="Manifesto KB nao encontrado. Execute a indexacao inicial.",
            commands=("aurora config kb ingest <caminho-do-vault>",),
        )

    if len(manifest.notes) == 0:
        return DoctorIssue(
            category="kb_collection_empty",
            message="KB sem notas indexadas. Execute a indexacao.",
            commands=("aurora config kb ingest <caminho-do-vault>",),
        )
    return None


def _check_kb_embeddings(settings: RuntimeSettings) -> DoctorIssue | None:
    if shutil.which("qmd") is None:
        return None
    try:
        result = subprocess.run(
            [
                "qmd",
                "--index",
                settings.kb_qmd_index_name,
                "collection",
                "list",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        return DoctorIssue(
            category="kb_embeddings_missing",
            message=f"Erro ao consultar colecoes QMD: {error}.",
            commands=("aurora config kb rebuild",),
        )

    if settings.kb_qmd_collection_name not in (result.stdout or ""):
        return DoctorIssue(
            category="kb_embeddings_missing",
            message=(
                "KB sem embeddings. Colecao QMD "
                f"'{settings.kb_qmd_collection_name}' nao encontrada no indice "
                f"'{settings.kb_qmd_index_name}'."
            ),
            commands=("aurora config kb rebuild",),
        )
    return None


def _check_memory_index(settings: RuntimeSettings) -> DoctorIssue | None:
    try:
        from aurora.memory.store import EpisodicMemoryStore

        memories = EpisodicMemoryStore().list_memories()
    except Exception:
        return None  # memory is optional — graceful degradation

    if not memories:
        return None

    if shutil.which("qmd") is None:
        return None

    try:
        result = subprocess.run(
            [
                "qmd",
                "--index",
                settings.kb_qmd_index_name,
                "collection",
                "list",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if "aurora-memory" not in (result.stdout or ""):
        return DoctorIssue(
            category="memory_index_missing",
            message=(
                f"Memorias encontradas ({len(memories)}) mas colecao QMD "
                "aurora-memory ausente."
            ),
            commands=("aurora config memory clear --yes",),
        )
    return None


def _check_disk_space() -> DoctorIssue | None:
    config_dir = get_settings_path().parent
    try:
        usage = shutil.disk_usage(config_dir)
    except (FileNotFoundError, OSError):
        # Config dir may not exist yet on a fresh install — skip silently
        return None
    if usage.free < 500 * 1024 * 1024:
        free_mb = usage.free // (1024 * 1024)
        return DoctorIssue(
            category="disk_space_low",
            message=(
                f"Espaco em disco baixo: {free_mb} MB livre em {config_dir}."
            ),
            commands=(f"Libere espaco em disco em {config_dir}",),
        )
    return None


def _check_required_packages() -> list[DoctorIssue]:
    required = ("typer", "pydantic", "pydantic-settings", "pyyaml", "httpx")
    missing: list[DoctorIssue] = []
    for name in required:
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(
                DoctorIssue(
                    category="package_missing",
                    message=f"Pacote '{name}' nao instalado.",
                    commands=(f"pip install {name}",),
                )
            )
    return missing


def _append_if_issue(issues: list[DoctorIssue], issue: DoctorIssue | None) -> None:
    if issue is not None:
        issues.append(issue)


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _print_json_report(
    *, settings: RuntimeSettings, issues: list[DoctorIssue]
) -> None:
    payload = {
        "ok": len(issues) == 0,
        "checks": {
            "endpoint": mask_sensitive(settings.endpoint_url),
            "model": settings.model_id,
            "local_only": bool(settings.local_only),
            "telemetry_enabled": bool(settings.telemetry_enabled),
        },
        "issues": [
            {
                "category": issue.category,
                "message": issue.message,
                "recovery_commands": list(issue.commands),
            }
            for issue in issues
        ],
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_issues(issues: list[DoctorIssue]) -> None:
    headings = {
        "endpoint_offline": "Conectividade",
        "timeout": "Conectividade",
        "invalid_token": "Autenticacao",
        "model_missing": "Modelo",
        "policy_mismatch": "Privacidade",
        "qmd_missing": "QMD",
        "qmd_version": "QMD",
        "kb_no_manifest": "Base de Conhecimento",
        "kb_collection_empty": "Base de Conhecimento",
        "kb_embeddings_missing": "Base de Conhecimento",
        "kb_manifest_error": "Base de Conhecimento",
        "memory_index_missing": "Memoria",
        "disk_space_low": "Sistema",
        "python_version": "Sistema",
        "package_missing": "Dependencias",
    }
    printed_groups: set[str] = set()

    typer.echo("")
    typer.echo("Problemas encontrados:")
    for issue in issues:
        group_name = headings.get(issue.category, "Diagnostico")
        if group_name not in printed_groups:
            typer.echo(f"[{group_name}]")
            printed_groups.add(group_name)
        typer.echo(f"- {issue.message}")
        for command in issue.commands:
            typer.echo(f"  -> {command}")


__all__ = [
    "DoctorIssue",
    "doctor_app",
    "doctor_command",
    "run_doctor_checks",
]
