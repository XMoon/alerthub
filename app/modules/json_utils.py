import json
from json import JSONDecodeError
from typing import Any

_VALID_JSON_ESCAPES = {'"', "\\", "/", "b", "f", "n", "r", "t"}


def normalize_json_body(body: bytes) -> tuple[bytes, bool]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body, False

    try:
        parsed_body, repaired = _load_json_with_fallback(text)
    except JSONDecodeError:
        return body, False

    if not repaired:
        return body, False

    normalized_body = json.dumps(parsed_body, ensure_ascii=False).encode("utf-8")
    return normalized_body, normalized_body != body


def _load_json_with_fallback(text: str) -> tuple[Any, bool]:
    try:
        return json.loads(text), False
    except JSONDecodeError as exc:
        original_error = exc

    try:
        return json.loads(text, strict=False), True
    except JSONDecodeError:
        pass

    repaired_text = _repair_json_string_content(text)
    if repaired_text == text:
        raise original_error

    return json.loads(repaired_text), True


def _repair_json_string_content(text: str) -> str:
    result: list[str] = []
    in_string = False
    index = 0

    while index < len(text):
        char = text[index]

        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue

        if char == '"':
            result.append(char)
            in_string = False
            index += 1
            continue

        if char == "\\":
            if _is_valid_json_escape(text, index):
                escape_end = index + 2
                if text[index + 1] == "u":
                    escape_end = index + 6
                result.append(text[index:escape_end])
                index = escape_end
                continue

            result.append("\\\\")
            index += 1
            continue

        if char == "\n":
            result.append("\\n")
        elif char == "\r":
            result.append("\\r")
        elif char == "\t":
            result.append("\\t")
        elif ord(char) < 0x20:
            result.append(f"\\u{ord(char):04x}")
        else:
            result.append(char)

        index += 1

    return "".join(result)


def _is_valid_json_escape(text: str, index: int) -> bool:
    if index + 1 >= len(text):
        return False

    next_char = text[index + 1]
    if next_char in _VALID_JSON_ESCAPES:
        return True

    if next_char != "u" or index + 5 >= len(text):
        return False

    return all(char in "0123456789abcdefABCDEF" for char in text[index + 2:index + 6])
