"""Paragraph chunking + slot substitution for story audio.

One audio clip = one prose paragraph ("chunk"). The pilot player
(buju_website/pilot/js/stories.js) splits segment text the same way its
renderProse() does; this module MUST mirror that split exactly, or clip
indices drift between the generated mp3s and what the player requests:

    JS:      text.split("\n") -> trim() -> skip empty
    Python:  text.split("\n") -> strip() -> skip empty

Slot substitution mirrors the site's appendWithSlots(): scan for {token}
markers with find/slice (split/join style, never regex .replace with
user-ish text), and only tokens declared in the story's slots are
substituted — anything else is left literally.

Used by generate_story_audio.py (batch mp3 generation) and by
build_pilot_site.py (stamping per-chunk audio info into stories.json).
The runtime name-audio endpoint (buju_website/api/pilot-name-audio.js)
re-implements the same two functions in JS; keep all three in sync.
"""

from __future__ import annotations

from typing import Any


def paragraph_chunks(text: str) -> list[str]:
    """Split prose into the paragraph chunks the player narrates."""
    return [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]


def declared_slot_tokens(chunk_text: str, slots: dict[str, Any]) -> list[str]:
    """The declared slot tokens ({rover_name} etc.) appearing in a chunk."""
    found: list[str] = []
    rest = chunk_text
    while True:
        open_brace = rest.find("{")
        if open_brace == -1:
            break
        close_brace = rest.find("}", open_brace)
        if close_brace == -1:
            break
        token = rest[open_brace + 1 : close_brace]
        if token in slots and token not in found:
            found.append(token)
        rest = rest[close_brace + 1 :]
    return found


def substitute_slot_values(
    chunk_text: str, slots: dict[str, Any], slot_values: dict[str, str]
) -> str:
    """Replace declared {token} markers with chosen values (or the slot's
    default). Undeclared {…} sequences are kept literally, matching the
    player's appendWithSlots()."""
    pieces: list[str] = []
    rest = chunk_text
    while True:
        open_brace = rest.find("{")
        if open_brace == -1:
            break
        close_brace = rest.find("}", open_brace)
        if close_brace == -1:
            break
        token = rest[open_brace + 1 : close_brace]
        if token not in slots:
            pieces.append(rest[: close_brace + 1])
            rest = rest[close_brace + 1 :]
            continue
        pieces.append(rest[:open_brace])
        value = slot_values.get(token) or slots[token]["default"]
        pieces.append(value)
        rest = rest[close_brace + 1 :]
    pieces.append(rest)
    return "".join(pieces)
