"""
Craft audit for the pilot stories — the first piece of the pipeline's
Stage 5 gate (see story_definitions/STORY_GENERATION_WORKFLOW.md).

    python scripts/audit_story_craft.py                 # every story
    python scripts/audit_story_craft.py --compare       # v1 vs v2.1 table
    python scripts/audit_story_craft.py --story bees    # one story, detailed

Two findings BLOCK, because they are exact: a segment over the age band's
word ceiling, and banned evaluation language. Everything else is a WARNING
for human eyes — a blocking threshold on a judgment call is how arbitrary
rules creep back in (prompt v2.1, §0).

Run as a script, not `python -m` from the repo root: the package's
logging/ subpackage would shadow stdlib logging.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = REPO_ROOT / "story_definitions" / "stories" / "pilot"
ARCHIVE_DIR = REPO_ROOT / "story_definitions" / "stories" / "archive_v1"

# Ceilings only — there is deliberately no minimum, because padding is the
# failure this whole audit exists to catch (prompt v2.1 §8).
SEGMENT_WORD_CEILING = {
    "3-4": 130,
    "5-6": 200,
    "7-8": 280,
    "9-10": 360,
    "11-12": 440,
}

# Mood words that usually mean a feeling was told instead of given.
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
# Unambiguous evaluation language: these BLOCK.
BANNED_EVALUATION = (
    r"\bassessment\b",
    r"\bmastery\b",
    r"\bmilestone(s)?\b",
    r"\bdelayed\b",
    r"\bgifted\b",
    r"\bgrade\s+level\b",
)
# Phrases that are developmental comparison in a parent-facing sentence but
# ordinary English in a story ("trotting ahead of us", "the light was falling
# behind"). These WARN, matching jubu_chat.story_generation.craft_gate; they
# are deliberately absent from graph_validator.BANNED_LANGUAGE_PATTERNS, which
# is what build_story_explorer --check enforces. Blocking on them here made the
# audit disagree with both, and reported 8 of the shipped 86 as blocked.
EVALUATION_ISH = (
    r"\b(is|are|fall(s|ing)?|lag(s|ging)?)\s+behind\b",
    r"\bahead\s+of\b",
)
# A choice question the narrator asks, rather than a character (v2.1 §9).
NARRATOR_ASK = re.compile(r"^\s*(should we|shall we|do we|what should)", re.IGNORECASE)
# Rough physical-action probe for the dialogue-or-action share.
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
SHORT_SENTENCE = 6  # words or fewer counts as a punch sentence
DIALOGUE_ACTION_SHARE = 0.40


@dataclass
class Finding:
    severity: str  # "block" or "warn"
    rule: str
    where: str
    detail: str


@dataclass
class StoryAudit:
    story_id: str
    file: str
    title: str
    prompt_version: str
    age_band: str
    pattern: str
    teller: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def blocks(self) -> int:
        return sum(1 for f in self.findings if f.severity == "block")

    @property
    def warns(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def has_speech(text: str) -> bool:
    return '"' in text


def sentence_is_action(sentence: str) -> bool:
    lowered = sentence.lower()
    if '"' in sentence:
        return True
    return any(re.search(rf"\b{verb}(s|ed|ing)?\b", lowered) for verb in ACTION_VERBS)


def audit_story(story: dict[str, Any], path: Path) -> StoryAudit:
    record = story.get("build_record", {})
    audit = StoryAudit(
        story_id=story["id"],
        file=path.name,
        title=story["title"],
        prompt_version=record.get("prompt_version", "segment_writing_v1 (archived)"),
        age_band=story["age_band"],
        pattern=story["pattern"],
        teller=story["teller"],
    )
    band = story["age_band"]
    if band not in SEGMENT_WORD_CEILING:
        raise SystemExit(
            f"no word ceiling for age band {band!r} ({path.name}); "
            "add it to SEGMENT_WORD_CEILING"
        )
    ceiling = SEGMENT_WORD_CEILING[band]

    segment_words: dict[str, int] = {}
    spreads: list[float] = []
    speech_segments = 0
    action_shares: list[float] = []

    for segment in story["segments"]:
        text = segment["text"]
        sid = segment["id"]
        words = len(text.split())
        segment_words[sid] = words

        if words > ceiling:
            audit.findings.append(
                Finding(
                    "block",
                    "length ceiling",
                    sid,
                    f"{words} words over the {ceiling} ceiling for age "
                    f"{story['age_band']}",
                )
            )

        for pattern in BANNED_EVALUATION:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                audit.findings.append(
                    Finding("block", "banned language", sid, repr(match.group(0)))
                )
        for pattern in EVALUATION_ISH:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                audit.findings.append(
                    Finding(
                        "warn",
                        "evaluation-ish phrase",
                        sid,
                        f"{match.group(0)!r} (usually literal; check it isn't a "
                        "developmental comparison)",
                    )
                )

        sentences = split_sentences(text)
        lengths = [len(s.split()) for s in sentences]
        spread = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0
        spreads.append(spread)
        if spread < FLAT_RHYTHM_SPREAD:
            audit.findings.append(
                Finding(
                    "warn",
                    "flat rhythm",
                    sid,
                    f"sentence lengths vary little (spread {spread:.1f}); "
                    "v2.1 asks for rise and fall",
                )
            )
        run = 1
        for previous, current in zip(lengths, lengths[1:]):
            run = run + 1 if abs(previous - current) <= 2 else 1
            if run >= SAME_LENGTH_RUN:
                audit.findings.append(
                    Finding(
                        "warn",
                        "flat rhythm",
                        sid,
                        f"{run} sentences in a row of near-identical length",
                    )
                )
                break
        if not any(length <= SHORT_SENTENCE for length in lengths):
            audit.findings.append(
                Finding("warn", "no punch sentence", sid, "no short landing sentence")
            )

        if has_speech(text):
            speech_segments += 1
        else:
            audit.findings.append(
                Finding("warn", "no voices", sid, "segment carries no spoken line")
            )

        share = (
            sum(1 for s in sentences if sentence_is_action(s)) / len(sentences)
            if sentences
            else 0.0
        )
        action_shares.append(share)
        if share < DIALOGUE_ACTION_SHARE:
            audit.findings.append(
                Finding(
                    "warn",
                    "narration heavy",
                    sid,
                    f"only {share:.0%} of sentences carry speech or action",
                )
            )

        for word in ABSTRACT_MOOD_WORDS:
            if re.search(rf"\b{word}\b", text, re.IGNORECASE):
                audit.findings.append(
                    Finding(
                        "warn",
                        "abstract mood word",
                        sid,
                        f"{word!r} usually means a feeling was told, not given",
                    )
                )

    for choice in story["choice_points"]:
        question = choice["question"]
        if not has_speech(question):
            audit.findings.append(
                Finding(
                    "warn",
                    "narrator asks the choice",
                    choice["id"],
                    "v2.1 asks for a character to pose the question in their voice",
                )
            )
        elif NARRATOR_ASK.match(question):
            audit.findings.append(
                Finding(
                    "warn",
                    "narrator asks the choice",
                    choice["id"],
                    "question opens in narrator voice",
                )
            )

    paths = [("s1", a, "s3", b) for a in ("s2a", "s2b") for b in ("s4a", "s4b")]
    path_totals = [
        sum(segment_words.get(sid, 0) for sid in p)
        for p in paths
        if all(sid in segment_words for sid in p)
    ]
    audit.metrics = {
        "segments": segment_words,
        "longest_path_words": max(path_totals) if path_totals else 0,
        "mean_rhythm_spread": round(statistics.mean(spreads), 2) if spreads else 0,
        "segments_with_speech": f"{speech_segments}/{len(story['segments'])}",
        "mean_action_share": (
            round(statistics.mean(action_shares), 2) if action_shares else 0
        ),
    }
    return audit


def load_all(include_archive: bool = False) -> list[tuple[dict[str, Any], Path]]:
    """Live stories, optionally plus the archived v1 texts for comparison."""
    directories = [STORIES_DIR]
    if include_archive and ARCHIVE_DIR.is_dir():
        directories.append(ARCHIVE_DIR)
    return [
        (json.loads(path.read_text(encoding="utf-8")), path)
        for directory in directories
        for path in sorted(directory.glob("*.json"))
    ]


def print_story(audit: StoryAudit, verbose: bool) -> None:
    flag = "BLOCK" if audit.blocks else ("warn " if audit.warns else "clean")
    version = "v2.1" if "v2.1" in audit.prompt_version else "v1  "
    print(
        f"[{flag}] {version} {audit.title[:38]:<38} "
        f"{audit.pattern:<16} path {audit.metrics['longest_path_words']:>4}w "
        f"rhythm {audit.metrics['mean_rhythm_spread']:>5} "
        f"action {audit.metrics['mean_action_share']:.0%} "
        f"warns {audit.warns}"
    )
    if verbose:
        for finding in audit.findings:
            mark = "!!" if finding.severity == "block" else " ·"
            print(f"     {mark} {finding.rule} [{finding.where}]: {finding.detail}")


def print_comparison(audits: list[StoryAudit]) -> None:
    v1 = [a for a in audits if "v2.1" not in a.prompt_version]
    v2 = [a for a in audits if "v2.1" in a.prompt_version]

    def mean(group: list[StoryAudit], key: str) -> float:
        values = [a.metrics[key] for a in group]
        return round(statistics.mean(values), 2) if values else 0.0

    def rate(group: list[StoryAudit], rule: str) -> str:
        if not group:
            return "-"
        hits = sum(1 for a in group for f in a.findings if f.rule == rule)
        return f"{hits / len(group):.1f} per story"

    print("\n" + "=" * 74)
    print(f"v1 prompt: {len(v1)} stories      v2.1 prompt: {len(v2)} stories")
    print("=" * 74)
    rows = [
        (
            "longest path, words",
            mean(v1, "longest_path_words"),
            mean(v2, "longest_path_words"),
            "lower is better: padding removed",
        ),
        (
            "sentence-length spread",
            mean(v1, "mean_rhythm_spread"),
            mean(v2, "mean_rhythm_spread"),
            "higher is better: rhythm alternates",
        ),
        (
            "speech or action share",
            mean(v1, "mean_action_share"),
            mean(v2, "mean_action_share"),
            "higher is better: voices carry it",
        ),
    ]
    print(f"{'metric':<26}{'v1':>10}{'v2.1':>10}   note")
    for name, a, b, note in rows:
        print(f"{name:<26}{a:>10}{b:>10}   {note}")
    print()
    print(f"{'warning':<26}{'v1':>10}{'v2.1':>10}")
    for rule in (
        "flat rhythm",
        "no punch sentence",
        "narration heavy",
        "no voices",
        "abstract mood word",
        "narrator asks the choice",
    ):
        print(f"{rule:<26}{rate(v1, rule):>10}{rate(v2, rule):>10}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="v1 vs v2.1 summary (reads the archived v1 texts too)",
    )
    parser.add_argument(
        "--story", default=None, help="audit one story by filename stem"
    )
    args = parser.parse_args()

    audits = []
    for story, path in load_all(include_archive=args.compare):
        if args.story and args.story not in path.stem:
            continue
        audits.append(audit_story(story, path))

    audits.sort(key=lambda a: ("v2.1" in a.prompt_version, a.title))
    for audit in audits:
        print_story(audit, verbose=bool(args.story))

    if args.compare:
        print_comparison(audits)

    blocked = [a for a in audits if a.blocks]
    print(f"\n{len(audits)} stories audited, {len(blocked)} with blocking findings")
    for audit in blocked:
        for finding in audit.findings:
            if finding.severity == "block":
                print(
                    f"  {audit.file} [{finding.where}] {finding.rule}: {finding.detail}"
                )
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
