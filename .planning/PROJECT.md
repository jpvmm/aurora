# Aurora

## What This Is

Aurora e um assistente privacy-first para Obsidian que roda 100% localmente. Ele ingere notas Markdown do vault, constrói uma base de conhecimento vetorial e combina isso com memoria de longo prazo das interacoes para responder e organizar ideias do usuario. A v1 e CLI-first, com foco em uso individual e invocacao global no terminal.

## Core Value

Privacidade total com memoria util de longo prazo sobre o vault, sem depender de servicos externos.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Ingerir vault Obsidian (.md), gerar embeddings e manter indice atualizado via CLI usando QMD.
- [ ] Executar assistente via CLI global com respostas em pt-BR por padrao, usando Agno + modelos open-source servidos por llama.cpp.
- [ ] Persistir memoria de longo prazo com Graphiti e realizar recuperacao hibrida (KB + memoria) para gerar respostas mais relevantes.

### Out of Scope

- Processamento em nuvem ou dependencia de APIs proprietarias de LLM — viola o principio de privacidade.
- Interface grafica desktop na v1 — CLI-first reduz complexidade inicial e acelera entrega.
- Colaboracao multiusuario na v1 — foco atual e uso individual.

## Context

O problema principal e transformar um vault Obsidian grande em conhecimento acessivel sem sacrificar privacidade. A proposta exige ingestao de Markdown, indexacao vetorial, memoria de interacoes e orquestracao de agente em um fluxo local rapido. Tecnologias definidas: Python 3.13, UV, Agno, Graphiti, QMD, llama.cpp, Docker e docker-compose. A experiencia inicial precisa ser simples de instalar e usar no terminal, com logs claros para processos longos como ingestao.

## Constraints

- **Privacy/Security**: Execucao 100% local — dados do vault e conversas nao podem sair da maquina.
- **Model Serving**: Somente modelos open-source em llama.cpp — sem fallback para provedores fechados.
- **Language**: Resposta padrao em pt-BR — troca de idioma apenas quando solicitado.
- **Cost/Hardware**: Funcionar bem em notebook comum — priorizar configuracao leve e barata.
- **Distribution**: CLI global com instalacao simples via UV/pipx — reduzir friccao de setup.
- **Process**: Branch por feature e testes em perspectiva de usuario — manter qualidade durante evolucao.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| QMD como base do knowledge base | Ja resolve pipeline de Markdown para vetores e reduz risco de implementacao | — Pending |
| Graphiti para memoria de longo prazo | Modela relacoes e facilita conexoes entre historico e notas | — Pending |
| Agno para framework do assistente | Suporta orquestracao de ferramentas e roteamento de contexto | — Pending |
| CLI-first na v1 | Entrega valor rapido antes de investir em UI desktop | — Pending |
| Publico inicial: usuario individual | Simplifica escopo e acelera validacao do produto | — Pending |

---
*Last updated: 2026-03-01 after initialization*
