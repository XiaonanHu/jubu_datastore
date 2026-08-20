#!/usr/bin/env python3
"""Validate a course-mode story against course_definitions/course_bands.yaml.

Run from the repo root as a script (never `python -m`, never PYTHONPATH=.):

    python scripts/check_course_story.py story_definitions/stories/courses/<file>.json

Reports every band metric plus the SEL and structural invariants.
Exit 1 if anything BLOCKS.
"""
import json, re, sys, yaml
from pathlib import Path

# --------------------------------------------------------------------------
# Dolch corpus, kept in its published tiers.
# A word being "known" depends on the BAND: a Pre-K text that leans on
# 3rd-grade sight words is not a Pre-K text, even if coverage looks high.
# --------------------------------------------------------------------------
PRE_PRIMER = set("""a and away big blue can come down find for funny go help here i in is it jump
little look make me my not one play red run said see the three to two up we where yellow you""".split())
PRIMER = set("""all am are at ate be black brown but came did do eat four get good have he into like
must new no now on our out please pretty ran ride saw say she so soon that there they this too under
want was well went what white who will with yes""".split())
FIRST = set("""after again an any as ask by could every fly from give going had has her him his how just
know let live may of old once open over put round some stop take thank them then think walk were when""".split())
SECOND = set("""always around because been before best both buy call cold does don't fast first five found
gave goes green its made many off or pull read right sing sit sleep tell their these those upon us use
very wash which why wish work would write your""".split())
THIRD = set("""about better bring carry clean cut done draw drink eight fall far full got grow hold hot hurt
if keep kind laugh light long much myself never only own pick seven shall show six small start ten today
together try warm""".split())
NOUNS = set("""apple baby back ball bear bed bell bird birthday boat box boy bread brother cake car cat chair
chicken children coat corn cow day dog doll door duck egg eye farm farmer father feet fire fish floor flower
game garden girl grass ground hand head hill home horse house kitty leg letter man men milk money morning
mother name nest night paper party picture pig rabbit rain ring robin school seed sheep shoe sister snow song
squirrel stick street sun table thing time top toy tree watch water way wind window""".split())

BAND_SIGHT_POOL = {
    "3-4":   PRE_PRIMER,
    "5-6":   PRE_PRIMER | PRIMER | NOUNS,
    "7-8":   PRE_PRIMER | PRIMER | FIRST | SECOND | NOUNS,
    "9-10":  PRE_PRIMER | PRIMER | FIRST | SECOND | THIRD | NOUNS,
    "11-12": PRE_PRIMER | PRIMER | FIRST | SECOND | THIRD | NOUNS,
}

ALL_DOLCH = PRE_PRIMER | PRIMER | FIRST | SECOND | THIRD | NOUNS

BANNED = r"\b(assessment|mastery|milestone|delayed|gifted|grade\s+level)\b"


# ---------------------------------------------------------------- tokenising
def normalize_word(w: str) -> str:
    w = w.lower().strip(".,!?;:\"'“”‘’")
    if w.endswith("'s"):
        w = w[:-2]
    return w


def word_stems(w: str) -> set[str]:
    """Base forms to test against a sight-word pool.

    Only regular inflections are stripped. Blindly calling rstrip('s') turns
    'grass' into 'gra' and 'this' into 'thi', which silently fails words that
    ARE on the list.
    """
    base = normalize_word(w)
    out = {base}
    if base.endswith("es") and len(base) > 3:
        out.add(base[:-2])
        out.add(base[:-1])
    elif base.endswith("s") and not base.endswith("ss") and len(base) > 2:
        out.add(base[:-1])
    elif base.endswith("ed") and len(base) > 3:
        out.add(base[:-2]); out.add(base[:-1])
    elif base.endswith("ing") and len(base) > 4:
        out.add(base[:-3]); out.add(base[:-3] + "e")
    return out


def syllables(w: str) -> int:
    w = normalize_word(w)
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    n = len(re.findall(r"[aeiouy]+", w))
    # Silent terminal 'e' — except consonant + le, where the l is syllabic:
    # lit-tle and can-dle are two syllables, not one.
    if w.endswith("e") and not re.search(r"[bcdfghjklmnpqrstvwxyz]le$", w):
        if n > 1:
            n -= 1
    return max(1, n)


def sentences(t: str) -> list[str]:
    """Split on sentence enders, protecting honorifics and ellipses.

    'Mr. Bear looked up.' is one sentence; splitting it into 'Mr.' + 'Bear
    looked up.' drags mean sentence length down and can turn a failing text
    into a passing one.
    """
    s = re.sub(r"\b(Mr|Mrs|Ms|Dr|St)\.", r"\1<DOT>", t)
    s = re.sub(r"\.{3}", "…", s)
    parts = [p for p in re.split(r'(?<=[.!?])["”’\']?\s+', s.strip()) if p.strip()]
    return [p.replace("<DOT>", ".") for p in parts]


def words(t: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", t)


# ------------------------------------------------------------------ traversal
def all_paths(story: dict) -> list[list[str]]:
    """Walk the braid from start_segment to every ending.

    Hardcoding ['s1','s2a','s3','s4a'] breaks the moment an author or a model
    names a segment 'intro' or 'choice_left'.
    """
    segs = {s["id"]: s for s in story["segments"]}
    cps = {c["id"]: c for c in story["choice_points"]}
    out: list[list[str]] = []

    def walk(node_id: str, acc: list[str], seen: set[str]) -> None:
        if node_id in seen:                      # cycle guard
            out.append(acc + [f"<cycle:{node_id}>"]); return
        if node_id in cps:
            for opt in cps[node_id]["options"]:
                walk(opt["next_segment"], list(acc), set(seen))
            return
        seg = segs.get(node_id)
        if seg is None:
            out.append(acc + [f"<missing:{node_id}>"]); return
        acc = acc + [node_id]; seen = seen | {node_id}
        nxt = seg.get("next")
        if not nxt:
            out.append(acc); return
        walk(nxt["id"], acc, seen)

    walk(story["start_segment"], [], set())
    return out


# ----------------------------------------------------------------------- main
def main(story_path: str, bands_path: str | None = None) -> int:
    story = json.loads(Path(story_path).read_text())
    if bands_path is None:
        here = Path(story_path).resolve()
        for parent in here.parents:
            cand = parent / "course_definitions" / "course_bands.yaml"
            if cand.exists():
                bands_path = str(cand); break
        else:
            bands_path = "course_bands.yaml"
    cfg = yaml.safe_load(Path(bands_path).read_text())["bands"][story["age_band"]]
    pool = BAND_SIGHT_POOL[story["age_band"]]
    segs = {s["id"]: s for s in story["segments"]}
    slots = story.get("slots", {})
    course = story.get("course", {})

    blocks, warns, info = [], [], []

    # -- structure ---------------------------------------------------------
    if len(story["choice_points"]) != cfg["choice_points"]:
        blocks.append(f"{len(story['choice_points'])} choice points, band wants {cfg['choice_points']}")
    for c in story["choice_points"]:
        if len(c["options"]) != 2:
            blocks.append(f"{c['id']}: needs exactly 2 options")
        sw = [o["say_word"].lower() for o in c["options"]]
        if len(set(sw)) != len(sw):
            blocks.append(f"{c['id']}: say-words not distinct")
        elif sw[0][0] == sw[1][0]:
            warns.append(f"{c['id']}: say-words '{sw[0]}'/'{sw[1]}' start with the same letter")
    if not story["choice_points"][0]["rejoins"]:
        blocks.append("first choice must rejoin")
    if story["choice_points"][-1]["rejoins"]:
        blocks.append("final choice must split")

    paths = all_paths(story)
    for p in paths:
        bad = [x for x in p if x.startswith("<")]
        if bad:
            blocks.append(f"broken path: {' -> '.join(p)}")
    endings = {p[-1] for p in paths if not p[-1].startswith("<")}
    if len(endings) != 2:
        blocks.append(f"expected 2 distinct endings, found {sorted(endings)}")
    unreachable = set(segs) - {n for p in paths for n in p}
    if unreachable:
        blocks.append(f"unreachable segments: {sorted(unreachable)}")

    # -- slots -------------------------------------------------------------
    blob = json.dumps(story["segments"]) + json.dumps(story["choice_points"])
    used = set(re.findall(r"\{(\w+)\}", blob))
    if used - set(slots):
        blocks.append(f"slot used but not declared: {sorted(used - set(slots))}")
    if set(slots) - used:
        blocks.append(f"slot declared but never used: {sorted(set(slots) - used)}")
    if len(slots) > 5:
        blocks.append(f"{len(slots)} slots; cap is 5")

    # -- course invariants -------------------------------------------------
    if story.get("mode") == "course":
        if not course.get("sel_theme"):
            blocks.append("course story has no sel_theme")
        if not course.get("sub_skill"):
            blocks.append("course story has no sub_skill")
        if len(course.get("checks", [])) != 3:
            blocks.append("need exactly 3 checks: recognition, strategy_recall, transfer")
        tiers = [c.get("tier") for c in course.get("checks", [])]
        if tiers and tiers != ["recognition", "strategy_recall", "transfer"]:
            blocks.append(f"checks must be in order recognition/strategy_recall/transfer, got {tiers}")
        # A knowledge_domain tag is the SETTING, not a second objective. It is
        # allowed and encouraged. What is forbidden is a second thing to assess.
        if story["topics"].get("knowledge_domain"):
            info.append(f"setting: {story['topics']['knowledge_domain']} (not assessed)")
        else:
            warns.append("no knowledge_domain setting — the story has nowhere interesting to happen")
        if any(c.get("assesses") == "knowledge" for c in course.get("checks", [])):
            blocks.append("a check assesses knowledge; course checks assess the SEL sub-skill only")
        # the strategy must sit where every path crosses it
        common = set(paths[0]).intersection(*[set(p) for p in paths[1:]]) if len(paths) > 1 else set(paths[0])
        common -= {story["start_segment"]}
        if not common:
            blocks.append("no segment is shared by every path — the strategy cannot land for every reader")
        else:
            info.append(f"shared by every path: {sorted(common)}")

    # -- banned language in prose -----------------------------------------
    prose = " ".join(s["text"] for s in story["segments"])
    for m in re.finditer(BANNED, prose, re.I):
        blocks.append(f"banned evaluation word in prose: {m.group(0)!r}")

    # -- per-path linguistics ---------------------------------------------
    print(f"\n{story['title']}   band {story['age_band']}   grade {cfg['grade_view']}   {cfg.get('lexile_band','')}")
    print(f"SEL: {course.get('sel_theme')} / {course.get('sub_skill')}")
    print(f"Setting: {story['topics'].get('knowledge_domain') or '(none)'}\n")
    hdr = (f"{'path':>22} {'words':>6} {'target':>12} {'MSL':>6} {'target':>12} "
           f"{'band%':>6} {'tgt':>4} {'all%':>6} {'syl':>5} {'max':>5}")
    print(hdr); print("-" * len(hdr))

    lo, hi = cfg["words_per_path"]; mlo, mhi = cfg["mean_sentence_length"]
    for p in paths:
        if any(x.startswith("<") for x in p):
            continue
        text = " ".join(segs[n]["text"] for n in p)
        text = re.sub(r"\{(\w+)\}", lambda m: slots[m.group(1)]["default"], text)
        w, s = words(text), sentences(text)
        msl = len(w) / len(s)
        sight = 100 * sum(1 for x in w if word_stems(x) & pool) / len(w)
        sight_all = 100 * sum(1 for x in w if word_stems(x) & ALL_DOLCH) / len(w)
        syl = sum(syllables(x) for x in w) / len(w)
        ok = lo <= len(w) <= hi and mlo <= msl <= mhi
        label = "→".join(p)
        print(f"{label:>22} {len(w):>6} {str([lo,hi]):>12} {msl:>6.1f} {str([mlo,mhi]):>12} "
              f"{sight:>6.1f} {cfg['sight_word_target_pct']:>4} {sight_all:>6.1f} {syl:>5.2f} "
              f"{cfg['syllables_per_word_avg_max']:>5.2f}" + ("" if ok else "   <-- OUT"))
        if not (lo <= len(w) <= hi):
            blocks.append(f"{label}: {len(w)} words, band is {lo}-{hi}")
        if not (mlo <= msl <= mhi):
            blocks.append(f"{label}: MSL {msl:.1f}, band is {mlo}-{mhi}")
        if syl > cfg["syllables_per_word_avg_max"]:
            warns.append(f"{label}: {syl:.2f} syllables/word over {cfg['syllables_per_word_avg_max']}")
        if sight < cfg["sight_word_target_pct"]:
            warns.append(f"{label}: band-gated sight words {sight:.1f}% under target "
                         f"{cfg['sight_word_target_pct']}% (full Dolch corpus: {sight_all:.1f}%)")

    # -- every non-sight word should be glossed ---------------------------
    glossed = {g["word"].lower() for g in course.get("glossary", [])}
    names = {v["default"].lower() for v in slots.values()} | {"pip"}
    missing = set()
    for seg in story["segments"]:
        t = re.sub(r"\{(\w+)\}", lambda m: slots[m.group(1)]["default"], seg["text"])
        for x in words(t):
            b = normalize_word(x)
            if b in names or (word_stems(x) & ALL_DOLCH):
                continue   # upper-tier Dolch is a "next sight word", not vocabulary
            if not (word_stems(x) & glossed):
                missing.add(b)
    if missing:
        blocks.append(f"content words with no glossary entry: {sorted(missing)}")
    else:
        info.append("every content word has a glossary entry")

    print()
    for i in info:  print(f"  info  {i}")
    for w_ in warns: print(f"  WARN  {w_}")
    for b in blocks: print(f"  BLOCK {b}")
    print("\n  band%% = Dolch tiers this band should know; all%% = full 315-word corpus.")
    print(f"\n{'FAIL' if blocks else 'PASS'} — {len(blocks)} blocking, {len(warns)} warnings")
    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
