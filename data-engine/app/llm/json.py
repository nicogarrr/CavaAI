from __future__ import annotations

import json
import re
from typing import Any

from app.llm.errors import StructuredOutputError


_FENCED_BLOCK = re.compile(r"```[^\r\n]*\r?\n?(.*?)```", re.DOTALL)


def parse_json_response(text: str) -> Any:
    """Parse JSON returned directly, in a code fence, or surrounded by prose."""
    if not isinstance(text, str) or not text.strip():
        raise StructuredOutputError("The model returned an empty structured response")

    stripped = text.strip()
    candidates = [stripped]
    candidates.extend(match.group(1).strip() for match in _FENCED_BLOCK.finditer(stripped))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return value

    raise StructuredOutputError("The model response did not contain valid JSON")
