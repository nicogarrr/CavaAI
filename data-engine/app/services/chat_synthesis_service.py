"""LLM synthesis layered on top of the deterministic chat context contract."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.llm import LLMRequest, Message, ResponseFormat, parse_json_response
from app.llm.base import LLMProvider
from app.schemas import ChatResponse, SynthesisSection
from app.services.budget import BudgetController, BudgetExceededError
from app.services.langfuse_client import LangfuseTracer
from app.services.llm_output_guard import _english_hits, complete_guarded
from app.services.prompt_registry import get_prompt

PROMPT_VERSION = get_prompt("chat_source_synthesis", allow_remote=False).version
SECTION_ORDER = (
    "facts",
    "calculations",
    "user_hypotheses",
    "unverified_claims",
    "inferences",
    "contradictions",
    "insufficient_data",
    "conclusion",
)
SECTION_LABELS = {
    "facts": "HECHO",
    "calculations": "CALCULO",
    "user_hypotheses": "HIPOTESIS / MEMORIA DEL USUARIO",
    "unverified_claims": "AFIRMACION SIN VERIFICAR",
    "inferences": "INFERENCIA",
    "contradictions": "CONTRADICCIONES",
    "insufficient_data": "DATOS INSUFICIENTES",
    "conclusion": "CONCLUSION",
}
# Confidence ceiling when the answer is not backed by sourced facts.
MAX_CONFIDENCE_WITHOUT_FACTS = 0.35
# Phrases a model uses to say "I found nothing", in the languages the prompt
# asks for. Matched against the FACT section only, which is the section that is
# supposed to carry the numbers.
_NO_DATA_PHRASES = (
    "no se han encontrado",
    "no se ha encontrado",
    "no encontramos",
    "no hay datos",
    "no existen datos",
    "insufficient data",
    "no data available",
    "not enough data",
    "no financial data",
    "sin datos",
    "no consta",
    "no hay informacion",
    "no hay información",
)
_FACT_BULLET = re.compile(r"(?m)^\s*(?:[-*\u2022]|\d+[.)])\s+\S")


def _section_is_empty(section: SynthesisSection | None) -> bool:
    if section is None:
        return True
    return not (section.body or "").strip()


def _section_states_no_data(section: SynthesisSection | None) -> bool:
    """True when the FACT section says, in effect, "I found nothing".

    A section that contains the phrase AND still lists items is reporting
    partial data, not none, so it does not count.
    """
    if section is None:
        return True
    body = (section.body or "").strip().lower()
    if not body:
        return True
    if not any(phrase in body for phrase in _NO_DATA_PHRASES):
        return False
    return not _FACT_BULLET.search(body)


# Sections that must rest on retrieved evidence. The five-way classification
# only holds if a FACT cannot be a user hypothesis and a CONCLUSION cannot be
# a memory item.
GROUNDED_SECTIONS = frozenset({"facts", "calculations", "inferences", "conclusion"})
# Source types each grounded section may legitimately rest on.
SECTION_SOURCE_TYPES: dict[str, set[str]] = {
    "facts": {"financial_fact", "document_chunk", "claim_evidence", "market_price"},
    "calculations": {"financial_fact", "document_chunk", "claim_evidence", "market_price"},
    "inferences": {
        "financial_fact",
        "document_chunk",
        "claim_evidence",
        "thesis_version",
        "rag_chunk",
        "knowledge_chunk",
        "memory_item",
        "memory_writeback",
    },
    "conclusion": {
        "financial_fact",
        "document_chunk",
        "claim_evidence",
        "claim",
        "news_event",
        "thesis_version",
        "memory_item",
        "memory_writeback",
    },
}
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sections": {
            "type": "array",
            "minItems": 8,
                        "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string", "enum": list(SECTION_ORDER)},
                    "body": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "body", "citations"],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "insufficient_data": {"type": "boolean"},
    },
    "required": ["sections", "confidence", "insufficient_data"],
}



_CURRENCY_WORDS = r"(?:USD|EUR|dólares?|dolares?|euros?)"
_MONEY_RE = re.compile(
    rf"(?:([$€]|{_CURRENCY_WORDS})\s*([-+−]?)(\d[\d.,]*)|([-+−]?)(\d[\d.,]*)\s*([$€]|{_CURRENCY_WORDS}))",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d[\d.,]*)\s*%")
_FINANCIAL_HINT_RE = re.compile(
    r"(?i)\b(rentabilidad|beneficio|dividendo|margen|crecimiento|cotiza(?:ción|do)?|"
    r"precio|sube|subida|baja|caída|cae|earnings|valoración|PER|market cap)\b"
)
_CURRENCY_MAP = {
    "$": "USD",
    "usd": "USD",
    "dólar": "USD",
    "dólares": "USD",
    "dolar": "USD",
    "dolares": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
}


def _parse_amount(raw: str) -> Decimal | None:
    """Decimal exacto con convencion explicita: NUNCA se quita el punto decimal.

    1999 != 19.99 y 35 != 3.5 (ronda 3 auditor: quitar separadores igualaba
    cifras 100x distintas). Con dos separadores, el ultimo es el decimal;
    con uno solo, tres digitos detras en TODOS los grupos = miles europeos,
    si no, decimal.
    """
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


_MONEY_FACT_TYPES = {"market_price", "financial_fact"}


def _money_pairs(text: str) -> set[tuple[Decimal, str]]:
    """Pares (importe CON SIGNO, divisa): -1999 nunca valida contra +1999."""
    pairs: set[tuple[Decimal, str]] = set()
    for match in _MONEY_RE.finditer(text):
        currency_raw = match.group(1) or match.group(6) or ""
        sign_raw = match.group(2) or match.group(4) or ""
        amount_raw = match.group(3) or match.group(5) or ""
        currency = _CURRENCY_MAP.get(currency_raw.lower())
        amount = _parse_amount(amount_raw)
        if currency and amount is not None:
            if sign_raw in ("-", "−"):
                amount = -amount
            pairs.add((amount, currency))
    return pairs


def _source_money_pairs(source: dict) -> set[tuple[Decimal, str]]:
    """Pares de UNA fuente: la cifra debe vivir en una sola fuente admisible
    (titulo + precio), no reconstruirse mezclando fuentes distintas."""
    return _money_pairs(f"{source.get('title', '')} {source.get('price', '')}")


_PERCENT_RE_SIGNED = re.compile(r"([-+−]?)(\d[\d.,]*)\s*%")


def _percents(text: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for m in _PERCENT_RE_SIGNED.finditer(text):
        amount = _parse_amount(m.group(2))
        if amount is not None:
            if m.group(1) in ("-", "−"):
                amount = -amount
            out.add(amount)
    return out


def _source_percents(source: dict) -> set[Decimal]:
    return _percents(f"{source.get('title', '')} {source.get('price', '')}")


_TICKER_RE = re.compile(r"\b[A-Z]{2,6}\b")
_TICKER_WHITELIST = {
    "USD", "EUR", "GBP", "JPY", "CHF", "OK", "PER", "CEO", "CFO", "IPO",
    "ETF", "AI", "IT", "RAG", "LLM", "API", "GDP", "CPI", "YOY", "QOQ",
}


def _source_tickers(sources: list[dict]) -> set[str]:
    """Tickers de las fuentes admisibles (primer token ALLCAPS del titulo)."""
    tickers: set[str] = set()
    for source in sources:
        match = _TICKER_RE.search(str(source.get("title", "")))
        if match:
            tickers.add(match.group(0))
    return tickers


class ChatSynthesisService:
    def __init__(self, provider: LLMProvider, tracer: LangfuseTracer | None = None) -> None:
        self.provider = provider
        self.tracer = tracer or LangfuseTracer()

    async def synthesize(
        self,
        *,
        question: str,
        ticker: str | None,
        baseline: ChatResponse,
        db: Session | None = None,
        enable_debate: bool | None = None,
    ) -> ChatResponse:
        retrieval_ids = [
            f"{source.get('type')}:{source.get('id')}"
            for source in baseline.sources
            if source.get("id") is not None
        ]
        trace_seed = {
            "workflow": "chat_source_aware_synthesis",
            "prompt_version": PROMPT_VERSION,
            "retrieval_set": retrieval_ids,
            "tools": [],
            "fallback": False,
            "escalation": False,
            "escalation_reason": "premium escalation requires a passing evaluation gate",
        }
        with self.tracer.workflow("ChatSourceAwareSynthesis", trace_seed) as trace:
            try:
                budget = BudgetController()
                if db is not None and not budget.can_spend(db, 0.02):
                    raise BudgetExceededError("LLM budget exhausted")
                request = LLMRequest(
                    messages=[
                        Message(
                            "system",
                            get_prompt("chat_source_synthesis").text,
                        ),
                        Message(
                            "user",
                            json.dumps(
                                {
                                    "question": question,
                                    "ticker": ticker,
                                    "allowed_source_ids": retrieval_ids,
                                    "deterministic_sections": [
                                        section.model_dump() for section in baseline.sections
                                    ],
                                    "retrieved_sources": baseline.sources[:40],
                                },
                                default=str,
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                    task="main_financial_analysis",
                    temperature=0.1,
                    max_tokens=1800,
                    response_format=ResponseFormat.json_schema(
                        RESPONSE_SCHEMA,
                        name="source_aware_chat",
                        strict=True,
                    ),
                    metadata={
                        "prompt_version": PROMPT_VERSION,
                        **get_prompt("chat_source_synthesis").trace_metadata(),
                    },
                )
                spent = {"cost": 0.0}

                def _record(resp: Any) -> None:
                    # CADA respuesta del proveedor consume presupuesto, tambien
                    # la que el validador descarta.
                    resp_cost = budget.estimate_cost_eur(
                        resp.model,
                        resp.usage.input_tokens,
                        resp.usage.output_tokens,
                    )
                    spent["cost"] += resp_cost
                    if db is not None:
                        budget.record(
                            db,
                            resp.model,
                            "chat_source_aware_synthesis",
                            resp_cost,
                            resp.usage.total_tokens,
                        )

                def _can_retry() -> None:
                    if db is not None and not budget.can_spend(db, 0.02):
                        raise BudgetExceededError("LLM budget exhausted")

                guarded = await complete_guarded(
                    self.provider,
                    request,
                    source="chat_synthesis",
                    on_response=_record,
                    before_retry=_can_retry,
                )
                response = guarded.response
                cost = spent["cost"]
                payload = parse_json_response(response.text)
                sections = self._verified_sections(payload, baseline, set(retrieval_ids))
                declared_confidence = max(0.0, min(1.0, float(payload["confidence"])))
                declared_insufficient = bool(payload["insufficient_data"])
                has_financial_facts = any(
                    source.get("type") == "financial_fact" for source in baseline.sources
                )
                # `insufficient_data` is a SAFETY state, so it is re-derived
                # from the verified output instead of taken from the model. The
                # model could otherwise declare sufficiency with confidence
                # 0.99 while its own FACT section read "no se han encontrado
                # datos financieros suficientes", and that combination was
                # accepted verbatim: the clamp only looked at the CONTEXT, never
                # at what the model actually produced.
                produced_nothing = _section_is_empty(
                    next((s for s in sections if s.key == "facts"), None)
                )
                states_no_data = _section_states_no_data(
                    next((s for s in sections if s.key == "facts"), None)
                )
                insufficient = (
                    declared_insufficient
                    or not has_financial_facts
                    or produced_nothing
                    or states_no_data
                )
                confidence = declared_confidence
                if insufficient:
                    # No evidence, or the model itself said there is none: a
                    # confident answer would be the most misleading output the
                    # system can produce.
                    confidence = min(confidence, MAX_CONFIDENCE_WITHOUT_FACTS)

                baseline.sections = sections
                baseline.answer = self._render(sections)
                baseline.prompt_version = PROMPT_VERSION
                baseline.model = response.model
                baseline.confidence = confidence
                baseline.insufficient_data = insufficient
                baseline.llm_trace = {
                    **trace.metadata,
                    "model": response.model,
                    "provider": response.provider,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_read_tokens": response.usage.cache_read_tokens,
                    "cache_write_tokens": response.usage.cache_write_tokens,
                    "cost": cost,
                    "citations": sum(len(section.citations) for section in sections),
                    "citation_verification": True,
                    "json_validity": True,
                    "evaluation_score": confidence,
                    "request_id": response.request_id,
                }
                trace.update(**baseline.llm_trace)
                trace.output = {
                    "confidence": confidence,
                    "insufficient_data": insufficient,
                    "citation_verification": True,
                }
                await self._maybe_attach_debate(baseline, ticker, enable_debate)
                return baseline
            except Exception as exc:
                # The deterministic response is the safe product contract and fallback.
                baseline.model = "deterministic"
                baseline.confidence = self._baseline_confidence(baseline)
                baseline.insufficient_data = baseline.confidence < 0.5
                baseline.llm_trace = {
                    **trace.metadata,
                    "model": "deterministic",
                    "provider": getattr(self.provider, "name", "unknown"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "cost": None,
                    "citations": sum(len(section.citations) for section in baseline.sections),
                    "citation_verification": False,
                    "json_validity": not isinstance(exc, (ValueError, ValidationError)),
                    "fallback": True,
                    "fallback_reason": type(exc).__name__,
                    "evaluation_score": baseline.confidence,
                }
                trace.update(**baseline.llm_trace)
                trace.output = {"fallback": True, "reason": type(exc).__name__}
                return baseline

    async def synthesize_general(
        self,
        *,
        question: str,
        baseline: ChatResponse,
        db: Session | None = None,
    ) -> ChatResponse:
        """Respuesta natural en espanol para preguntas sin ticker.

        El contrato estructurado (HECHO/CALCULO/...) es para respuestas de
        datos; una pregunta general merece prosa natural con citas cuando
        use las fuentes recuperadas.
        """
        budget = BudgetController()
        # Mismo control de presupuesto que la ruta estructurada: sin saldo
        # NO hay primera llamada (antes solo se comprobaba el reintento).
        if db is not None and not budget.can_spend(db, 0.02):
            return self._general_fallback(baseline, reason="budget_exhausted")
        request = LLMRequest(
            messages=[
                Message("system", get_prompt("chat_general").text),
                Message(
                    "user",
                    json.dumps(
                        {
                            "question": question,
                            "retrieved_sources": baseline.sources[:40],
                        },
                        default=str,
                        ensure_ascii=False,
                    ),
                ),
            ],
            task="chat",
            temperature=0.3,
            max_tokens=600,
        )
        spent = {"cost": 0.0}

        def _record(resp: Any) -> None:
            # CADA respuesta consume presupuesto y se registra en DB como en
            # la ruta estructurada, tambien la descartada por el guard.
            resp_cost = budget.estimate_cost_eur(
                getattr(resp, "model", None) or "unknown",
                resp.usage.input_tokens,
                resp.usage.output_tokens,
            )
            spent["cost"] += resp_cost
            if db is not None:
                budget.record(
                    db,
                    getattr(resp, "model", None) or "unknown",
                    "chat_general",
                    resp_cost,
                    resp.usage.total_tokens,
                )

        def _can_retry() -> None:
            if db is not None and not budget.can_spend(db, 0.02):
                raise BudgetExceededError("LLM budget exhausted")

        try:
            guarded = await complete_guarded(
                self.provider,
                request,
                source="chat_general",
                english="strict",
                on_response=_record,
                before_retry=_can_retry,
            )
        except Exception:  # proveedor caido, guard agotado o presupuesto: fallback honesto
            return self._general_fallback(baseline, reason="provider_or_guard_failure")
        text = (guarded.response.text or "").strip()
        if not text or not self._general_text_grounded(text, baseline):
            return self._general_fallback(baseline, reason="ungrounded")
        return ChatResponse(
            answer=text,
            sources=baseline.sources,
            proposed_actions=baseline.proposed_actions,
            model=getattr(self.provider, "name", "unknown"),
            prompt_version="chat-general-v1",
            confidence=0.35 if baseline.sources else 0.2,
            llm_trace={"path": "general", "cost": spent["cost"]},
        )

    @staticmethod
    def _general_fallback(baseline: ChatResponse, *, reason: str) -> ChatResponse:
        """Degradado honesto en espanol: nunca texto crudo del proveedor."""
        return ChatResponse(
            answer=(
                "No puedo responderte con fuentes ahora mismo; "
                "prueba de nuevo en un momento o dame un ticker para ir a datos concretos."
            ),
            sources=baseline.sources,
            proposed_actions=baseline.proposed_actions,
            model="fallback",
            prompt_version="chat-general-v1",
            confidence=0.2,
            llm_trace={"path": "general", "fallback": True, "reason": reason},
        )

    @staticmethod
    def _general_text_grounded(text: str, baseline: ChatResponse) -> bool:
        """El texto libre no puede inventar citas ni cifras financieras.

        - Citas [tipo:id] ⊆ fuentes recuperadas.
        - Toda cifra con divisa debe coincidir como par (Decimal exacto,
          divisa) con UNA sola fuente admisible: nunca substring, nunca
          19.99 contra 1999, nunca otra divisa.
        - Vinculo compania/cita: una afirmacion financiera exige al menos
          una cita valida, y un ticker junto a la cifra que no este en las
          fuentes (MSFT con fuente ASTS) invalida el texto.
        - Los porcentajes solo se exigen en contexto financiero
          (rentabilidad, cotiza, ...) y deben existir en una fuente.
        """
        allowed = {
            f"{source.get('type')}:{source.get('id')}"
            for source in baseline.sources
            if source.get("id") is not None
        }
        citations = list(re.finditer(r"\[([a-z_]+):([^\]]+)\]", text))
        for match in citations:
            if f"{match.group(1)}:{match.group(2)}" not in allowed:
                return False
        # Ingles OFF tambien en la ruta general: el umbral del guard
        # estructural (4 hits) deja pasar frases cortas; aqui basta un par
        # de marcadores funcionales ingleses para que no sea publicable.
        hits, total = _english_hits(text)
        if hits >= 2 and hits / max(total, 1) >= 0.15:
            return False
        financial_hint = bool(_FINANCIAL_HINT_RE.search(text))
        by_id = {
            f"{source.get('type')}:{source.get('id')}": source
            for source in baseline.sources
            if source.get("id") is not None
        }
        # Validacion POR AFIRMACION (segmento): la MISMA cita debe contener
        # compania + importe con signo + divisa/metrica. Nada de uniones de
        # fuentes: MSFT no se valida con la cifra de ASTS ni con una nota de
        # memoria (tipo no factual no respalda cotizaciones).
        for segment in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(])|\n", text):
            seg_money = _money_pairs(segment)
            seg_percents = _percents(segment) if financial_hint else set()
            if not seg_money and not seg_percents:
                continue
            seg_citations = [
                by_id[f"{m.group(1)}:{m.group(2)}"]
                for m in re.finditer(r"\[([a-z_]+):([^\]]+)\]", segment)
                if f"{m.group(1)}:{m.group(2)}" in by_id
            ]
            if not seg_citations:
                return False
            seg_tickers = [
                t.upper()
                for t in _TICKER_RE.findall(segment)
                if t.upper() not in _TICKER_WHITELIST
            ]

            def _backs(source: dict) -> bool:
                if source.get("type") not in _MONEY_FACT_TYPES:
                    return False
                title_upper = str(source.get("title", "")).upper()
                if any(t not in title_upper for t in seg_tickers):
                    return False
                if seg_money - _source_money_pairs(source):
                    return False
                return not (seg_percents - _source_percents(source))

            if not any(_backs(source) for source in seg_citations):
                return False
        return True

    @staticmethod
    def _verified_sections(
        payload: Any,
        baseline: ChatResponse,
        allowed: set[str],
    ) -> list[SynthesisSection]:
        if not isinstance(payload, dict) or not isinstance(payload.get("sections"), list):
            raise ValueError("Invalid synthesis envelope")
        parsed = [SynthesisSection.model_validate(item) for item in payload["sections"]]
        by_key = {section.key: section for section in parsed}
        if set(by_key) != set(SECTION_ORDER) or len(parsed) != len(SECTION_ORDER):
            raise ValueError("Synthesis must contain each contract section exactly once")
        baseline_by_key = {section.key: section for section in baseline.sections}
        for section in parsed:
            if any(citation not in allowed for citation in section.citations):
                raise ValueError("Unsupported citation returned by model")
            if section.key not in GROUNDED_SECTIONS:
                continue
            baseline_section = baseline_by_key.get(section.key)
            if not baseline_section or not baseline_section.citations:
                continue
            if not section.citations:
                raise ValueError("Grounded section omitted required citations")
            # A citation must be BOTH in the global allowed set AND in the
            # baseline set of ITS OWN section. Checking only the global set let
            # a `memory_item:*` citation render a user's own hypothesis under the
            # FACT heading with citation_verification: true, which is exactly
            # the five-way classification (fact / calculation / user assumption
            # / inference / unverified) the product sells.
            baseline_citations = set(baseline_section.citations)
            outside = [c for c in section.citations if c not in baseline_citations]
            if outside:
                raise ValueError(
                    f"Citation not sourced from this section's baseline: {outside}"
                )
            # And the source TYPE has to be one a section may legitimately
            # rest on, so a memory or a news item can never pose as a fact.
            for citation in section.citations:
                source_type = citation.split(":", 1)[0]
                permitted = SECTION_SOURCE_TYPES.get(section.key, set())
                if permitted and source_type not in permitted:
                    raise ValueError(
                        f"Citation type {source_type!r} is not permitted in section "
                        f"{section.key!r}"
                    )
        return [by_key[key] for key in SECTION_ORDER]

    @staticmethod
    def _render(sections: list[SynthesisSection]) -> str:
        return "\n\n".join(
            f"{SECTION_LABELS[section.key]}\n{section.body}" for section in sections
        )

    @staticmethod
    def _baseline_confidence(baseline: ChatResponse) -> float:
        facts = sum(source.get("type") == "financial_fact" for source in baseline.sources)
        primary = sum(
            source.get("type") in {"document_chunk", "claim_evidence"}
            for source in baseline.sources
        )
        return min(0.75, 0.20 + facts * 0.06 + primary * 0.04)

    @staticmethod
    def _debate_enabled(enable_debate: bool | None) -> bool:
        if enable_debate is not None:
            return enable_debate
        return os.getenv("CAVA_THESIS_DEBATE_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    async def _maybe_attach_debate(
        self,
        baseline: ChatResponse,
        ticker: str | None,
        enable_debate: bool | None,
    ) -> None:
        """Enganche opcional del debate bull/bear. Nunca rompe el flujo."""
        if not ticker or not self._debate_enabled(enable_debate):
            return
        try:
            from app.services.jev_gates import (
                DEBATE_WORTHWHILE_CRITERIA,
                DEBATE_WORTHWHILE_INSTRUCTIONS,
                DEBATE_WORTHWHILE_THRESHOLD,
                jev_choice_or_none,
            )

            gate = await jev_choice_or_none(
                name="debate_worthwhile",
                text=baseline.answer,
                instructions=DEBATE_WORTHWHILE_INSTRUCTIONS,
                criteria=DEBATE_WORTHWHILE_CRITERIA,
            )
            if (
                gate is not None
                and gate.label == "clear_cut"
                and gate.confidence >= DEBATE_WORTHWHILE_THRESHOLD
            ):
                baseline.llm_trace["thesis_debate"] = {
                    "skipped": True,
                    "reason": "jev_clear_cut",
                    "jev_gate": {
                        "label": gate.label,
                        "confidence": gate.confidence,
                    },
                }
                return
        except Exception:
            pass
        try:
            from app.services.thesis_debate_service import debate_thesis

            baseline.llm_trace["thesis_debate"] = await debate_thesis(
                ticker, baseline.answer, provider=self.provider,
                skip_jev_gate=True,
            )
        except Exception:
            pass
