"""
Craft audit for the pilot stories — runs the shared craft gate over the
library and reports.

    python scripts/audit_story_craft.py                 # every story
    python scripts/audit_story_craft.py --compare       # per prompt version
    python scripts/audit_story_craft.py --story bees    # one story, detailed

The rules live in jubu_datastore/story_generation/craft_gate.py — the same
module the generation pipeline runs per segment. This script only loads,
runs, and prints. Three findings BLOCK (word ceiling, banned evaluation
language, markdown asterisk); everything else is a WARNING for human eyes.

Run as a script, not `python -m` from the repo root: the package's
logging/ subpackage would shadow stdlib logging.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jubu_datastore.story_generation.craft_gate import (
    Finding,
    ceiling_for_band,
    check_story,
    paragraphs,
    sentence_carries_speech_or_action,
    split_sentences,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = REPO_ROOT / "story_definitions" / "stories" / "pilot"
ARCHIVE_DIR = REPO_ROOT / "story_definitions" / "stories" / "archive_v1"

PATH_SHAPES = [("s1", a, "s3", b) for a in ("s2a", "s2b") for b in ("s4a", "s4b")]


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
    audit.findings = check_story(story, ceiling_for_band(story["age_band"]))

    segment_words: dict[str, int] = {}
    spreads: list[float] = []
    action_shares: list[float] = []
    paragraph_counts: list[int] = []
    speech_segments = 0
    for segment in story["segments"]:
        text = segment["text"]
        segment_words[segment["id"]] = len(text.split())
        sentences = split_sentences(text)
        lengths = [len(s.split()) for s in sentences]
        spreads.append(statistics.pstdev(lengths) if len(lengths) > 1 else 0.0)
        action_shares.append(
            sum(1 for s in sentences if sentence_carries_speech_or_action(s))
            / len(sentences)
            if sentences
            else 0.0
        )
        paragraph_counts.append(len(paragraphs(text)))
        if '"' in text:
            speech_segments += 1

    path_totals = [
        sum(segment_words.get(sid, 0) for sid in shape)
        for shape in PATH_SHAPES
        if all(sid in segment_words for sid in shape)
    ]
    audit.metrics = {
        "segments": segment_words,
        "longest_path_words": max(path_totals) if path_totals else 0,
        "mean_rhythm_spread": round(statistics.mean(spreads), 2) if spreads else 0,
        "segments_with_speech": f"{speech_segments}/{len(story['segments'])}",
        "mean_action_share": (
            round(statistics.mean(action_shares), 2) if action_shares else 0
        ),
        "mean_paragraphs": (
            round(statistics.mean(paragraph_counts), 1) if paragraph_counts else 0
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


def short_version(prompt_version: str) -> str:
    return prompt_version.replace("segment_writing_", "").split(" ")[0]


def print_story(audit: StoryAudit, verbose: bool) -> None:
    flag = "BLOCK" if audit.blocks else ("warn " if audit.warns else "clean")
    print(
        f"[{flag}] {short_version(audit.prompt_version):<5} {audit.age_band:<5} "
        f"{audit.title[:36]:<36} {audit.pattern:<16} "
        f"path {audit.metrics['longest_path_words']:>4}w "
        f"paras {audit.metrics['mean_paragraphs']:>4} "
        f"rhythm {audit.metrics['mean_rhythm_spread']:>5} "
        f"action {audit.metrics['mean_action_share']:.0%} "
        f"warns {audit.warns}"
    )
    if verbose:
        for finding in audit.findings:
            mark = "!!" if finding.severity == "block" else " ·"
            print(f"     {mark} {finding.rule} [{finding.where}]: {finding.detail}")


def print_comparison(audits: list[StoryAudit]) -> None:
    """Metrics and warning rates grouped by prompt version."""
    groups: dict[str, list[StoryAudit]] = {}
    for audit in audits:
        groups.setdefault(short_version(audit.prompt_version), []).append(audit)
    versions = sorted(groups)

    def mean(group: list[StoryAudit], key: str) -> float:
        values = [a.metrics[key] for a in group]
        return round(statistics.mean(values), 2) if values else 0.0

    def rate(group: list[StoryAudit], rule: str) -> str:
        hits = sum(1 for a in group for f in a.findings if f.rule == rule)
        return f"{hits / len(group):.2f}"

    width = 10
    print("\n" + "=" * (28 + width * len(versions)))
    print("stories".ljust(28) + "".join(f"{len(groups[v]):>{width}}" for v in versions))
    print("prompt".ljust(28) + "".join(f"{v:>{width}}" for v in versions))
    print("=" * (28 + width * len(versions)))
    for name, key in (
        ("longest path, words", "longest_path_words"),
        ("paragraphs per segment", "mean_paragraphs"),
        ("sentence-length spread", "mean_rhythm_spread"),
        ("speech or action share", "mean_action_share"),
    ):
        print(name.ljust(28) + "".join(f"{mean(groups[v], key):>{width}}" for v in versions))
    print()
    print("warnings per story")
    for rule in (
        "single paragraph",
        "flat rhythm",
        "no punch sentence",
        "narration heavy",
        "no voices",
        "abstract mood word",
        "narrator asks the choice",
    ):
        print(rule.ljust(28) + "".join(f"{rate(groups[v], rule):>{width}}" for v in versions))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="metrics per prompt version (reads the archived v1 texts too)",
    )
    parser.add_argument("--story", default=None, help="audit one story by filename stem")
    parser.add_argument("--verbose", action="store_true", help="print every finding")
    args = parser.parse_args()

    audits = []
    for story, path in load_all(include_archive=args.compare):
        if args.story and args.story not in path.stem:
            continue
        audits.append(audit_story(story, path))

    audits.sort(key=lambda a: (a.prompt_version, a.age_band, a.title))
    for audit in audits:
        print_story(audit, verbose=bool(args.story) or args.verbose)

    if args.compare:
        print_comparison(audits)

    blocked = [a for a in audits if a.blocks]
    print(f"\n{len(audits)} stories audited, {len(blocked)} with blocking findings")
    for audit in blocked:
        for finding in audit.findings:
            if finding.severity == "block":
                print(f"  {audit.file} [{finding.where}] {finding.rule}: {finding.detail}")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
