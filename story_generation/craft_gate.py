"""
The craft gate — the one place the mechanical story rules live.

Imported by the generation pipeline (jubu_backend, per segment as it is
written and once over the whole braid) and by the library audit
(scripts/audit_story_craft.py). The knowledge-graph validator derives its
banned-language list from BANNED_EVALUATION below. Change a rule here and
every consumer changes with it; there is deliberately no second copy.

Three findings BLOCK, because they are exact: a segment over its age band's
word ceiling, banned evaluation language, and a markdown asterisk (nothing
renders it, so the narrator reads it aloud). Everything else WARNS for
human eyes. A blocking threshold on a judgment call is how arbitrary rules
creep back in (writing prompt, section 0), so craft findings never fail a
build on their own.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List

# Word CEILINGS per segment, per age band. Never targets: padding is a
# failure, so there is deliberately no minimum. A new band needs an entry
# here, plus audio_voices.json, BANDS in the pilot's stories.js and a stop
# on the slider in stories.html.
SEGMENT_WORD_CEILING: Dict[str, int] = {
    "3-4": 130,
    "5-6": 200,
    "7-8": 280,
    "9-10": 360,
    "11-12": 440,
}

# A segment this long that arrives as ONE paragraph is almost always a
# writer that forgot to break it, not a choice. Paragraphs are load-bearing:
# the audio pipeline makes one clip per paragraph, so a single-paragraph
# segment is one long clip with no way to resume partway.
SINGLE_PARAGRAPH_MIN_WORDS = 60

ABSTRACT_MOOD_WORDS = (
    "cozy",
    "cosy",
    "magical",
    "wondrous",
    "serene",
    "peaceful",
    "delightful",
    "beautiful",
)
# Evaluation language that frames a CHILD in developmental-report terms. These
# are never innocent in a children's story, so a match BLOCKS the build.
BANNED_EVALUATION = (
    r"\bassessment\b",
    r"\bmastery\b",
    r"\bmilestone(s)?\b",
    r"\bdelayed\b",
    r"\bgifted\b",
    r"\bgrade\s+level\b",
)
# Comparative phrases that are almost always literal in a story ("the boat
# ahead of us", "the rock behind him") and only rarely slip into
# developmental comparison. Far too false-positive-prone to BLOCK — across
# every generation run they were the #1 spurious blocker — so they only WARN.
BANNED_EVALUATION_SOFT = (
    r"\bahead\s+of\b",
    r"\b(is|are|fall(s|ing)?|lag(s|ging)?)\s+behind\b",
)
NARRATOR_ASK = re.compile(r"^\s*(should we|shall we|do we|what should)", re.IGNORECASE)
ACTION_VERBS = (
    "walk",
    "run",
    "climb",
    "push",
    "pull",
    "sit",
    "stand",
    "hold",
    "reach",
    "touch",
    "lift",
    "listen",
    "look",
    "watch",
    "press",
    "dig",
    "jump",
    "crouch",
    "point",
    "carry",
    "open",
    "close",
    "step",
    "lean",
    "wait",
    "put",
    "take",
    "turn",
    "come",
    "go",
    "swim",
    "fly",
    "land",
    "hop",
)

FLAT_RHYTHM_SPREAD = 5.0  # stdev of sentence lengths below this reads flat
SAME_LENGTH_RUN = 4  # this many near-identical sentences in a row is a hum
SHORT_SENTENCE_WORDS = 6  # words or fewer counts as a punch sentence
DIALOGUE_ACTION_SHARE = 0.40


@dataclass(frozen=True)
class Finding:
    """One gate result, addressed to a segment or a choice point."""

    severity: str  # "block" or "warn"
    rule: str
    where: str
    detail: str

    def as_note(self) -> str:
        return f"[{self.where}] {self.rule}: {self.detail}"


def ceiling_for_band(age_band: str) -> int:
    try:
        return SEGMENT_WORD_CEILING[age_band]
    except KeyError:
        raise ValueError(
            f"no word ceiling for age band {age_band!r}; add it to "
            "jubu_datastore.story_generation.craft_gate.SEGMENT_WORD_CEILING"
        ) from None


def normalize_prose(text: str) -> str:
    """
    Mechanical cleanup applied to every segment the writer returns, before
    any check runs. Removes markdown emphasis (the narrator would read the
    asterisks aloud), normalizes line endings, trims each paragraph, and
    collapses runs of blank lines to one — so the paragraph split the audio
    pipeline and the player both perform sees exactly one break per
    paragraph.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("*", "")
    paragraphs = [line.strip() for line in text.split("\n")]
    out: List[str] = []
    for paragraph in paragraphs:
        if paragraph:
            out.append(paragraph)
        elif out and out[-1] != "":
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def paragraphs(text: str) -> List[str]:
    """The paragraph split — identical to story_audio_chunks.paragraph_chunks."""
    return [p.strip() for p in text.split("\n") if p.strip()]


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def sentence_carries_speech_or_action(sentence: str) -> bool:
    if '"' in sentence:
        return True
    lowered = sentence.lower()
    return any(re.search(rf"\b{verb}(s|ed|ing)?\b", lowered) for verb in ACTION_VERBS)


def check_segment(segment_id: str, text: str, word_ceiling: int) -> List[Finding]:
    """Every per-segment rule, run on one segment."""
    findings: List[Finding] = []
    words = len(text.split())
    if words > word_ceiling:
        findings.append(
            Finding(
                "block",
                "length ceiling",
                segment_id,
                f"{words} words over the {word_ceiling} ceiling",
            )
        )
    if "*" in text:
        findings.append(
            Finding(
                "block",
                "markdown asterisk",
                segment_id,
                "asterisk in prose; nothing renders it and the narrator reads it",
            )
        )
    for pattern in BANNED_EVALUATION:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            findings.append(
                Finding("block", "banned language", segment_id, repr(match.group(0)))
            )
    for pattern in BANNED_EVALUATION_SOFT:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            findings.append(
                Finding(
                    "warn",
                    "evaluation-ish phrase",
                    segment_id,
                    repr(match.group(0)) + " (usually literal; check it isn't a "
                    "developmental comparison)",
                )
            )

    if words >= SINGLE_PARAGRAPH_MIN_WORDS and len(paragraphs(text)) == 1:
        findings.append(
            Finding(
                "warn",
                "single paragraph",
                segment_id,
                f"{words} words in one paragraph; one clip, no resume point",
            )
        )

    sentences = split_sentences(text)
    lengths = [len(sentence.split()) for sentence in sentences]
    if len(lengths) > 1:
        spread = statistics.pstdev(lengths)
        if spread < FLAT_RHYTHM_SPREAD:
            findings.append(
                Finding(
                    "warn",
                    "flat rhythm",
                    segment_id,
                    f"sentence lengths vary little (spread {spread:.1f})",
                )
            )
        run = 1
        for previous, current in zip(lengths, lengths[1:]):
            run = run + 1 if abs(previous - current) <= 2 else 1
            if run >= SAME_LENGTH_RUN:
                findings.append(
                    Finding(
                        "warn",
                        "flat rhythm",
                        segment_id,
                        f"{run} sentences in a row of near-identical length",
                    )
                )
                break
    if lengths and not any(length <= SHORT_SENTENCE_WORDS for length in lengths):
        findings.append(
            Finding(
                "warn", "no punch sentence", segment_id, "no short landing sentence"
            )
        )
    if '"' not in text:
        findings.append(
            Finding("warn", "no voices", segment_id, "segment carries no spoken line")
        )
    if sentences:
        share = sum(
            1 for sentence in sentences if sentence_carries_speech_or_action(sentence)
        ) / len(sentences)
        if share < DIALOGUE_ACTION_SHARE:
            findings.append(
                Finding(
                    "warn",
                    "narration heavy",
                    segment_id,
                    f"only {share:.0%} of sentences carry speech or action",
                )
            )
    for word in ABSTRACT_MOOD_WORDS:
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            findings.append(
                Finding(
                    "warn",
                    "abstract mood word",
                    segment_id,
                    f"{word!r} usually means a feeling was told, not given",
                )
            )
    return findings


def check_choice_point(choice: Dict[str, Any]) -> List[Finding]:
    """A character should ask the question, in their own voice."""
    findings: List[Finding] = []
    question = choice.get("question", "")
    choice_id = choice.get("id", "choice")
    if "*" in question:
        findings.append(
            Finding("block", "markdown asterisk", choice_id, "asterisk in question")
        )
    if '"' not in question:
        findings.append(
            Finding(
                "warn",
                "narrator asks the choice",
                choice_id,
                "no spoken line; a character should pose the question",
            )
        )
    elif NARRATOR_ASK.match(question):
        findings.append(
            Finding(
                "warn",
                "narrator asks the choice",
                choice_id,
                "question opens in narrator voice",
            )
        )
    options = choice.get("options", [])
    say_words = {str(option.get("say_word", "")).strip().lower() for option in options}
    if len(say_words) != len(options):
        findings.append(
            Finding("warn", "say-words alike", choice_id, "say-words are not distinct")
        )
    return findings


def check_story(story: Dict[str, Any], word_ceiling: int) -> List[Finding]:
    """The whole braid, including structure and slot consistency."""
    findings: List[Finding] = []
    for segment in story.get("segments", []):
        findings.extend(check_segment(segment["id"], segment["text"], word_ceiling))
    for choice in story.get("choice_points", []):
        findings.extend(check_choice_point(choice))

    segments = {segment["id"]: segment for segment in story.get("segments", [])}
    endings = [s for s in story.get("segments", []) if s.get("next") is None]
    if len(endings) != 2:
        findings.append(
            Finding(
                "block", "braid", "story", f"expected 2 endings, found {len(endings)}"
            )
        )
    declared = set(story.get("slots", {}))
    used: set[str] = set()
    for segment in story.get("segments", []):
        used.update(re.findall(r"\{(\w+)\}", segment["text"]))
    unknown = used - declared
    if unknown:
        findings.append(
            Finding(
                "block", "slots", "story", f"undeclared slots used: {sorted(unknown)}"
            )
        )
    unused = declared - used
    if unused:
        findings.append(
            Finding(
                "warn", "slots", "story", f"declared but never used: {sorted(unused)}"
            )
        )
    for choice in story.get("choice_points", []):
        for option in choice.get("options", []):
            if option.get("next_segment") not in segments:
                findings.append(
                    Finding(
                        "block",
                        "braid",
                        choice.get("id", "choice"),
                        f"option points at unknown segment {option.get('next_segment')}",
                    )
                )
    return findings


def blocking(findings: List[Finding]) -> List[Finding]:
    return [finding for finding in findings if finding.severity == "block"]


def summarize(findings: List[Finding]) -> str:
    blocks = len(blocking(findings))
    warns = len(findings) - blocks
    return f"{blocks} blocking, {warns} warning"
