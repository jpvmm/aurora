# How Aurora Works With the Model (and llama.cpp)

> **Reading map.** If you've never wondered what happens between "I type `aurora ask`" and "tokens stream onto my terminal," this is the doc that answers it end to end. Assumes nothing beyond knowing what an HTTP POST is. Estimated time: 25–35 minutes. Companion to [memory.md](memory.md) — that one is about *state*, this one is about *inference*.

---

## Table of Contents

1. [Why local, and why llama.cpp specifically](#1-why-local-and-why-llamacpp-specifically)
2. [The 30-second mental model](#2-the-30-second-mental-model)
3. [The HTTP surface — what Aurora actually speaks](#3-the-http-surface--what-aurora-actually-speaks)
4. [Configuration — endpoint, model_id, model_source](#4-configuration--endpoint-model_id-model_source)
5. [The model lifecycle — who owns the server process?](#5-the-model-lifecycle--who-owns-the-server-process)
6. [Downloading a model from Hugging Face](#6-downloading-a-model-from-hugging-face)
7. [Streaming vs sync — two modes, one endpoint](#7-streaming-vs-sync--two-modes-one-endpoint)
8. [The privacy gate — loopback-only, enforced at the settings layer](#8-the-privacy-gate--loopback-only-enforced-at-the-settings-layer)
9. [Health checks and startup validation](#9-health-checks-and-startup-validation)
10. [The prompt layer — how messages are assembled](#10-the-prompt-layer--how-messages-are-assembled)
11. [Design decisions and tradeoffs](#11-design-decisions-and-tradeoffs)
12. [Exercises — trace it yourself](#12-exercises--trace-it-yourself)
13. [Where to go next](#13-where-to-go-next)

---

## 1. Why local, and why llama.cpp specifically

The fundamental bet Aurora makes is: **your notes and conversations never leave your machine.** Every architectural choice in this layer flows from that.

A few alternatives and why each was rejected:

| Option | Why not |
|---|---|
| OpenAI / Anthropic / any cloud API | Violates the premise. Your vault would be transmitted. |
| Embed a model in-process (via `llama-cpp-python` / `mlx-lm`) | Forces one Python process to hold a multi-GB model in memory, couples Aurora's lifecycle to the model's, makes CLI startup slow, forbids reusing one loaded model across concurrent invocations. |
| Ollama | Good option, but requires users to install a separate daemon with its own opinions about model management. Aurora wanted a thinner, more transparent integration. |
| Raw `llama.cpp` CLI (batch mode) | No persistent KV cache, no streaming, new process per turn — terrible UX. |

**`llama-server` from llama.cpp** wins because:

- It's a standalone binary with a long-lived process (keeps the model warm + KV cache across turns).
- It speaks an **OpenAI-compatible HTTP API** — `/v1/chat/completions` with the same JSON shape as the OpenAI SDK. Aurora can treat it as a drop-in local substitute.
- It's loopback-bindable, which makes the privacy guarantee enforceable at the network layer (not just by convention).
- It's fast enough that streaming tokens feel native on consumer hardware.

So Aurora is shaped around an assumption: **there's a `llama-server` running somewhere on your machine**, and Aurora is a well-behaved HTTP client to it.

---

## 2. The 30-second mental model

```
┌───────────────────────┐              ┌─────────────────────────┐
│      aurora CLI       │              │      llama-server       │
│                       │              │  (from llama.cpp repo)  │
│  - reads settings     │   HTTP POST  │                         │
│  - builds prompts     │  ─────────►  │  - loads a GGUF model   │
│  - streams tokens     │  ◄─── SSE    │  - OpenAI-compat API    │
│  - saves memories     │              │  - single long-lived    │
└───────────┬───────────┘              │    process              │
            │                          └─────────────────────────┘
            │
            │ optionally supervises
            │ (start/stop/status)
            ▼
┌───────────────────────┐
│  server-state.json    │    lockfile + pid + ownership + endpoint
└───────────────────────┘
```

Three things to internalize:

1. **Aurora does not do inference.** It builds prompts, sends them to `llama-server` over HTTP, and streams back tokens.
2. **Aurora optionally supervises the server.** You can let Aurora start and stop `llama-server` for you (a "managed" runtime), or run it yourself in a terminal (an "external" runtime). Aurora detects which situation it's in and adapts.
3. **Everything about the server — how to reach it, which model it's serving, whether it's healthy — is recorded in two files:** `settings.json` (user intent) and `server-state.json` (observed reality).

---

## 3. The HTTP surface — what Aurora actually speaks

Aurora uses **three HTTP endpoints**, all on llama-server:

| Endpoint | Method | Purpose | Called by |
|---|---|---|---|
| `/v1/chat/completions` | POST | Inference (streaming or sync) | Every `ask`, every `chat` turn, intent classification, summarization |
| `/v1/models` | GET | List loaded models | `doctor`, first-run validation, post-`set` check |
| `/health` | GET | Is the server up and the model loaded? | `doctor`, `model health`, lifecycle polling |

### 3.1 Surprising choice: no `httpx`, no `openai` SDK

If you peek at `src/aurora/llm/streaming.py`, you'll see something unusual for a modern Python project:

```python
# Conceptually (src/aurora/llm/streaming.py)
import json
import urllib.request

def stream_chat_completions(*, endpoint_url, model_id, messages, on_token):
    body = json.dumps({"model": model_id, "messages": messages, "stream": True}).encode()
    req = urllib.request.Request(
        f"{endpoint_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=STREAM_TIMEOUT_SECONDS) as response:
        for raw_line in response:
            # parse SSE …
```

**Just `urllib.request` from the stdlib.** No SDK, no HTTP client library.

Why? Three reasons:

- Aurora's HTTP needs are trivial. Two endpoints, one POST, SSE parsing — ~60 lines.
- Zero dependency cost. Not pulling in `httpx`/`openai` keeps the install tree thin.
- The privacy story is easier to audit. Every line of network code is right there, reading `urllib.request.urlopen`. No SDK surface area to trust.

The cost is that you lose retries, HTTP/2, connection pooling, and pretty error messages. For a local-only client talking to a loopback server, none of that matters.

### 3.2 The SSE parser

Streaming responses come back as **Server-Sent Events**. llama-server emits chunks like:

```
data: {"choices":[{"delta":{"content":"Hel"}}]}

data: {"choices":[{"delta":{"content":"lo"}}]}

data: [DONE]
```

Aurora's parser at `src/aurora/llm/streaming.py:31-42` is dead simple:

```python
for raw_line in response:
    line = raw_line.decode("utf-8").strip()
    if not line.startswith("data: "):
        continue
    payload = line[6:]              # strip "data: "
    if payload == "[DONE]":
        break
    chunk = json.loads(payload)
    delta = chunk["choices"][0]["delta"]
    if content := delta.get("content"):
        on_token(content)           # callback fires per token
        full_response.append(content)
```

That's it. `on_token` is how the CLI prints streaming output to your terminal one token at a time.

### 3.3 Timeouts

- Streaming: 120 seconds (`STREAM_TIMEOUT_SECONDS` at `src/aurora/llm/streaming.py:8`)
- Sync: 30 seconds
- Health probe: 3 seconds

No retries. If a request fails, the CLI shows the error and exits. Aurora prefers "tell the user something is wrong" over "silently retry and maybe work."

---

## 4. Configuration — endpoint, model_id, model_source

All runtime settings live in `~/Library/Application Support/aurora/settings.json` (macOS path). The schema is defined by a Pydantic model in `src/aurora/runtime/settings.py:23-44`:

| Field | Default | What it is |
|---|---|---|
| `endpoint_url` | `http://127.0.0.1:8080` | Where to reach `llama-server`. Must be loopback (see §8). |
| `model_id` | `Qwen3-8B-Q8_0` | The string sent as `"model": ...` in API calls. Must match what the server is hosting. |
| `model_source` | `Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf` | HF shorthand for downloading the GGUF if Aurora needs to fetch it. |
| `local_only` | `true` | The privacy gate flag. Defaults on. |
| `telemetry_enabled` | `false` | Defaults off. Injects `AGNO_TELEMETRY=false` etc. into spawned subprocesses. |

Two distinctions worth burning in:

### `model_id` vs `model_source`

- **`model_id`** is the *API-level name*. It's what llama-server advertises in `/v1/models` and what you send in the `"model"` field of each request. If the server is hosting `Qwen3-8B-Q8_0`, this must be `Qwen3-8B-Q8_0` exactly.
- **`model_source`** is the *download shorthand*. It's in Hugging Face `repo/model:file.gguf` form. Aurora parses it when you run `aurora config model set --source ...` and uses it to fetch the GGUF file via `huggingface_hub`.

One describes "what to call the model on the wire"; the other describes "where to download the weights from." They can match each other, or not, depending on how you label things.

### `endpoint_url`

Just the base URL: `http://127.0.0.1:8080`. Aurora appends `/v1/chat/completions`, `/v1/models`, `/health` itself.

The port is extracted from this URL and used if Aurora spawns a managed server (`--port 8080`).

---

## 5. The model lifecycle — who owns the server process?

This is the most conceptually dense part of the system. Take it slow.

### 5.1 The central distinction: managed vs external

When Aurora wants to make an inference request, *somebody* has to have started `llama-server`. That somebody is either:

- **You**, in a separate terminal, with your own `llama-server -m mymodel.gguf …` command. Aurora didn't spawn it, doesn't know its parent process, and can't kill it without your permission.
- **Aurora itself**, as a subprocess spawned by `aurora config model start`. Aurora knows the PID, the process group, and can cleanly stop it later.

Aurora calls these **external** and **managed** ownership respectively. The distinction matters because:

1. `aurora config model stop` should *not* kill an external runtime (that's your process — Aurora has no business managing it). It refuses unless you pass `--force`.
2. Telemetry env vars (`AGNO_TELEMETRY=false` etc.) can only be injected into managed runtimes. External runtimes are opaque.
3. Crash recovery — Aurora can restart a managed runtime if the PID is gone, but can't restart an external one.

### 5.2 The state file

Ownership and reality live at `~/.config/aurora/server-state.json`. Schema at `src/aurora/runtime/server_state.py:13-26`:

```python
@dataclass(frozen=True)
class ServerLifecycleState:
    ownership: Literal["managed", "external"]
    pid: int | None
    process_group_id: int | None
    endpoint_url: str
    port: int
    model_id: str
    started_at: str                    # ISO 8601
    last_transition_reason: str        # "manual_start", "external_reused", …
    crash_count: int = 0
    restart_count: int = 0
```

Every meaningful state change (`start`, `stop`, detected crash, external-reuse confirmation) writes this file. `aurora config model status` just reads and pretty-prints it.

### 5.3 How `start` decides managed-vs-external

The decision flow lives in `ServerLifecycleService.start_server()` at `src/aurora/runtime/server_lifecycle.py:166`. Simplified:

```
 aurora config model start
         │
         ▼
┌─────────────────────────┐
│ Try GET /health on      │
│ the configured endpoint │
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     │             │
  success       failure
     │             │
     ▼             ▼
 somebody       nobody is
 else already   running —
 running        spawn managed
     │             │
     ▼             ▼
 ask user:    subprocess.Popen(
 "reuse it?"    ["llama-server",
     │           "--host", host,
     ▼           "--port", port,
 ownership=     "-m", model_path,
 "external"     "--alias", model_id])
                    │
                    ▼
                ownership="managed"
                + record PID
                + poll /health until ready
```

### 5.4 How `stop` decides whether to kill

`ServerLifecycleService.stop_server()` at `src/aurora/runtime/server_lifecycle.py:227`:

- `ownership == "managed"` → send SIGTERM to the process group, wait, SIGKILL if still alive. Clean up state file.
- `ownership == "external"` and `not --force` → refuse with a clear message. Leave the process alone.
- `ownership == "external"` and `--force` → attempt to kill it anyway. (You asked.)

### 5.5 The lock file

Concurrent `aurora config model start` invocations from two terminals would race. `src/aurora/runtime/server_lock.py` provides a file-based advisory lock (`~/.config/aurora/server.lock`) that serializes lifecycle transitions. The first process that grabs the lock wins; the second waits or fails.

---

## 6. Downloading a model from Hugging Face

### 6.1 The shorthand

`aurora config model set --source "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"`.

The parser at `src/aurora/runtime/model_source.py:29` splits that on `:`:

```python
HuggingFaceTarget(
    repo_id="Qwen/Qwen3-8B-GGUF",     # before the colon
    filename="Qwen3-8B-Q8_0.gguf",     # after
    source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
)
```

Validation enforces: `repo_id` has exactly one `/`, `filename` ends in `.gguf`, no path separators that would escape the repo.

### 6.2 The download

`download_model()` at `src/aurora/runtime/model_download.py:33` uses `huggingface_hub`:

1. Call `HfApi().model_info(repo_id)` to verify the file exists and get its size.
2. If size ≥ 5 GB and `--yes` wasn't passed, prompt the user.
3. Call `hf_hub_download()` — streams the file to `~/.config/aurora/models/{repo_slug}/{filename}` where `repo_slug` is `repo_id.replace("/", "--")`.
4. Return `DownloadResult(source, local_path, downloaded, used_token)`.

### 6.3 Private repos and tokens

Flags on `aurora config model set`:

- `--private` — tells Aurora the repo needs auth. Prompts for a token interactively unless `--token` is passed.
- `--token <value>` — pass the HF token explicitly (for scripts).

Tokens are not persisted anywhere — they're held in memory for the duration of the download and then forgotten. If you need the token again later, pass it again.

### 6.4 Where the GGUF actually lives

```
~/.config/aurora/models/
└── Qwen--Qwen3-8B-GGUF/
    └── Qwen3-8B-Q8_0.gguf
```

When Aurora spawns a managed `llama-server`, it passes the full path via `-m /absolute/path/to/file.gguf`.

---

## 7. Streaming vs sync — two modes, one endpoint

Both streaming and non-streaming requests hit `/v1/chat/completions`. The only difference is `"stream": true` vs `"stream": false` in the request body.

**Aurora uses streaming for user-facing answers** — `aurora ask`, every chat turn in `aurora chat`. Reason: UX. Tokens feel immediate as they arrive.

**Aurora uses sync for internal LLM calls** — intent classification, session summarization, query reformulation (Phase 7), and the optional sufficiency judge (Phase 7). Reason: the caller needs the full string before doing anything with it (parsing intent, writing a memory file, building the next retrieval query, deciding whether to retry). There's no "partial" to render.

Both paths share `src/aurora/llm/streaming.py`. The sync path (`chat_completion_sync()` at line 46) just POSTs with `stream=False` and returns `response["choices"][0]["message"]["content"]`.

### When streaming breaks

If the connection drops mid-stream, Aurora detects the incomplete SSE and surfaces the partial response plus an error. There is no automatic retry — the user sees what was streamed so far and a "connection closed" message. Honest failure beats silent hang.

---

## 8. The privacy gate — loopback-only, enforced at the settings layer

The most important invariant in Aurora:

> **`endpoint_url` must resolve to a loopback address.**

This is not a runtime check or a nice-to-have. It is enforced at the **settings validation layer**, which means *you cannot save bad config*. If you try, `save_settings()` raises.

### 8.1 The check

`src/aurora/privacy/policy.py:11`:

```python
def is_loopback_endpoint(endpoint_url: str) -> bool:
    parsed = urlparse(endpoint_url)
    host = parsed.hostname
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
```

Accepted:
- `localhost` (any case)
- `127.0.0.1` … `127.255.255.254` (IPv4 loopback range)
- `::1` (IPv6 loopback)

Rejected:
- `0.0.0.0` — not technically loopback on every OS, rejected for safety
- Any public IP
- Any hostname that resolves to a non-loopback address at DNS time
- `http://api.openai.com/v1` (the failure mode we're preventing)

### 8.2 Where it's enforced

Two call sites, both in `src/aurora/runtime/settings.py`:

- `load_settings()` — validates on read. If someone hand-edits `settings.json` to a cloud URL, the next Aurora command fails at startup.
- `save_settings()` — validates on write. The CLI can't *accept* a bad endpoint even if you try.

So there's nowhere in normal flow that Aurora can end up pointing at a cloud host. The only way is to delete the privacy policy module entirely. (That's on purpose.)

### 8.3 Why the HTTP client doesn't re-check

You might wonder: why not also check in `streaming.py`? The answer is defense-in-depth vs. **single source of truth**. Adding the check in multiple places creates the possibility of them drifting out of sync. The settings layer is the one gate; if a bad URL reached the HTTP client, it means the settings layer has a bug, and that's the bug to fix.

`doctor` does re-verify by calling `validate_local_endpoint` explicitly — a second-opinion check that catches drift between `settings.json` on disk and what the running process loaded.

---

## 9. Health checks and startup validation

Two separate health concepts live in the code. Keep them distinct.

### 9.1 `/health` probe

`src/aurora/runtime/llama_client.py:58`. A single GET to `{endpoint}/health`:

- 3-second timeout.
- Accepts any 2xx response with `status` or `state` ∈ `{"ok", "ready", "healthy", "loading", "starting"}`.
- On `"loading"` / `"starting"`, retries up to 2 times with 1-second backoff.

This is cheap. It only answers "is the server up?"

### 9.2 `validate_runtime()` — full validation

`src/aurora/runtime/llama_client.py:121`. Used by first-run setup and `doctor`:

1. Probe `/health` (as above).
2. GET `/v1/models`. Parse `{"data": [{"id": "..."}, …]}`.
3. Confirm the configured `model_id` appears in that list.
4. Return a `RuntimeValidationResult` with the state + available models + errors.

This answers "is the server up **and hosting the model I think it's hosting**?"

A common mistake: setting `model_id = "Qwen3-8B"` in Aurora while running `llama-server --alias Qwen3-8B-Q8_0`. Health passes, `/v1/models` shows `["Qwen3-8B-Q8_0"]`, and `validate_runtime()` fires a `model_id_mismatch` error. `doctor` surfaces this cleanly.

### 9.3 Startup polling

When Aurora spawns a managed `llama-server`, it can't immediately make requests — the model takes seconds to load. `src/aurora/runtime/server_lifecycle.py:397` polls `/health` every 200ms for up to 20 seconds before declaring the startup timed out. The polling loop is the *only* reason Aurora waits at all; as soon as `/health` returns ready, the CLI proceeds.

---

## 10. The prompt layer — how messages are assembled

All user-facing inference in Aurora funnels through **three system prompts** plus one auxiliary (intent classifier).

All live in `src/aurora/llm/prompts.py`.

| Function | When used |
|---|---|
| `get_system_prompt_grounded()` | `ask` (no memory) — "only answer from vault context; cite sources inline." |
| `get_system_prompt_grounded_with_memory()` | `ask`/`chat` when memory is supplementing the vault. |
| `get_system_prompt_chat()` | Freeform chat — no grounding, no vault context. |
| `INTENT_PROMPT` | The classifier that decides vault/memory/chat (see [memory.md §5.1](memory.md#51-intent-classification--the-traffic-cop)). |
| `SUMMARIZE_SESSION_PROMPT` | Background session summarization on chat exit. |
| `REFORMULATION_SYSTEM_PROMPT` + `REFORMULATION_USER_PROMPT` | The Phase 7 iterative loop's reformulation call ([retrieval.md §12.3](retrieval.md#123-the-reformulation--what-the-llm-sees-what-it-doesnt)). System prompt fixes the role + privacy contract; user prompt template wraps the original query and the deterministic sufficiency reason. Privacy-by-construction: the prompt template has no slot for note paths or content. |
| `SUFFICIENCY_JUDGE_PROMPT` | The Phase 7 opt-in LLM judge ([retrieval.md §12.2](retrieval.md#122-the-deterministic-sufficiency-check)). Asked "este contexto basta para responder?" — returns text containing "sim" / "não" with negative-wins-on-tie ambiguity policy. Off by default (`iterative_retrieval_judge=false`). |

### 10.1 Messages shape

Every call to llama-server uses the OpenAI chat-completion message format:

```json
[
  {"role": "system", "content": "<preferences + system prompt + assembled context>"},
  {"role": "user",   "content": "<the user's actual question>"}
]
```

For multi-turn chat, prior turns are replayed as alternating `user` / `assistant` messages.

### 10.2 Sampling parameters

**Aurora does not override sampling params.** No `temperature`, no `top_p`, no `top_k` in any request body. llama-server uses its compiled-in defaults.

Why: opinionated sampling was deferred until there's evidence it's needed. If you want determinism for an eval harness, you can patch it in, but the codebase is intentionally thin here.

---

## 11. Design decisions and tradeoffs

### 11.1 Stdlib-only HTTP client

Explained in §3.1. The tradeoff is lose-retries-gain-transparency. Worth re-reading once you're sure you understand what the alternative buys.

### 11.2 State file next to settings file

Some systems would encode runtime state into the settings file itself. Aurora keeps `settings.json` (intent) and `server-state.json` (observed reality) separate because they have different update cadences and different failure semantics. You `git diff` settings; state is ephemeral.

### 11.3 Ownership inferred from behavior, not declared

When a user runs `aurora config model start` and Aurora finds `/health` already responding, Aurora doesn't assume "must be a stale managed runtime I lost track of." It prompts: *reuse this external runtime?* Users are never surprised by Aurora killing a process they didn't know was managed.

### 11.4 The lock file over the state file

Aurora locks on `server.lock`, not on `server-state.json`. The state file is read by `doctor`, `status`, etc. — operations that should be non-blocking even while `start`/`stop` are in flight. Separating reader and writer concerns is worth the extra file.

### 11.5 No SDK means no auto-upgrade

If llama.cpp changes the SSE format (it once almost did), Aurora's tiny parser would break. An SDK would abstract it. Tradeoff: we accept the risk because the SSE format has been stable for ~18 months and the parser is 12 lines.

### 11.6 Privacy enforced at the settings layer, not the HTTP layer

Explained in §8.3. Single-source-of-truth wins over defense-in-depth here because the gain (fewer places for bugs to hide) outweighs the cost (a second check that'd catch a bug we don't expect to exist).

---

## 12. Exercises — trace it yourself

Best way to internalize this layer:

1. **Watch an HTTP call live.** Run `llama-server` with `--verbose`. In another terminal, `aurora ask "ola"`. Watch the request body arrive, the SSE stream out. Can you identify each token in the server's log? Each `data: { ... }` line in a hypothetical tcpdump?
2. **Break the `model_id`.** Edit `settings.json` to a model_id your server isn't hosting. Run `aurora doctor`. What category does it flag? Run `aurora ask "x"` — where in the code does the error come from?
3. **Provoke the privacy gate.** Try `aurora config model set --endpoint http://example.com:8080`. What error do you get? Now try to hand-edit `settings.json` to that value. What happens next time you run any Aurora command?
4. **Observe the lifecycle.** `aurora config model start`. Read `server-state.json`. `aurora config model stop`. Read it again. Start `llama-server` yourself in a terminal. Run `aurora config model start`. What's different?
5. **Benchmark streaming.** Add `time.perf_counter()` calls around `stream_chat_completions()`. How much of the total latency is first-token? All remaining tokens? What's the actual tokens/sec your hardware delivers?
6. **Rewrite the parser.** The SSE parser at `streaming.py:31-42` is 12 lines. Can you rewrite it in 8? In 3 (with a regex)? Which is easier to understand for someone new to the codebase?

Bonus hard mode: port the HTTP client from `urllib.request` to `httpx` (async). What did you gain? What did you lose? Was it worth it?

---

## 13. Where to go next

| To understand... | Read... |
|---|---|
| How memories layer onto the prompt | [memory.md](memory.md) §5 |
| The full pydantic settings model | `src/aurora/runtime/settings.py` (top-to-bottom) |
| The lifecycle orchestrator | `src/aurora/runtime/server_lifecycle.py` — the densest file in the repo; read `start_server` and `stop_server` first |
| The privacy policy in detail | `src/aurora/privacy/policy.py` (40 lines — read it whole) |
| How the CLI wires everything together | `src/aurora/cli/model.py` (the `set/start/stop/status/health` commands) |
| How `doctor` probes everything | `src/aurora/cli/doctor.py` |
| Testing the lifecycle | `tests/runtime/test_server_lifecycle.py` — good reading for learning the state machine |
| llama.cpp's HTTP API reference | External — [llama.cpp server docs](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md) |

---

**Appendix — one-sentence summary per concept:**

- **llama.cpp/`llama-server`** — the inference engine Aurora talks to over HTTP.
- **`/v1/chat/completions`** — the OpenAI-compatible endpoint Aurora POSTs to for all inference.
- **SSE streaming** — tokens arrive as `data: {...}` lines terminated by `[DONE]`.
- **`model_id`** — how the model is named on the wire; **`model_source`** — where to download it from.
- **managed vs external ownership** — who started `llama-server`: Aurora, or you?
- **`server-state.json`** — the observed reality of the runtime, updated on every state transition.
- **Loopback gate** — enforced at the settings layer; `endpoint_url` must resolve to `127.x`, `localhost`, or `::1`.
- **Stdlib-only HTTP** — Aurora uses `urllib.request`, not `httpx` or the OpenAI SDK; 60 lines total.
