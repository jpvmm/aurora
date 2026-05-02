"""System prompts and classification prompts for Aurora LLM interactions."""
from __future__ import annotations

from datetime import date
from pathlib import Path


def _date_context() -> str:
    """Return a temporal context line with today's date."""
    return f"Data de hoje: {date.today().isoformat()}."


_GROUNDED_BASE = """Voce e Aurora, um assistente pessoal privado.
{date_context}
Responda SOMENTE com base nas notas do vault fornecidas no contexto.
Cite as fontes inline no formato [caminho/nota.md] imediatamente apos a informacao usada.
Deduplique as citacoes: cite cada nota apenas uma vez.
Se a informacao nao estiver no contexto fornecido, diga que nao encontrou evidencia suficiente.
Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente.
Nao invente informacoes nem extrapole alem do que esta nas notas."""

_GROUNDED_WITH_MEMORY_BASE = """Voce e Aurora, um assistente pessoal privado.
{date_context}
Responda com base nas notas do vault e nas memorias fornecidas no contexto.
Cite as fontes inline:
- Notas do vault: [caminho/nota.md]
- Memorias: [memoria: titulo]
Deduplique as citacoes: cite cada fonte apenas uma vez.
Quando houver conflito entre uma memoria antiga e uma nota atual do vault, prefira a nota do vault (informacao mais recente).
Se a informacao nao estiver no contexto fornecido, diga que nao encontrou evidencia suficiente.
Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente.
Nao invente informacoes nem extrapole alem do que esta nas fontes."""

_CHAT_BASE = """Voce e Aurora, um assistente pessoal privado.
{date_context}
Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente.
Voce pode conversar livremente sobre qualquer assunto."""


def get_system_prompt_grounded() -> str:
    """Return grounded system prompt with current date."""
    return _GROUNDED_BASE.format(date_context=_date_context())


def get_system_prompt_grounded_with_memory() -> str:
    """Return grounded+memory system prompt with current date."""
    return _GROUNDED_WITH_MEMORY_BASE.format(date_context=_date_context())


def get_system_prompt_chat() -> str:
    """Return chat system prompt with current date."""
    return _CHAT_BASE.format(date_context=_date_context())


# Keep constants for backward compatibility (tests that import them directly)
# These are snapshots without date — prefer the get_* functions for runtime use.
SYSTEM_PROMPT_GROUNDED = _GROUNDED_BASE.format(date_context=_date_context())
SYSTEM_PROMPT_GROUNDED_WITH_MEMORY = _GROUNDED_WITH_MEMORY_BASE.format(date_context=_date_context())
SYSTEM_PROMPT_CHAT = _CHAT_BASE.format(date_context=_date_context())

INTENT_PROMPT = """Analise a mensagem do usuario e responda em formato estruturado.

1. Classifique a intencao:
- vault: pergunta sobre notas, documentos, informacoes do vault pessoal
- memory: pergunta sobre conversas anteriores, historico de interacoes, memorias de sessoes passadas
- chat: conversa geral, tarefa generica, sem relacao com vault nem memorias

2. Defina a estrategia de busca (apenas para vault e memory):
- hybrid: busca semantica (melhor para perguntas conceituais, temas amplos)
- keyword: busca por palavras-chave exatas (melhor para nomes proprios, termos especificos, datas)
- both: combinar semantica + palavras-chave (quando ha termos especificos dentro de uma pergunta ampla)

3. Extraia os termos de busca mais relevantes (apenas para vault e memory):
- Para hybrid: reformule como uma boa query de busca
- Para keyword: extraia os termos exatos que devem ser buscados
- Para both: forneça ambos

Formato de resposta (3 linhas, sem explicacao):
intent: vault|memory|chat
search: hybrid|keyword|both
terms: <termos de busca separados por virgula>

Exemplos:
Mensagem: "encontre notas que mencionei a Rosely"
intent: vault
search: both
terms: Rosely, notas mencionei Rosely

Mensagem: "sobre o que conversamos ontem?"
intent: memory
search: hybrid
terms: conversa sessao anterior

Mensagem: "o que escrevi sobre produtividade?"
intent: vault
search: hybrid
terms: produtividade

Mensagem: "quem é o Anderson?"
intent: vault
search: keyword
terms: Anderson

Mensagem: "me ajude a escrever um email"
intent: chat
search: none
terms: none

Mensagem: {message}"""

INSUFFICIENT_EVIDENCE_MSG = (
    "Nao encontrei evidencia suficiente no vault para responder. "
    "Tente reformular ou verifique se o topico esta indexado."
)

SUMMARIZE_SESSION_PROMPT = """Resuma a conversa a seguir de forma concisa e util para consulta futura.

Formato obrigatorio:
- Primeira linha: titulo curto (maximo 60 caracteres) descrevendo o tema principal
- Segunda linha: Data da sessao: {date}
- Corpo organizado nas seguintes secoes:

## Topicos
Liste os principais assuntos discutidos.

## Decisoes
Liste decisoes tomadas ou conclusoes alcancadas. Se nenhuma, escreva "Nenhuma decisao registrada."

## Contexto
Informacoes de fundo relevantes para consulta futura.

Nao inclua saudacoes ou preambulos. Va direto ao conteudo.

Conversa:
{conversation}"""


REFORMULATION_SYSTEM_PROMPT = """Voce reformula consultas para uma base de conhecimento pessoal.

Sua tarefa: dada uma consulta original que retornou poucos resultados, gerar UMA nova consulta substancialmente diferente que tenha mais chance de encontrar evidencia relevante.

Estrategias possiveis:
- Trocar termos amplos por especificos (ou vice-versa)
- Reformular como pergunta direta vs descritiva
- Usar sinonimos ou termos relacionados em pt-BR
- Adicionar contexto temporal ou tematico implicito

Regras:
- Responda APENAS com a consulta reformulada, sem explicacao, sem prefixo, sem aspas
- Maximo 15 palavras
- Sempre em pt-BR
- NUNCA repita a consulta original literalmente"""


REFORMULATION_USER_PROMPT = """Consulta original: {query}

Motivo da reformulacao: {reason}

Reformule:"""


SUFFICIENCY_JUDGE_PROMPT = """Voce e um juiz de suficiencia de contexto.

Pergunta original: {query}

Contexto recuperado:
{context_text}

O contexto acima e suficiente para responder a pergunta de forma fundamentada e citavel?

Responda APENAS na primeira linha:
sim - se o contexto basta
nao - se falta informacao essencial

Nao explique. Nao reformule. Apenas: sim ou nao."""


_MEMORY_FIRST_BASE = """Voce e Aurora, um assistente pessoal privado.
{date_context}
O usuario esta perguntando sobre conversas anteriores. Priorize as memorias e cite a data da sessao.
Responda com base nas memorias e notas do vault fornecidas no contexto.
Cite as fontes inline:
- Memorias: [memoria: titulo da sessao]
- Notas do vault: [caminho/nota.md]
Deduplique as citacoes: cite cada fonte apenas uma vez.
Quando houver conflito entre fontes, prefira a memoria mais recente.
Se a informacao nao estiver no contexto fornecido, diga que nao encontrou evidencia suficiente.
Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente.
Nao invente informacoes nem extrapole alem do que esta nas fontes."""

SYSTEM_PROMPT_MEMORY_FIRST = _MEMORY_FIRST_BASE.replace(
    "{date_context}", ""
).strip()


def get_system_prompt_memory_first(*, date_context: str = "") -> str:
    """Return the memory-first system prompt with optional temporal date context.

    Args:
        date_context: Optional string describing current date context,
                      e.g. 'Hoje e 2026-04-03.' Injected into the prompt template.

    Returns:
        Formatted system prompt string with temporal emphasis for memory-intent turns.
    """
    return _MEMORY_FIRST_BASE.format(date_context=date_context).strip()


def build_system_prompt_with_preferences(base_prompt: str, preferences_path: Path) -> str:
    """Prepend preferences.md content to system prompt if file exists (per D-04, Pitfall 5).

    Returns base_prompt unchanged when the file doesn't exist or is empty.
    """
    if preferences_path.exists():
        prefs = preferences_path.read_text(encoding="utf-8").strip()
        if prefs:
            return f"## Preferencias do usuario\n\n{prefs}\n\n{base_prompt}"
    return base_prompt


__all__ = [
    "SYSTEM_PROMPT_GROUNDED",
    "SYSTEM_PROMPT_GROUNDED_WITH_MEMORY",
    "SYSTEM_PROMPT_CHAT",
    "SYSTEM_PROMPT_MEMORY_FIRST",
    "INTENT_PROMPT",
    "INSUFFICIENT_EVIDENCE_MSG",
    "SUMMARIZE_SESSION_PROMPT",
    "REFORMULATION_SYSTEM_PROMPT",
    "REFORMULATION_USER_PROMPT",
    "SUFFICIENCY_JUDGE_PROMPT",
    "build_system_prompt_with_preferences",
    "get_system_prompt_memory_first",
]
