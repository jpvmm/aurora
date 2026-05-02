"""Phase 7 latency bench: iterative vs single-shot per query.

NOT a CI test. Runs against real local llama.cpp + vault — latency assertions
are flaky in CI per Phase 7 RESEARCH §9. Run manually after model swaps or
significant retrieval changes.

Usage:
    python scripts/bench_iterative_retrieval.py

Output:
    Per-query line:
        <query>  single= XXXms  iter= YYYms  ratio=Z.ZZ  attempts=N  WITHIN BUDGET

    Summary lines:
        happy-path p50=X.XX p95=Y.YY (target {_HAPPY_TARGET})  -> WITHIN BUDGET
        worst-case p50=X.XX p95=Y.YY (target {_WORST_TARGET})  -> WITHIN BUDGET

Verdict is informational. Process exits 0 regardless of WITHIN/OVER BUDGET so
this script can be run from a wrapper without gating CI on flaky timing.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from aurora.llm.service import LLMService
from aurora.memory.store import MEMORY_COLLECTION, MEMORY_INDEX
from aurora.retrieval.iterative import IterativeRetrievalOrchestrator
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.retrieval.service import RetrievalService
from aurora.runtime.settings import RuntimeSettings

_HAPPY_TARGET = 1.0  # single-shot baseline ratio (no overhead)
_WORST_TARGET = 2.5  # worst-case loop overhead ratio (one full reformulation)

_QUERIES = [
    "o que escrevi sobre produtividade",
    "notas sobre Python ontem",
    "Rosely",
    "como organizei minha semana",
    "o que pensei sobre o livro de marco",
    "quando comecei o projeto Aurora",
    "diario de janeiro",
    "ideias sobre escrita",
]


@dataclass
class _Sample:
    query: str
    single_ms: float
    iter_ms: float
    ratio: float
    n_attempts: int

    @property
    def verdict(self) -> str:
        target = _WORST_TARGET if self.n_attempts > 1 else _HAPPY_TARGET
        return "WITHIN BUDGET" if self.ratio <= target else "OVER BUDGET"


def _enabled_settings() -> RuntimeSettings:
    return RuntimeSettings(iterative_retrieval_enabled=True)


def _disabled_settings() -> RuntimeSettings:
    return RuntimeSettings(iterative_retrieval_enabled=False)


def _bench_one(query: str) -> _Sample:
    """Time disabled vs enabled mode for a single query, return ratio + attempts."""
    backend = QMDSearchBackend()
    memory_backend = QMDSearchBackend(
        index_name=MEMORY_INDEX,
        collection_name=MEMORY_COLLECTION,
    )
    retrieval = RetrievalService(
        search_backend=backend, memory_backend=memory_backend,
    )
    llm = LLMService()

    def _retrieve_fn(q, *, search_strategy, search_terms):
        return retrieval.retrieve_with_memory(
            q, search_strategy=search_strategy, search_terms=search_terms,
        )

    # Single-shot baseline: orchestrator in disabled mode = 1 attempt, no LLM rescue
    orch_disabled = IterativeRetrievalOrchestrator(
        llm=llm, settings_loader=_disabled_settings,
    )
    t0 = time.perf_counter()
    _, _ = orch_disabled.run(
        query, intent="vault",
        retrieve_fn=_retrieve_fn,
        search_strategy="hybrid", search_terms=[],
    )
    single_ms = (time.perf_counter() - t0) * 1000.0

    # Iterative: real LLM may fire reformulation if attempt 1 thin
    orch_enabled = IterativeRetrievalOrchestrator(
        llm=llm, settings_loader=_enabled_settings,
    )
    t0 = time.perf_counter()
    _, trace = orch_enabled.run(
        query, intent="vault",
        retrieve_fn=_retrieve_fn,
        search_strategy="hybrid", search_terms=[],
    )
    iter_ms = (time.perf_counter() - t0) * 1000.0

    ratio = iter_ms / single_ms if single_ms > 0 else float("inf")
    return _Sample(
        query=query, single_ms=single_ms, iter_ms=iter_ms,
        ratio=ratio, n_attempts=len(trace.attempts),
    )


def _pct(values: list[float], q: float) -> float:
    """Estimate the q-quantile (q in [0,1]) using statistics.quantiles."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100)[int(q * 100) - 1]


def main() -> int:
    samples: list[_Sample] = []
    for q in _QUERIES:
        s = _bench_one(q)
        samples.append(s)
        print(
            f"{s.query[:42]:42s}  "
            f"single={s.single_ms:6.0f}ms  iter={s.iter_ms:6.0f}ms  "
            f"ratio={s.ratio:.2f}  attempts={s.n_attempts}  {s.verdict}"
        )

    happy = [s for s in samples if s.n_attempts == 1]
    worst = [s for s in samples if s.n_attempts > 1]

    if happy:
        h_p50 = statistics.median([s.ratio for s in happy])
        h_p95 = _pct([s.ratio for s in happy], 0.95)
        h_verdict = "WITHIN BUDGET" if h_p95 <= _HAPPY_TARGET else "OVER BUDGET"
        print(
            f"happy-path p50={h_p50:.2f} p95={h_p95:.2f} "
            f"(target {_HAPPY_TARGET})  -> {h_verdict}"
        )
    if worst:
        w_p50 = statistics.median([s.ratio for s in worst])
        w_p95 = _pct([s.ratio for s in worst], 0.95)
        w_verdict = "WITHIN BUDGET" if w_p95 <= _WORST_TARGET else "OVER BUDGET"
        print(
            f"worst-case p50={w_p50:.2f} p95={w_p95:.2f} "
            f"(target {_WORST_TARGET})  -> {w_verdict}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
