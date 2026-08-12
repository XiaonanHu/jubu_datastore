"""
Ingest generated stories into the pilot library.

Takes the raw output of a generation run (jubu_backend/_demo_run_*/) and
promotes the keepers into story_definitions/stories/pilot/ in library form.

    python scripts/ingest_pilot_stories.py --source ../jubu_backend/_demo_run_kid1
    python scripts/ingest_pilot_stories.py --source ../jubu_backend/_demo_run_kid1 \
                                           --source ../jubu_backend/_demo_run_kid2 \
                                           --dry-run

What it does to each story (the same pass that produced the original 86,
which was run ad hoc and never committed -- this is that pass, written down):

  1. Unwraps the bench's {topic, ok, craft_findings, story} envelope. Bare
     story files (build_story.py output) are accepted as-is.
  2. Skips anything the craft gate blocked, unless --include-blocked.
  3. Prunes orphaned naming slots -- declared slots are cut to exactly the
     tokens the prose actually uses, and options' sets_slots are scrubbed to
     match. build_story_explorer.validate_story treats a mismatch either way
     as fatal, so this is not cosmetic.
  4. Mints an opaque 6-hex uniqueness token, collision-checked against the
     library and against this run. Nothing downstream parses it -- group by
     topic + depth, never by reading the filename.
  5. Rewrites id to story.{topic}.age{band}.d{n}.{provenance}.{hash6} and
     writes {topic}__age{band}__d{n}__{provenance}__{hash6}.json.
  6. Appends depth (top level, last key) and build_record.library_ingest
     (last key of build_record), matching the shape of the existing 86.
  7. Re-gates every written story through audit_story_craft.

Run as a script from the repo root, not `python -m`: the package's logging/
subpackage would shadow stdlib logging.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = REPO_ROOT / "story_definitions" / "stories" / "pilot"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_story_craft as asc  # noqa: E402

# Canonical key order of a library story. depth is last, after build_record.
TOP_LEVEL_ORDER = [
    "id", "title", "age_band", "topics", "pattern", "teller", "tone", "spine",
    "slots", "start_segment", "segments", "choice_points", "status",
    "build_record", "depth",
]
SLOT_TOKEN = re.compile(r"\{([a-z0-9_]+)\}", re.IGNORECASE)


def band_token(age_band: str) -> str:
    """'9-10' -> 'age9to10'."""
    low, _, high = age_band.partition("-")
    return f"age{low}to{high}"


def used_slots(story: dict[str, Any]) -> set[str]:
    """Slots the prose actually renders.

    Deliberately segments-only: that is exactly what validate_story counts,
    so anything else would pass here and fail there.
    """
    found: set[str] = set()
    for segment in story.get("segments", []):
        found.update(SLOT_TOKEN.findall(segment.get("text") or ""))
    return found


def question_only_slots(story: dict[str, Any]) -> set[str]:
    """Slots that appear ONLY in a choice question -- unrenderable either way."""
    in_questions: set[str] = set()
    for choice in story.get("choice_points", []):
        in_questions.update(SLOT_TOKEN.findall(choice.get("question") or ""))
    return in_questions - used_slots(story)


def prune_slots(story: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Cut declared slots to the used set; scrub sets_slots to match."""
    keep = used_slots(story)
    declared = dict(story.get("slots") or {})
    dropped = sorted(set(declared) - keep)
    story["slots"] = {k: v for k, v in declared.items() if k in keep}

    scrubbed: list[str] = []
    for choice in story.get("choice_points", []):
        for option in choice.get("options", []):
            sets = option.get("sets_slots")
            if not sets:
                continue
            kept = [s for s in sets if s in keep]
            if kept != list(sets):
                scrubbed.extend(s for s in sets if s not in keep)
                option["sets_slots"] = kept
    return dropped, sorted(set(scrubbed))


def mint_hash6(taken: set[str]) -> str:
    while True:
        token = secrets.token_hex(3)
        if token not in taken:
            taken.add(token)
            return token


def existing_hashes() -> set[str]:
    found: set[str] = set()
    for path in STORIES_DIR.glob("*.json"):
        parts = path.stem.split("__")
        if len(parts) == 5:
            found.add(parts[-1])
    return found


def unwrap(raw: dict[str, Any], path: Path) -> tuple[dict[str, Any] | None, bool, str]:
    """Return (story, gate_passed, note). story is None when unusable."""
    if "segments" in raw and "story" not in raw:
        return raw, True, "bare story file (no gate record)"
    story = raw.get("story")
    if not isinstance(story, dict) or "segments" not in story:
        return None, False, "no story object"
    passed = bool(raw.get("ok", True))
    note = "" if passed else str(raw.get("failure") or "gate blocked")
    return story, passed, note


def ordered(story: dict[str, Any]) -> dict[str, Any]:
    out = {k: story[k] for k in TOP_LEVEL_ORDER if k in story}
    for k, v in story.items():  # anything unexpected keeps its place at the end
        out.setdefault(k, v)
    return out


def ingest_one(
    path: Path, args: argparse.Namespace, taken: set[str]
) -> dict[str, Any] | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    story, passed, note = unwrap(raw, path)
    if story is None:
        print(f"  SKIP  {path.name}: {note}")
        return None
    if not passed and not args.include_blocked:
        print(f"  SKIP  {path.name}: {note}")
        return None

    orphan_q = question_only_slots(story)
    if orphan_q:
        print(
            f"  SKIP  {path.name}: slots {sorted(orphan_q)} appear only in a "
            "choice question, never in prose -- fix by hand, pruning would "
            "leave a raw token on screen"
        )
        return None

    topic_id = story["topics"]["knowledge_domain"]
    topic = topic_id.split(".")[-1]
    band = band_token(story["age_band"])
    depth = args.depth
    token = mint_hash6(taken)

    dropped, scrubbed = prune_slots(story)
    story["id"] = f"story.{topic}.{band}.d{depth}.{args.provenance}.{token}"

    record = story.setdefault("build_record", {})
    record.pop("library_ingest", None)  # keep it last on re-ingest
    ingest: dict[str, Any] = {"provenance": f"{args.provenance}_batch"}
    if args.provenance == "pregen":
        ingest["generator"] = args.generator
        ingest["source_run"] = path.parent.name
        ingest["source_file"] = path.name
    ingest["depth"] = depth
    record["library_ingest"] = ingest
    story["depth"] = depth

    out_name = f"{topic}__{band}__d{depth}__{args.provenance}__{token}.json"
    out_path = STORIES_DIR / out_name
    flags = []
    if dropped:
        flags.append(f"pruned slots {dropped}")
    if scrubbed:
        flags.append(f"scrubbed sets_slots {scrubbed}")
    if not passed:
        flags.append(f"INGESTED DESPITE GATE: {note}")
    suffix = ("  -- " + "; ".join(flags)) if flags else ""
    print(f"  {'would write' if args.dry_run else 'wrote'}  {out_name}{suffix}")

    if not args.dry_run:
        out_path.write_text(
            json.dumps(ordered(story), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {"path": out_path, "story": ordered(story), "source": path.name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", action="append", required=True, metavar="DIR",
        help="a generation output directory (repeatable)",
    )
    parser.add_argument(
        "--generator", default="kimi-k3",
        help="model that wrote these, recorded in provenance (default kimi-k3)",
    )
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument(
        "--provenance", default="pregen", choices=["pregen", "authored"],
    )
    parser.add_argument(
        "--include-blocked", action="store_true",
        help="ingest stories the craft gate rejected (records it in the log)",
    )
    parser.add_argument(
        "--only", default=None,
        help="substring filter on source filenames",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not STORIES_DIR.is_dir():
        raise SystemExit(f"no pilot stories directory at {STORIES_DIR}")

    taken = existing_hashes()
    print(f"library: {len(list(STORIES_DIR.glob('*.json')))} stories, "
          f"{len(taken)} hashes in use")

    written: list[dict[str, Any]] = []
    for source in args.source:
        directory = Path(source).expanduser().resolve()
        if not directory.is_dir():
            raise SystemExit(f"not a directory: {directory}")
        files = [
            p for p in sorted(directory.glob("*.json"))
            if p.name != "manifest.json"
            and (args.only is None or args.only in p.name)
        ]
        print(f"\n{directory.name}: {len(files)} candidate file(s)")
        for path in files:
            result = ingest_one(path, args, taken)
            if result:
                written.append(result)

    print(f"\n{len(written)} story(ies) {'would be ' if args.dry_run else ''}ingested")
    if not written:
        return 0

    print("\nre-gate:")
    blocked = 0
    for item in written:
        audit = asc.audit_story(item["story"], item["path"])
        if audit.blocks:
            blocked += 1
            print(f"  BLOCK  {item['path'].name} ({audit.blocks} blocking)")
            for finding in audit.findings:
                if finding.severity == "block":
                    print(f"           [{finding.where}] {finding.rule}: {finding.detail}")
        else:
            print(f"  ok     {item['path'].name} ({audit.warns} warning(s))")

    if blocked:
        print(f"\n{blocked} story(ies) still block the craft gate.")
        if not args.dry_run:
            print("They are on disk -- fix or delete them before validating.")
    print("\nnext: python scripts/build_story_explorer.py --check")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
