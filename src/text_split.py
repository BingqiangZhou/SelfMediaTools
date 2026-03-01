from __future__ import annotations

import re
import unicodedata

END_PUNCT = {
    "\u3002",  # 。
    "\uff01",  # ！
    "\uff1f",  # ？
    "\uff1b",  # ；
    "\uff1a",  # ：
    ";",
    ":",
    "!",
    "?",
    ".",
    "\u2026",  # …
}
TRAILING_QUOTES = {
    '"',
    "'",
    ")",
    "]",
    "}",
    "\uff09",  # ）
    "\u3011",  # 】
    "\u300b",  # 》
    "\u300d",  # 」
    "\u300f",  # 』
    "\u201d",  # ”
    "\u2019",  # ’
}


def _normalize_inline_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_text_content(text: str) -> bool:
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        if category.startswith("L") or category.startswith("N"):
            return True
    return False


def _split_line(line: str) -> list[str]:
    line = _normalize_inline_whitespace(line)
    if not line:
        return []

    sentences: list[str] = []
    current: list[str] = []
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]
        current.append(ch)

        if ch in END_PUNCT:
            i += 1
            while i < n and line[i] in END_PUNCT:
                current.append(line[i])
                i += 1
            while i < n and line[i] in TRAILING_QUOTES:
                current.append(line[i])
                i += 1
            sentence = _normalize_inline_whitespace("".join(current))
            if sentence and _has_text_content(sentence):
                sentences.append(sentence)
            current = []
            continue

        i += 1

    tail = _normalize_inline_whitespace("".join(current))
    if tail and _has_text_content(tail):
        sentences.append(tail)
    return sentences


def split_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    output: list[str] = []
    for raw_line in normalized.split("\n"):
        output.extend(_split_line(raw_line))
    return output
