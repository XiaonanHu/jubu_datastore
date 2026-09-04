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
re-implements the same functions in JS; keep all of them in sync.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------
# Sentence pacing
# ---------------------------------------------------------------------
# Sonic-3 reads a paragraph without much of a beat between sentences, which
# is too brisk for a bedtime read-aloud, so we insert SSML break tags at
# sentence boundaries (docs: build-with-cartesia/sonic-3/ssml-tags).
# Cartesia warns that break tags segment generation and that several in
# quick succession can make the model hallucinate — hence one per boundary
# at most, and never after a very short exclamation.
SENTENCE_FINAL = ".!?…"
SENTENCE_CLOSERS = "\"'”’)»"
SENTENCE_OPENERS = "\"'“‘(«—"
# Don't mistake "Mr. Whiskers" for a sentence boundary.
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "prof", "sgt", "mt", "vs"}
# Skip the pause after very short sentences ("Beep." / "Yes.") so a burst of
# them can't stack up break tags.
MIN_SENTENCE_CHARS_FOR_PAUSE = 10


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


def _is_abbreviation(text: str, terminal_index: int) -> bool:
    """True when the '.' at terminal_index closes a known abbreviation."""
    start = terminal_index
    while start > 0 and (text[start - 1].isalpha() or text[start - 1] == "."):
        start -= 1
    word = text[start:terminal_index].replace(".", "").lower()
    return word in ABBREVIATIONS


def _opens_sentence(char: str) -> bool:
    return char.isupper() or char in SENTENCE_OPENERS


def to_transcript(
    chunk_text: str,
    sentence_pause_ms: int,
    short_sentence_chars: int = 0,
    short_sentence_pause_ms: int | None = None,
) -> str:
    """The text actually sent to Cartesia: prose with a <break/> at each
    sentence boundary so the narrator takes a breath mid-paragraph.

    Short-sentence rule (off unless short_sentence_chars > 0): a sentence
    shorter than short_sentence_chars is followed by short_sentence_pause_ms
    instead of sentence_pause_ms. Stories for the youngest bands are written
    in bursts ("No orange. Only red. Only yellow.") and a full-length pause
    after every burst reads as staccato; a shorter beat keeps the rhythm.
    Sentences under MIN_SENTENCE_CHARS_FOR_PAUSE still get no pause at all.

    Boundary rule: sentence-final punctuation (plus any closing quotes),
    then whitespace, then something that starts a new sentence — a capital
    or an opening quote. That deliberately leaves dialogue attribution
    alone: in `"What is he doing?" you ask.` the lowercase "you" means no
    break, so the line still reads as one thought.
    """
    # Markdown emphasis never renders anywhere in the pilot; the craft gate
    # now blocks it at generation, and this strips any that slipped in
    # earlier so the narrator never reads an asterisk aloud. Character
    # removal only: the paragraph split above is untouched.
    chunk_text = chunk_text.replace("*", "")
    if not sentence_pause_ms or sentence_pause_ms <= 0:
        return chunk_text
    tag = f'<break time="{int(sentence_pause_ms)}ms"/>'
    short_tag = tag
    if short_sentence_chars > 0 and short_sentence_pause_ms is not None:
        short_tag = (
            f'<break time="{int(short_sentence_pause_ms)}ms"/>'
            if short_sentence_pause_ms > 0 else " "  # keep the word gap
        )
    pieces: list[str] = []
    segment_start = 0
    index = 0
    length = len(chunk_text)
    while index < length:
        if chunk_text[index] not in SENTENCE_FINAL:
            index += 1
            continue
        terminal_index = index
        after = index + 1
        while after < length and chunk_text[after] in SENTENCE_FINAL:
            after += 1
        while after < length and chunk_text[after] in SENTENCE_CLOSERS:
            after += 1
        next_start = after
        while next_start < length and chunk_text[next_start].isspace():
            next_start += 1
        sentence_long_enough = (
            after - segment_start >= MIN_SENTENCE_CHARS_FOR_PAUSE
        )
        if (
            next_start > after
            and next_start < length
            and _opens_sentence(chunk_text[next_start])
            and sentence_long_enough
            and not _is_abbreviation(chunk_text, terminal_index)
        ):
            pieces.append(chunk_text[segment_start:after])
            is_short = (
                short_sentence_chars > 0
                and after - segment_start < short_sentence_chars
            )
            pieces.append(short_tag if is_short else tag)
            # The break replaces the inter-sentence whitespace.
            segment_start = next_start
            index = next_start
            continue
        index = after
    pieces.append(chunk_text[segment_start:])
    return "".join(pieces)


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
