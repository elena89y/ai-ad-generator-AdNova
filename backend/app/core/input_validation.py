from __future__ import annotations


def contains_emoji(value: str | None) -> bool:
    """Return whether user-entered ad text contains emoji characters."""
    if not value:
        return False

    for char in value:
        codepoint = ord(char)
        if (
            0x1F000 <= codepoint <= 0x1FAFF
            or 0x2600 <= codepoint <= 0x27BF
            or codepoint in (0x200D, 0xFE0F)
        ):
            return True
    return False
