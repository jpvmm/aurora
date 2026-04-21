# Aurora

> A privacy-first Obsidian assistant that runs 100% locally. Ingests your vault, builds a vector knowledge base, and combines it with long-term memory of your conversations to answer questions and help organize ideas — without sending anything to the cloud.

Aurora is CLI-first. Portuguese (pt-BR) is the default response language. The runtime uses `llama.cpp` for local inference and [QMD](https://github.com/tobi/qmd) for vector storage. No telemetry. No cloud fallback. Data never leaves your machine.

---

## Table of Contents

1. [Requirements](#1-requirements)
2. [Installation](#2-installation)
3. [First-Run Setup](#3-first-run-setup)
4. [Core Workflow](#4-core-workflow-in-five-commands)
5. [Command Reference](#5-command-reference)
   - [`aurora ask`](#51-aurora-ask)
   - [`aurora chat`](#52-aurora-chat)
   - [`aurora status`](#53-aurora-status)
   - [`aurora doctor`](#54-aurora-doctor)
   - [`aurora config`](#55-aurora-config)
     - [`config show`](#551-config-show)
     - [`config setup`](#552-config-setup)
     - [`config kb`](#553-config-kb)
     - [`config model`](#554-config-model)
     - [`config memory`](#555-config-memory)
6. [Where Aurora Stores Things](#6-where-aurora-stores-things)
7. [Privacy Model](#7-privacy-model)
8. [Troubleshooting](#8-troubleshooting)
9. [Shell Completion](#9-shell-completion)
10. [Uninstall](#10-uninstall)

---

## 1. Requirements

| Dependency | Minimum | Notes |
|---|---|---|
| **Python** | 3.13 | Strict floor — `aurora doctor` will block on older versions. |
| **uv** or **pipx** | any recent | Used to install Aurora as a global CLI. `uv tool` is recommended. |
| **qmd** | 0.1.1+ | Vector storage engine. Installed automatically as a Python dep, but the `qmd` binary must be on your `PATH`. |
| **llama.cpp server** | any recent | `llama-server` or an OpenAI-compatible local endpoint. Defaults to `http://127.0.0.1:8080`. |
| **A GGUF model** | any | Aurora defaults to `Qwen3-8B-Q8_0` from `Qwen/Qwen3-8B-GGUF`. You can download any other GGUF via `aurora config model set --source ...` or bring your own. |
| **Obsidian vault** | — | Any folder with Markdown files. Aurora never writes to the vault, it only reads. |
| **Disk** | ~1–20 GB | Model file + QMD index + memory files. `aurora doctor` warns below 500 MB free. |

Supported platforms: macOS, Linux, Windows (via Git Bash/WSL). Tested primarily on macOS.

---

## 2. Installation

Aurora is a Python package that ships a `aurora` script entry point. Install it globally so the command is available from any directory.

### Option A — `uv tool` (recommended)

```bash
git clone <repo-url> aurora
cd aurora
uv tool install .
```

### Option B — `pipx`

```bash
git clone <repo-url> aurora
cd aurora
pipx install .
```

### Make sure `aurora` is on your `PATH`

If running `aurora --help` says "command not found":

```bash
# For uv:
uv tool update-shell

# For pipx:
pipx ensurepath
```

Restart your shell, then verify:

```bash
aurora --help
```

You should see the top-level command surface:

```
Usage: aurora [OPTIONS] COMMAND [ARGS]...

  Aurora CLI local.

Commands:
  ask        Pergunte ao vault e receba respostas fundamentadas.
  chat       Inicie uma conversa interativa com Aurora.
  status     Painel de estado atual do Aurora.
  doctor     Diagnostico de runtime local e privacidade.
  config     Inspecao da configuracao global.
  kb         [DEPRECADO] Use `aurora config kb ...`
  model      [DEPRECADO] Use `aurora config model ...`
  memory     [DEPRECADO] Use `aurora config memory ...`
```

### Start a local `llama.cpp` server

Aurora does **not** start `llama-server` for you on the first run — it expects the endpoint to be reachable. A typical setup:

```bash
# Download or point to a GGUF model, then:
llama-server -m /path/to/Qwen3-8B-Q8_0.gguf --host 127.0.0.1 --port 8080
```

Leave that process running in a separate terminal (or under a process manager). Aurora talks to it over HTTP. The default endpoint Aurora expects is `http://127.0.0.1:8080`.

> **Privacy gate:** Aurora's `local_only` flag is on by default and the CLI will **reject** any endpoint whose hostname is not a loopback address. There is no way to point Aurora at a cloud provider through normal config.

---

## 3. First-Run Setup

The first time you run `aurora` with no subcommand and no settings file, a guided wizard starts automatically:

```bash
aurora
```

The wizard asks for:

| Prompt | Default | What it does |
|---|---|---|
| **Endpoint local llama.cpp** | `http://127.0.0.1:8080` | Where Aurora sends inference requests. Must be loopback. |
| **Modelo padrão** | `Qwen3-8B-Q8_0` | The model id to send in each request. Must match what `llama-server` is hosting. |
| **Fonte Hugging Face (opcional)** | *(empty)* | Optional `repo/model:file.gguf` shorthand to download from HF. Leave empty if you already have the model locally. |

After you confirm, Aurora:

1. Writes your settings to the global config file.
2. Attempts to contact the endpoint and validate the model is reachable.
3. Prints a summary and points you at `aurora ask "Ola"` to try it.

If validation fails, the wizard prints the specific error and recovery commands, then offers to retry. You can always re-run the wizard later:

```bash
aurora config setup
```

---

## 4. Core Workflow in Five Commands

Once installed and configured, a typical first session looks like:

```bash
# 1. Point Aurora at your Obsidian vault
aurora config kb config set --vault /Users/you/Obsidian/MyVault

# 2. Build the knowledge base (first ingestion — can take a few minutes)
aurora config kb ingest /Users/you/Obsidian/MyVault

# 3. Check that everything is healthy
aurora doctor

# 4. Ask a one-shot grounded question
aurora ask "quais notas mencionam postgres performance?"

# 5. Open an interactive conversation
aurora chat
```

Later, when your vault has changed:

```bash
aurora config kb update   # re-index only what changed
aurora status             # confirm the new note count
```

That is the entire day-to-day loop.

---

## 5. Command Reference

All commands print help with `--help`. Most commands accept a `--json` flag for machine-readable output.

> **A note on deprecated aliases:** `aurora kb`, `aurora model`, and `aurora memory` still work but print a `[DEPRECADO]` warning to stderr and delegate to the canonical `aurora config ...` paths. New scripts should use the canonical forms.

### 5.1 `aurora ask`

Single-shot grounded question. Aurora classifies the question's intent, searches the vault and episodic memories, and streams a grounded answer.

```bash
aurora ask "sua pergunta aqui"
aurora ask --json "sua pergunta aqui"
```

| Flag | Effect |
|---|---|
| `--json` | Emit a structured JSON payload (`{query, answer, sources, insufficient_evidence}`) instead of streaming text. |

If Aurora cannot find enough evidence in the vault or memory to answer honestly, it prints an "insufficient evidence" message rather than hallucinating.

**Example — text mode:**

```
$ aurora ask "o que eu disse sobre vector databases?"
Analisando pergunta...
Buscando no vault e memorias...
Encontrei 4 nota(s) e 1 memoria(s). Gerando resposta...
<streamed answer>
```

**Example — JSON mode:**

```json
{
  "query": "o que eu disse sobre vector databases?",
  "answer": "...",
  "sources": ["notes/dbs/vectors.md", "daily/2025-11-03.md"],
  "insufficient_evidence": false
}
```

---

### 5.2 `aurora chat`

Interactive multi-turn chat. Aurora remembers the turns in the session, routes each turn through intent classification (vault / memory / chat), and **saves a summary of the session to long-term memory in the background** when you exit.

```bash
aurora chat
```

Inside the chat:
- Type `sair`, `exit`, or `quit` to end the session.
- `Ctrl-C` also ends the session gracefully.

Flags:

| Flag | Effect |
|---|---|
| `--clear` | Delete the in-memory chat history file and exit. Does NOT touch long-term memories. |

**Example session:**

```
$ aurora chat
Aurora Chat — digite 'sair' para encerrar.

voce> resume o que eu anotei essa semana sobre arquitetura
<streamed answer referencing this week's notes>

voce> e a decisao sobre filas?
<streamed answer that carries the previous-turn context forward>

voce> sair
Ate logo!
```

After exit, a background thread summarizes the conversation and writes it into the episodic memory store — so future `aurora ask` and `aurora chat` sessions can refer back to it.

---

### 5.3 `aurora status`

Read-only unified dashboard. Shows model, KB, memory, disk, and privacy state at a glance. Never triggers inference, never auto-starts the server, never writes anything.

```bash
aurora status
aurora status --json
```

**Text output (example):**

```
Aurora status
- versao: 0.1.0

Modelo
- estado: running
- modelo: Qwen3-8B-Q8_0
- endpoint: http://127.0.0.1:8080
- pid: 54321
- uptime(s): 3721

KB
- vault: /Users/you/Obsidian/MyVault
- notas indexadas: 337
- ultima atualizacao: 2026-04-11T12:03:11Z

Memoria
- memorias: 4

Config
- local-only: ativado
- telemetria: desativada
```

`--json` returns the same data as a structured payload suitable for scripting.

---

### 5.4 `aurora doctor`

Runtime + privacy + full-stack diagnostics. Runs a series of checks and prints any issues it finds, each with a pt-BR recovery command. Doctor **never auto-fixes** — it only reports.

```bash
aurora doctor
aurora doctor --json
```

Checks include:

- **Privacy policy:** endpoint is loopback, `local_only` flag is on.
- **Runtime validation:** the configured endpoint is reachable and the configured model responds.
- **Python version:** ≥ 3.13.
- **QMD binary:** `qmd` is on `PATH` and responds to `--version`.
- **KB manifest:** Aurora's KB manifest file exists.
- **KB embeddings:** the configured QMD collection contains the indexed corpus.
- **Memory index:** if memories exist, the `aurora-memory` QMD collection exists too.
- **Disk space:** ≥ 500 MB free on the config dir's volume.
- **Required packages:** core runtime dependencies importable.

**Healthy output:**

```
Diagnostico Aurora
- endpoint: http://127.0.0.1:8080
- model: Qwen3-8B-Q8_0
- local-only: ativado
- telemetria: desativada

Runtime local pronto. Nenhum problema encontrado.
```

**With issues, doctor groups them by category and shows recovery commands,** e.g.:

```
[qmd_missing] QMD nao encontrado no PATH.
- pip install qmd
```

Use `--json` to pipe doctor output into scripts or your own monitoring.

---

### 5.5 `aurora config`

Parent namespace for configuration and administrative operations. The raw `aurora config` with no subcommand points you to `aurora config show` or `aurora config --help`.

#### 5.5.1 `config show`

Print the current resolved runtime configuration (sensitive values are masked):

```bash
aurora config show
```

Output sections:
- **Runtime** — endpoint, model id, model source.
- **KB** — vault path, active index name, active collection name, auto-embeddings flag.
- **Privacidade** — `local_only`, `telemetry_enabled`, and the defaults Aurora exports for `AGNO_TELEMETRY` / `GRAPHITI_TELEMETRY_ENABLED`.

#### 5.5.2 `config setup`

Re-run the guided first-run wizard. Useful if you want to re-validate the runtime or change the endpoint/model interactively.

```bash
aurora config setup
```

#### 5.5.3 `config kb`

Everything about the vault knowledge base.

##### Lifecycle operations

| Command | What it does |
|---|---|
| `aurora config kb ingest <vault-path>` | First-time ingestion of an Obsidian vault. Walks the folder, extracts notes, and indexes them in the active QMD collection. |
| `aurora config kb update` | Re-index only notes that changed since the last run (based on mtime). Use `--verify-hash` to fall back to content hashing. |
| `aurora config kb delete` | Destructive — removes all indexed content from the active collection. Requires `--yes` in non-interactive shells. |
| `aurora config kb rebuild` | Full rebuild: deletes and re-ingests. Equivalent to `delete` + `ingest` but atomic. |
| `aurora config kb recent` | Read-only — list the most recently ingested notes sorted by `indexed_at`. Accepts `--limit N` / `-n N` (default 10) and `--json`. Useful for confirming `update` actually picked up your new notes. |

The four mutating commands (`ingest`, `update`, `delete`, `rebuild`) accept:
- `--json` — structured output
- `--dry-run` (not on `delete`) — preview counters without touching the index
- `--index NAME` / `--collection NAME` — override the active QMD index/collection for this run only

**Example — see what was just indexed:**

```bash
$ aurora config kb recent -n 3
vault: /Users/you/Obsidian/MyVault
notas recentes: 3 de 337
  2026-04-21T14:02:11Z  daily/2026-04-21.md
  2026-04-21T13:48:00Z  projects/aurora.md
  2026-04-20T22:10:55Z  notes/dbs/vectors.md
```

**Example first ingestion:**

```bash
$ aurora config kb ingest /Users/you/Obsidian/MyVault
etapa: scan read=0 indexed=0 updated=0 removed=0 skipped=0 errors=0
etapa: ingest read=337 indexed=337 updated=0 removed=0 skipped=0 errors=0
operacao: ingest
dry-run: nao
duracao_s: 42.183
vault: /Users/you/Obsidian/MyVault
effective_scope: include=[] exclude=['.obsidian', '.trash']
totais: read=337 indexed=337 updated=0 removed=0 skipped=0 errors=0
embedding: atualizado
```

If embeddings fail partially, Aurora exits with code `2` and prints the category plus a recovery command — the index is in a consistent state, but you'll want to re-run.

##### Configuration inspection and changes

```bash
aurora config kb config show
aurora config kb config set [OPTIONS]
```

Flags for `config set`:

| Flag | Effect |
|---|---|
| `--vault PATH` | Default vault path used when `ingest` is called with no argument. Validated at set-time: the path must exist and be a directory, must not contain embedded whitespace (newlines/tabs — usually a paste accident), and `~` is expanded to an absolute path before being persisted. |
| `--include PATTERN` | Glob patterns to include. Repeat to add multiple. |
| `--exclude PATTERN` | Glob patterns to exclude. Repeat to add multiple. |
| `--index NAME` | Active QMD index name (default `aurora-kb`). |
| `--collection NAME` | Active QMD collection name (default `aurora-kb-managed`). |
| `--auto-embeddings` / `--no-auto-embeddings` | Whether KB mutations automatically trigger re-embedding. On by default. |

##### Scheduler

Run KB updates automatically once a day at a local hour.

```bash
aurora config kb scheduler enable --hour 9
aurora config kb scheduler status
aurora config kb scheduler disable
```

The scheduler is in-process — it runs when Aurora commands are invoked and catches up if a slot was missed. It is **not** a system-level cron.

#### 5.5.4 `config model`

Manage the local `llama.cpp` runtime and the model it serves.

| Command | What it does |
|---|---|
| `aurora config model set` | Write the endpoint, model id, and (optional) HF source to settings. Optionally downloads the model from Hugging Face. |
| `aurora config model start` | Start a managed `llama-server` process, or (with confirmation) reuse an external one already running on the endpoint. |
| `aurora config model stop` | Stop a managed runtime. Requires `--force` to stop an externally-owned process. |
| `aurora config model status` | Show the lifecycle state from the lock file. Does not touch the network. |
| `aurora config model health` | Ping the endpoint and report model readiness. Exits non-zero if unhealthy. |

**Typical flow for switching models:**

```bash
# Download and configure a new model from Hugging Face
aurora config model set \
  --endpoint http://127.0.0.1:8080 \
  --source "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf" \
  --yes

# Aurora will prompt you to confirm restart if a managed runtime is running
# and you changed the model id.
```

For private HF repos, pass `--private` and Aurora will prompt for a token (or accept `--token <value>`).

The `local_only` privacy gate applies here too: you cannot point `--endpoint` at a non-loopback host.

#### 5.5.5 `config memory`

Manage long-term episodic memory — the session summaries Aurora writes when you exit a `chat` session, plus your "preferences" file.

| Command | What it does |
|---|---|
| `aurora config memory list` | List every episodic memory with date, turn count, and topic. |
| `aurora config memory search "<query>"` | Semantic search across memories via QMD. |
| `aurora config memory edit` | Open the preferences file (`preferences.md`) in `$EDITOR` (defaults to `nano`). Preferences are injected into the system prompt during chat. |
| `aurora config memory clear` | Remove **all** episodic memories and the `aurora-memory` QMD collection. Destructive — requires `--yes` in non-interactive shells. |

The preferences file is a plain Markdown document where you can write:
- Conventions you want the assistant to follow ("always respond with bullet points", "prefer pt-BR").
- Rules about your projects ("when I mention `aurora`, I mean the Obsidian assistant").
- Any other durable context.

Preferences are Tier-1 memory — they are always loaded. Episodic memories are Tier-2 and retrieved via semantic search per-query.

---

## 6. Where Aurora Stores Things

All state lives in a **single per-user config directory**. On macOS that resolves to:

```
~/Library/Application Support/aurora/
```

On Linux: `~/.config/aurora/`. On Windows: `%APPDATA%\aurora\aurora\`. You can override the location by setting the `AURORA_CONFIG_DIR` environment variable.

Contents of the config dir:

| File / folder | Purpose |
|---|---|
| `settings.json` | Persisted runtime settings (endpoint, model, KB config, retrieval tuning). |
| `server-state.json` | Current lifecycle state of the managed `llama-server`. |
| `server.lock` | Lock file preventing concurrent lifecycle transitions. |
| `kb.lock` | Lock file preventing concurrent KB mutations. |
| `kb-manifest.json` | Mapping of indexed notes → hash / mtime for incremental updates. |
| `kb-state.json` | Operation history (last ingest, last update, counters). |
| `kb-qmd-corpus/` | Aurora-managed QMD corpus files for the KB. |
| `memory/` | Episodic memory markdown files — one per summarized chat session. |
| `preferences.md` | Tier-1 memory injected into every chat system prompt. |

Aurora **never** writes into the Obsidian vault. Reads only.

To fully reset Aurora, delete the config dir. The next `aurora` invocation will re-run the first-run wizard.

---

## 7. Privacy Model

Privacy is not a toggle — it is enforced at several layers:

1. **Endpoint validation.** `local_only` is on by default. The settings validator refuses any non-loopback endpoint. Even if you hand-edit `settings.json`, `aurora doctor` will flag it as `policy_mismatch` on the next run.
2. **Telemetry disabled by default.** Aurora sets `AGNO_TELEMETRY=false` and `GRAPHITI_TELEMETRY_ENABLED=false` as the default environment for anything it spawns.
3. **No cloud fallback.** There is no code path that calls an external inference API. Model serving is `llama.cpp` only.
4. **Vault is read-only.** Aurora ingests Markdown but never modifies or writes to the vault directory.
5. **Sensitive values are masked** in `config show` and `doctor` output — HF tokens, query-string credentials, and URL userinfo are redacted.

If you find a code path that violates any of the above, it is a bug — please open an issue.

---

## 8. Troubleshooting

When something goes wrong, **start with `aurora doctor`.** Every issue it reports includes a pt-BR recovery command you can copy-paste.

Common scenarios:

### "O endpoint `http://...` viola a politica local-only."

Your settings file contains a non-loopback endpoint. Fix:

```bash
aurora config model set --endpoint http://127.0.0.1:8080
```

### "Runtime externo detectado" on `model start`

Something is already listening on your endpoint port. Either Aurora's previous run, another `llama-server`, or an unrelated process. You can:
- **Reuse it:** `aurora config model start --yes` — trust it as a valid runtime.
- **Replace it:** stop the external process, then run `aurora config model start --force`.

### "QMD nao encontrado no PATH."

`qmd` is a Python package but also needs a CLI binary:

```bash
pip install qmd
# or: uv tool install qmd
```

Then re-run `aurora doctor`.

### Ingestion fails with "embeddings desatualizados (falha parcial)"

The corpus was indexed but embeddings were not fully generated. Aurora exits with code `2` on purpose so CI catches this. Re-run `aurora config kb rebuild` — or use the recovery command printed alongside the warning.

### `aurora ask` returns "insufficient evidence"

Aurora refused to answer because retrieval found nothing relevant enough. This is intentional — it prefers honesty over confabulation. Check:
- Is the vault ingested? `aurora status` should show a non-zero note count.
- Is the query in Portuguese? Retrieval is language-tuned — try rephrasing.
- Consider increasing `retrieval_top_k` in `settings.json` (bounds: 5–30).

### `kb update` reports zero notes but you just added some

Almost always a vault-path mismatch between your config and where you're actually saving notes. Triage in three commands:

```bash
aurora config kb config show                      # what path is Aurora reading?
aurora config kb update --dry-run --json          # how many notes does scan find? (look at counters.read)
aurora config kb recent -n 1                      # when was the last note actually indexed?
```

If `config show` prints a path that looks wrapped across lines or contains unexpected whitespace, you pasted a bad value into `--vault`. The CLI now validates this at set-time, but older configs persisted before validation can still contain the problem. Re-set it:

```bash
aurora config kb config set --vault "/absolute/path/to/vault"
aurora config kb ingest     "/absolute/path/to/vault"
```

Shell-quoting gotcha: inside double quotes, `\ ` does **not** escape a space — the backslash is passed through literally. Either quote the whole path with plain spaces, or drop the quotes and backslash-escape (not both).

### Python 3.12 or older

Aurora requires Python 3.13. `uv tool install` will refuse to install on an older interpreter. Upgrade Python, then retry.

### Deprecated alias warnings

If scripts print `[DEPRECADO]: aurora kb foi movido. Use aurora config kb ...`, they still work — but update them to the canonical `aurora config ...` path when convenient. Old aliases will be removed in a future release.

---

## 9. Shell Completion

Aurora uses Typer's built-in completion support.

```bash
# Install completion for your current shell (bash/zsh/fish/powershell)
aurora --install-completion

# Print the completion script without installing
aurora --show-completion
```

Restart your shell to pick up the completion.

---

## 10. Uninstall

```bash
# If you installed with uv:
uv tool uninstall aurora

# If you installed with pipx:
pipx uninstall aurora

# Optionally wipe local state (settings, KB, memories):
rm -rf "~/Library/Application Support/aurora"    # macOS
rm -rf "~/.config/aurora"                         # Linux
```

The Obsidian vault is never touched by uninstall — Aurora only ever read from it.

---

## Getting Help

- `aurora --help` — top-level command surface
- `aurora <command> --help` — per-command flags
- `aurora doctor` — health diagnosis with recovery commands
- `aurora status` — read-only runtime dashboard
- `aurora config show` — current configuration

For issues, please open a ticket on the repository with the output of `aurora doctor --json` attached.
