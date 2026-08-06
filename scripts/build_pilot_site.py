"""Build the deployable buju.ai/pilot assets from the pilot story library.

Outputs (under story_definitions/preview/pilot_site/):

  data/stories.json      parent-facing story data: full prose + choices + slots,
                         but NO build_record / gate findings / R&D internals.
  explorer/index.html    the admin story explorer, with its script split out to
  explorer/explorer.js   an external file so it can ship under the website's
                         CSP (script-src 'self' forbids inline scripts).

Run from the repo root as:  python scripts/build_pilot_site.py
(never `python -m`, never with PYTHONPATH=. — the repo's logging/ package
shadows stdlib logging when the root is sys.path[0]).

The parent page itself (HTML/CSS/JS) is hand-authored in the buju_website
repo under pilot/ — this script only produces the data + explorer artifacts
that get copied there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import build_story_explorer as bse  # same directory; reuse loader + validator

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "story_definitions" / "preview" / "pilot_site"
EXPLORER_HTML = REPO_ROOT / "story_definitions" / "preview" / "story_explorer.html"

# Split markers for the single inline <script> in the built explorer.
# split/join only — no regex, no .replace() (see STORY_EXPLORER_SPEC.md).
SCRIPT_OPEN = "<script>"
SCRIPT_CLOSE = "</script>"


def _reading_minutes(story: dict[str, Any]) -> int:
    """Rough read-aloud minutes for the longest path (~140 wpm aloud)."""
    segments = {seg["id"]: seg for seg in story["segments"]}
    words_a = 0
    words_b = 0
    for seg_id, seg in segments.items():
        n = len(seg["text"].split())
        if seg_id.endswith("a"):
            words_a += n
        elif seg_id.endswith("b"):
            words_b += n
        else:
            words_a += n
            words_b += n
    minutes = max(words_a, words_b) / 140.0
    return max(2, round(minutes))


def build_parent_data(stories: list[dict[str, Any]]) -> dict[str, Any]:
    registry = bse.load_default_registry()
    topics: dict[str, str] = {}
    out_stories: list[dict[str, Any]] = []
    for story in sorted(stories, key=lambda s: (s["title"])):
        topic_id = story["topics"]["knowledge_domain"]
        if topic_id not in topics:
            node = registry.get_node(topic_id)
            topics[topic_id] = node.display_name if node else topic_id.split(".")[-1]
        segments = {
            seg["id"]: {"text": seg["text"], "next": seg["next"]}
            for seg in story["segments"]
        }
        choices = {
            cp["id"]: {
                "question": cp["question"],
                "rejoins": cp["rejoins"],
                "options": [
                    {
                        "say_word": opt["say_word"],
                        "label": opt["label"],
                        "next_segment": opt["next_segment"],
                        "sets_slots": opt.get("sets_slots", {}),
                    }
                    for opt in cp["options"]
                ],
            }
            for cp in story["choice_points"]
        }
        slots = {
            name: {
                "role": slot["role"],
                "kind": slot["kind"],
                "ask_child": slot["ask_child"],
                "default": slot["default"],
            }
            for name, slot in story["slots"].items()
        }
        out_stories.append(
            {
                "id": story["id"],
                "title": story["title"],
                "age_band": story["age_band"],
                "topic": topic_id,
                "depth": story["depth"],
                "minutes": _reading_minutes(story),
                "start": story["start_segment"],
                "segments": segments,
                "choices": choices,
                "slots": slots,
            }
        )
    return {"topics": topics, "stories": out_stories}


def split_explorer() -> None:
    html = EXPLORER_HTML.read_text(encoding="utf-8")
    head, _, rest = html.partition(SCRIPT_OPEN)
    script, _, tail = rest.rpartition(SCRIPT_CLOSE)
    if not script:
        raise SystemExit("could not find inline <script> in story_explorer.html")
    out = OUT_DIR / "explorer"
    out.mkdir(parents=True, exist_ok=True)
    (out / "explorer.js").write_text(script, encoding="utf-8")
    parts = [head, '<script src="./explorer.js" defer>', SCRIPT_CLOSE, tail]
    (out / "index.html").write_text("".join(parts), encoding="utf-8")


def main() -> int:
    # Rebuild the explorer first so the split copy is never stale.
    if bse.main() != 0:
        return 1
    stories = bse.load_stories()
    data = build_parent_data(stories)
    out = OUT_DIR / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stories.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    split_explorer()
    n = len(data["stories"])
    t = len(data["topics"])
    print(f"wrote pilot_site: {n} stories, {t} topics -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
