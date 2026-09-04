"""Write the transcript-parity fixture that buju_website's tests check.

    python scripts/build_transcript_fixture.py

story_audio_chunks.py (Python, generation) and buju_website/api/
pilot-name-audio.js (JS, live name re-voicing) build the SAME transcript for
the same paragraph, or a renamed paragraph lands with different pacing than
its neighbours. This picks real paragraphs from the library — every one that
contains an abbreviation, ellipsis, dash, quote, slot or asterisk, plus a
plain sample — runs them through the Python side under several settings,
and writes the results to

    buju_website/tests/pilot/fixtures/transcript_parity.json

`node tests/pilot/test_transcript.js` then asserts the JS gives byte-identical
output. Re-run this whenever story_audio_chunks.py changes; the website test
failing at publish time is the point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build_story_explorer as bse
import story_audio_chunks

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = (
    REPO_ROOT.parent / "buju_website" / "tests" / "pilot" / "fixtures"
    / "transcript_parity.json"
)
# (sentence_pause_ms, short_sentence_chars, short_sentence_pause_ms)
SETTINGS = [(400, 0, None), (300, 25, 200), (300, 25, 0)]
# Rare constructs the boundary rule has opinions about. Ordinary quotes,
# "!" and "?" are in nearly every paragraph, so those come in via the sample.
INTERESTING = ("Mr.", "Mrs.", "Dr.", "St.", "Ms.", "…", "...", ".)", '."', "!\"", "?\"", "{", "*", "?!", "!!")
PLAIN_SAMPLE_EVERY = 45
MAX_INTERESTING = 200


def main() -> int:
    chunks: list[dict] = []
    plain = 0
    for story in sorted(bse.load_stories(), key=lambda s: s["id"]):
        slots = story.get("slots") or {}
        units = [(s["id"], s["text"]) for s in story["segments"]]
        units += [(c["id"], c["question"]) for c in story["choice_points"]]
        for unit_id, prose in units:
            for index, chunk in enumerate(story_audio_chunks.paragraph_chunks(prose)):
                interesting = any(marker in chunk for marker in INTERESTING)
                plain += 1
                if interesting:
                    if sum(1 for c in chunks if c["why"] == "interesting") >= MAX_INTERESTING:
                        interesting = False
                if not interesting and plain % PLAIN_SAMPLE_EVERY:
                    continue
                spoken = story_audio_chunks.substitute_slot_values(chunk, slots, {})
                chunks.append(
                    {
                        "story": story["id"].rsplit(".", 1)[-1],
                        "unit": unit_id,
                        "i": index,
                        "why": "interesting" if interesting else "sample",
                        "text": chunk,
                        "slots": {name: slot["default"] for name, slot in slots.items()},
                        "spoken": spoken,
                        "transcripts": [
                            story_audio_chunks.to_transcript(spoken, pause, short_chars, short_pause)
                            for pause, short_chars, short_pause in SETTINGS
                        ],
                    }
                )
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps({"settings": SETTINGS, "chunks": chunks}, ensure_ascii=False, indent=0)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(chunks)} chunks x {len(SETTINGS)} settings to {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
