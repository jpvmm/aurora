# Aurora — Teachings

This folder is the project's "explain it to someone learning" companion to the README. The README tells you *what* Aurora does and *how to use it*. The docs in here tell you *why it's designed this way* and *how the pieces fit together inside the code* — so you can extend, debug, or just understand the system instead of treating it as a black box.

Each doc is standalone. Pick whichever topic you're curious about; there's no required reading order beyond what each doc declares at its top.

## Index

| Doc | Topic | What you'll learn |
|---|---|---|
| [memory.md](memory.md) | How the agent's memory works | The two memory tiers, how a chat session becomes a persisted memory, how memories get pulled back into future answers, and why Aurora uses the design it does. |

## Conventions

- **pt-BR in code, en-US in docs.** User-facing CLI strings are pt-BR; these teaching docs are in English so they're accessible to anyone reading the source.
- **Code pointers use `path:line` format.** You can `cmd+click` them in most editors to jump straight to the evidence.
- **Every claim in these docs points at code.** If you read something that contradicts what the code does *now*, trust the code and update the doc.
