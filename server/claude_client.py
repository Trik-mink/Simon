from __future__ import annotations

import asyncio
import base64
import json
import re

import anthropic

MODEL = "claude-haiku-4-5"
FALLBACK = {
    "emotion": "sad",
    "guidance": "I couldn't see the desk clearly.",
    "answer": "I couldn't see the desk clearly. Could you move the camera so I can see better?",
    "position": None,
}

_client = anthropic.AsyncAnthropic()

_history: list[dict] = []
_MAX_HISTORY = 12  # 6 user+assistant pairs
_history_lock = asyncio.Lock()


MARKER_DESCRIPTIONS = {
    "study": "The user is working on a worksheet or study notes.",
    "electronics": "The user is working on an electronics/breadboard project.",
    "tabletop": "The user is playing a tabletop game.",
}


def _build_prompt(
    question: str | None,
    marker_context: str | None = None,
    has_history: bool = False,
    want_position: bool = False,
) -> str:
    context_line = ""
    if marker_context and marker_context in MARKER_DESCRIPTIONS:
        context_line = f"CONTEXT: {MARKER_DESCRIPTIONS[marker_context]}\n\n"

    position_field = ',\n  "position": {"x": <0.0-1.0>, "y": <0.0-1.0>}' if want_position else ''
    position_note = (
        '\nposition: normalized x,y of the single spot on the desk your answer refers to '
        '(0,0 = top-left, 1,1 = bottom-right of the image), or null if there is no specific spot.'
    ) if want_position else ''

    rules = (
        'YOUR JOB:\n'
        '- Focus on actual content: handwriting, printed questions, books, notes, diagrams, components.\n'
        '- If you see a question written or printed on paper — ANSWER IT. Do not ask for '
        'clarification if you can already read the question.\n'
        '- Only reference what you can actually see. Never invent steps or pages.\n\n'
        'Respond ONLY with a single JSON object — no markdown, no explanation:\n'
        '{\n'
        '  "emotion": "<dance|thinking|study|nonchalant|sad>",\n'
        '  "guidance": "<one-line summary, max 100 chars>",\n'
        '  "answer": "<direct answer to the visible question or content>"'
        + position_field + '\n'
        '}\n\n'
        'emotion: "study" for schoolwork; "nonchalant" if desk is empty; '
        '"sad" if too unclear; "dance" as default.'
        + position_note
    )
    history_note = (
        '\n\nNOTE: You have already seen this desk earlier this session. '
        'Skip anything you have already answered. Only address new or unanswered content.'
    ) if has_history else ''

    if question:
        return (
            context_line
            + f'The user is asking: "{question}"\n\n'
            'Look at this desk image and answer their question using only what you can see. '
            'Give a direct, accurate answer. If you need more information, ask for it.\n\n'
            + rules
            + history_note
        )
    return (
        context_line
        + 'Look at this desk image. Identify what the person is working on and give '
        'specific, accurate help based only on what is visible.\n\n'
        + rules
        + history_note
    )


def _parse_response(text: str) -> dict:
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        raw = match.group(0) if match else text
        data = json.loads(raw)
        guidance = str(data.get("guidance", ""))[:100]
        answer = str(data.get("answer", guidance))
        return {
            "emotion": data.get("emotion", "dance"),
            "guidance": guidance,
            "answer": answer,
            "position": _clean_position(data.get("position")),
        }
    except Exception:
        return FALLBACK.copy()


def _clean_position(position) -> dict | None:
    if position is None:
        return None
    try:
        x = float(position["x"])
        y = float(position["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "x": max(0.0, min(1.0, x)),
        "y": max(0.0, min(1.0, y)),
    }


def reset_history() -> None:
    _history.clear()


_IMAGE_PLACEHOLDER = {"type": "text", "text": "[earlier desk photo omitted]"}


def _strip_images(message: dict) -> dict:
    """Replace image blocks in a user message with a text placeholder.

    Older desk photos add huge base64 payloads (and token cost) to every API
    call while contributing almost nothing — the text history carries the
    memory. Only the newest message keeps its image.
    """
    content = message.get("content")
    if not isinstance(content, list):
        return message
    if not any(block.get("type") == "image" for block in content):
        return message
    return {
        **message,
        "content": [
            _IMAGE_PLACEHOLDER if block.get("type") == "image" else block
            for block in content
        ],
    }


async def analyze_desk(
    jpeg_bytes: bytes,
    question: str | None = None,
    marker_context: str | None = None,
    want_position: bool = False,
) -> dict:
    image_data = base64.standard_b64encode(jpeg_bytes).decode("utf-8")

    async with _history_lock:
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                },
                {
                    "type": "text",
                    "text": _build_prompt(
                        question,
                        marker_context,
                        has_history=len(_history) > 0,
                        want_position=want_position,
                    ),
                },
            ],
        }

        _history[:] = [_strip_images(m) for m in _history]
        _history.append(user_message)
        if len(_history) > _MAX_HISTORY:
            _history[:] = _history[-_MAX_HISTORY:]

        response = await _client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=list(_history),  # snapshot so the mock captures the call-time list
        )

        text = response.content[0].text
        _history.append({"role": "assistant", "content": text})
        if len(_history) > _MAX_HISTORY:
            _history[:] = _history[-_MAX_HISTORY:]
        return _parse_response(text)
