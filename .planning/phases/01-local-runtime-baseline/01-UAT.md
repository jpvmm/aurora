---
status: resolved
phase: 01-local-runtime-baseline
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md
started: 2026-03-02T01:12:50Z
updated: 2026-03-03T20:49:22Z
---

## Current Test

number: 2
name: Root No-Args Discovery
expected: |
  Com configuracao existente, executar `aurora` (sem subcomando)
  deve mostrar help, sem erro silencioso.
awaiting: user response

## Tests

### 1. Root Help Surface
expected: `aurora --help` mostra `setup`, `config`, `model` e `doctor`.
result: passed
reported: "Ive got this error: - Nao foi possivel conectar ao endpoint local llama.cpp. Detalhe: [Errno 61] Connection refused -> aurora model set --endpoint http://127.0.0.1:8080 -> aurora doctor"
severity: blocker

### 2. Root No-Args Discovery
expected: Com configuracao existente, executar `aurora` (sem subcomando) mostra help, sem erro silencioso.
result: pending

### 3. Model Set Local Endpoint
expected: `aurora model set` aceita endpoint local + modelo e salva configuracao global sem falhar.
result: pending

### 4. Model Set Cloud Block
expected: `aurora model set --endpoint https://api.openai.com/v1 ...` deve ser bloqueado com mensagem clara de local-only.
result: pending

### 5. Config Visibility
expected: `aurora config show` exibe endpoint/modelo e estado explicito de local-only + telemetria desativada.
result: pending

### 6. Setup Wizard Trigger
expected: Sem configuracao valida, executar `aurora` deve iniciar wizard guiado em pt-BR.
result: pending

### 7. Setup Validation Gate
expected: No wizard, validacao de endpoint/modelo bloqueia conclusao ate passar e oferece orientacao de correcao.
result: pending

### 8. Doctor Diagnostics
expected: `aurora doctor` mostra diagnostico acionavel (endpoint/modelo/privacidade) e comandos de recuperacao.
result: pending

## Summary

total: 8
passed: 1
issues: 0
pending: 7
skipped: 0

## Gaps

- truth: "`aurora --help` mostra `setup`, `config`, `model` e `doctor`."
  status: resolved
  reason: "Resolvido via fase 01.1 (planos 01.1-03 e 01.1-04), adicionando lifecycle CLI e paridade de contrato de health para diagnostico acionavel."
  severity: blocker
  test: 1
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
