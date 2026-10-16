"""Round-trip nativo con MockTransport: sin red ni activación del chat."""

import asyncio
import json
import unittest

import httpx

from app.llm import LLMRequest, Message, OpenAICompatibleProvider, ToolCall


class NativeToolRoundtripTests(unittest.TestCase):
    def transcript(self, call_id="call_1"):
        call = ToolCall(id=call_id, name="company_facts", arguments={"ticker": "SAN"})
        return [
            Message("user", "Lee los hechos de SAN"),
            Message("assistant", "", tool_calls=[call]),
            Message("tool", '{"source_id":"fact:1","data":{"price":1}}', tool_call_id=call_id),
        ]

    def test_sobre_openai_conserva_calls_resultados_y_ids(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "test-free",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Dato con fuente fact:1"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenAICompatibleProvider(
                    api_key="mock",
                    base_url="https://mock.invalid",
                    default_model="test-free",
                    client=client,
                    max_retries=0,
                )
                return await provider.complete(LLMRequest(messages=self.transcript(), cache=False))

        result = asyncio.run(run())
        self.assertEqual(result.text, "Dato con fuente fact:1")
        messages = seen[0]["messages"]
        self.assertIsNone(messages[1]["content"])
        self.assertEqual(messages[1]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(json.loads(messages[1]["tool_calls"][0]["function"]["arguments"]), {"ticker": "SAN"})
        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "call_1")
        self.assertEqual(messages[2]["content"], self.transcript()[2].content)

    def test_roles_anteriores_conservan_el_mismo_sobre(self):
        for role in ("system", "user", "assistant"):
            self.assertEqual(Message(role, "texto").to_openai(), {"role": role, "content": "texto"})

    def test_rechaza_roles_incorrectos_o_resultados_sin_id(self):
        call = ToolCall(id="c1", name="company_facts")
        invalid = [
            lambda: Message("user", "x", tool_calls=[call]),
            lambda: Message("tool", "x"),
            lambda: Message("assistant", "x", tool_call_id="c1"),
            lambda: Message("assistant", "", tool_calls=[{}]),
        ]
        for build in invalid:
            with self.assertRaises((ValueError, TypeError)):
                build()

    def test_rechaza_huerfano_resultado_repetido_o_faltante(self):
        messages = self.transcript()
        invalid = [
            [messages[0], messages[2]],
            messages + [messages[2]],
            messages[:2],
            messages[:2] + [Message("user", "otra pregunta")],
            messages + messages[1:],
        ]
        for transcript in invalid:
            with self.assertRaises(ValueError):
                LLMRequest(messages=transcript)

    def test_varias_tools_y_rondas_ids_distintos(self):
        first = ToolCall(id="a", name="company_facts")
        second = ToolCall(id="b", name="company_news")
        LLMRequest(
            messages=[
                Message("user", "Lee"),
                Message("assistant", "", tool_calls=[first, second]),
                Message("tool", "{}", tool_call_id="b"),
                Message("tool", "{}", tool_call_id="a"),
                *self.transcript("next"),
            ]
        )
        with self.assertRaises(ValueError):
            LLMRequest(messages=[Message("assistant", "", tool_calls=[first, first])])

    def test_cambio_id_cambia_payload_que_la_cache_hashea(self):
        provider = OpenAICompatibleProvider(
            api_key="mock", base_url="https://mock.invalid", default_model="test-free", max_retries=0
        )
        one = provider._build_payload(LLMRequest(messages=self.transcript("one")), "test-free")
        two = provider._build_payload(LLMRequest(messages=self.transcript("two")), "test-free")
        self.assertNotEqual(one, two)

    def test_argumentos_no_finitos_no_salen_al_proveedor(self):
        with self.assertRaises(ValueError):
            ToolCall(id="x", name="company_facts", arguments={"price": float("nan")}).to_openai()
