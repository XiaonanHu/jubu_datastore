"""
Validate the pilot branching stories and build the interactive explorer page.

    python scripts/build_story_explorer.py --check   # validate only
    python scripts/build_story_explorer.py           # validate + build HTML

Output: story_definitions/preview/story_explorer.html — a self-contained
page showing the pilot topic subset as a map; clicking a topic shows its
story shelf; clicking a story opens a player that walks the braid, asks the
child-nameable slots, and offers each choice (buttons plus a free-text
"say it" box standing in for the voice pipeline).

Run as a script (not `python -m` from the repo root): repo root on
sys.path[0] makes the package's logging/ subpackage shadow stdlib logging.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from jubu_datastore.knowledge_graph.graph_loader import load_default_registry
from jubu_datastore.knowledge_graph.graph_validator import BANNED_LANGUAGE_PATTERNS

REPO_ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = REPO_ROOT / "story_definitions" / "stories" / "pilot"
OUTPUT_PATH = REPO_ROOT / "story_definitions" / "preview" / "story_explorer.html"

KNOWN_PATTERNS = {
    "problem_and_fix",
    "journey",
    "mystery",
    "dilemma",
    "inner_weather",
    "quiet_hour",
    "romp",
    "make_and_build",
}
KNOWN_TELLERS = {"we_adventure", "named_hero", "storyteller_tale"}
MAXIMUM_SLOTS_PER_STORY = 5

_DATA_PLACEHOLDER = "__EXPLORER_DATA_JSON__"


def _check(condition: bool, issues: list[str], message: str) -> None:
    if not condition:
        issues.append(message)


def validate_story(story: dict[str, Any], topic_ids: set[str]) -> list[str]:
    """All structural rules for one pilot story; empty list means valid."""
    issues: list[str] = []
    story_id = story.get("id", "<missing id>")

    def flag(message: str) -> None:
        issues.append(f"{story_id}: {message}")

    for key in (
        "id",
        "title",
        "age_band",
        "topics",
        "pattern",
        "teller",
        "tone",
        "spine",
        "slots",
        "start_segment",
        "segments",
        "choice_points",
        "status",
    ):
        _check(key in story, issues, f"{story_id}: missing key {key!r}")
    if issues:
        return issues

    _check(
        story["pattern"] in KNOWN_PATTERNS,
        issues,
        f"{story_id}: unknown pattern {story['pattern']!r}",
    )
    _check(
        story["teller"] in KNOWN_TELLERS,
        issues,
        f"{story_id}: unknown teller {story['teller']!r}",
    )
    main_topic = story["topics"].get("knowledge_domain")
    _check(
        main_topic in topic_ids,
        issues,
        f"{story_id}: unknown main topic {main_topic!r}",
    )

    segments = {segment["id"]: segment for segment in story["segments"]}
    choices = {choice["id"]: choice for choice in story["choice_points"]}
    _check(
        len(segments) == len(story["segments"]),
        issues,
        f"{story_id}: duplicate segment ids",
    )
    _check(
        story["start_segment"] in segments,
        issues,
        f"{story_id}: start segment missing",
    )

    endings = [s for s in story["segments"] if s["next"] is None]
    _check(len(endings) == 2, issues, f"{story_id}: expected 2 endings")

    for segment in story["segments"]:
        nxt = segment["next"]
        if nxt is None:
            continue
        if nxt["kind"] == "segment":
            _check(
                nxt["id"] in segments,
                issues,
                f"{story_id}: {segment['id']} points at unknown segment",
            )
        elif nxt["kind"] == "choice":
            _check(
                nxt["id"] in choices,
                issues,
                f"{story_id}: {segment['id']} points at unknown choice",
            )
        else:
            flag(f"segment {segment['id']} has unknown next kind")

    final_choice_ids = set()
    for choice in story["choice_points"]:
        options = choice["options"]
        _check(
            len(options) == 2,
            issues,
            f"{story_id}: choice {choice['id']} needs exactly 2 options",
        )
        say_words = {option["say_word"].strip().lower() for option in options}
        _check(
            len(say_words) == len(options),
            issues,
            f"{story_id}: choice {choice['id']} say-words not distinct",
        )
        targets = []
        for option in options:
            _check(
                option["next_segment"] in segments,
                issues,
                f"{story_id}: option in {choice['id']} points at unknown segment",
            )
            targets.append(option["next_segment"])
        if choice["rejoins"]:
            merge_points = {
                json.dumps(segments[target]["next"], sort_keys=True)
                for target in targets
                if target in segments
            }
            _check(
                len(merge_points) == 1,
                issues,
                f"{story_id}: rejoining choice {choice['id']} branches do not converge",
            )
        else:
            final_choice_ids.add(choice["id"])
    _check(
        len(final_choice_ids) == 1,
        issues,
        f"{story_id}: expected exactly one splitting (final) choice",
    )

    declared_slots = set(story["slots"])
    _check(
        len(declared_slots) <= MAXIMUM_SLOTS_PER_STORY,
        issues,
        f"{story_id}: more than {MAXIMUM_SLOTS_PER_STORY} slots",
    )
    used_slots = set()
    for segment in story["segments"]:
        text = segment["text"]
        start = 0
        while True:
            open_brace = text.find("{", start)
            if open_brace == -1:
                break
            close_brace = text.find("}", open_brace)
            if close_brace == -1:
                break
            used_slots.add(text[open_brace + 1 : close_brace])
            start = close_brace + 1
    _check(
        used_slots <= declared_slots,
        issues,
        f"{story_id}: undeclared slots used: {sorted(used_slots - declared_slots)}",
    )
    _check(
        declared_slots <= used_slots,
        issues,
        f"{story_id}: declared slots never used: {sorted(declared_slots - used_slots)}",
    )
    set_slots = {
        slot
        for choice in story["choice_points"]
        for option in choice["options"]
        for slot in option["sets_slots"]
    }
    _check(
        set_slots <= declared_slots,
        issues,
        f"{story_id}: options set undeclared slots: "
        f"{sorted(set_slots - declared_slots)}",
    )

    display_texts = [story["title"], story["spine"]]
    display_texts += [segment["text"] for segment in story["segments"]]
    for choice in story["choice_points"]:
        display_texts.append(choice["question"])
        display_texts += [option["label"] for option in choice["options"]]
    for text in display_texts:
        for pattern, reason in BANNED_LANGUAGE_PATTERNS:
            match = pattern.search(text)
            if match:
                flag(f"banned language {match.group(0)!r} ({reason})")

    return issues


def load_stories() -> list[dict[str, Any]]:
    if not STORIES_DIR.is_dir():
        raise SystemExit(f"no pilot stories directory at {STORIES_DIR}")
    stories = []
    for path in sorted(STORIES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            stories.append(json.load(f))
    return stories


# The focused R&D view: a few categories, each with its deep dives around it.
PILOT_CATEGORIES = [
    "knowledge_domain.ocean_animals",
    "knowledge_domain.insects",
    "knowledge_domain.planets",
    "knowledge_domain.dinosaurs",
    "knowledge_domain.volcanoes",
    "knowledge_domain.computers_and_code",
    "knowledge_domain.musical_instruments",
    "knowledge_domain.drawing_and_animation",
    "knowledge_domain.shapes_and_symmetry",
    "knowledge_domain.farms_and_food",
    "knowledge_domain.maps_and_globes",
    "knowledge_domain.engines_and_vehicles",
    "knowledge_domain.oceans_and_tides",
    "knowledge_domain.frogs_and_amphibians",
    "knowledge_domain.theater_and_pretending",
]
# The map is drawn in 3D and orbited by the viewer, so positions are points
# on nested spheres: categories on a big one, their deep dives on small ones.
CATEGORY_SPHERE_RADIUS = 215.0
DEEP_DIVE_SPHERE_RADIUS = 108.0
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def _sphere_points(count: int, radius: float) -> list[tuple[float, float, float]]:
    """Evenly spread points on a sphere (Fibonacci lattice)."""
    points = []
    for index in range(count):
        y = 1.0 - 2.0 * (index + 0.5) / count
        ring = math.sqrt(max(0.0, 1.0 - y * y))
        theta = GOLDEN_ANGLE * index
        points.append(
            (
                round(radius * ring * math.cos(theta), 2),
                round(radius * y, 2),
                round(radius * ring * math.sin(theta), 2),
            )
        )
    return points


def build_explorer_data(stories: list[dict[str, Any]]) -> dict[str, Any]:
    """Categories + deep dives as 3D points, with edges and stories."""
    registry = load_default_registry()
    stories_by_topic: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        stories_by_topic.setdefault(story["topics"]["knowledge_domain"], []).append(
            story
        )

    topics: list[dict[str, Any]] = []
    shown: dict[str, dict[str, Any]] = {}
    category_points = _sphere_points(len(PILOT_CATEGORIES), CATEGORY_SPHERE_RADIUS)

    for cluster_index, category_id in enumerate(PILOT_CATEGORIES):
        category = registry.get_node(category_id)
        cx, cy, cz = category_points[cluster_index]
        treatment = registry.effective_treatment(category.id, 6)
        entry = {
            "id": category.id,
            "display_name": category.display_name,
            "tier": "curriculum",
            "cluster": cluster_index,
            "parent": None,
            "facets": [],
            "framing": treatment.framing if treatment else "",
            "vocabulary": list(treatment.vocabulary) if treatment else [],
            "avoid": registry.effective_avoid_list(category.id, 6),
            "stories": len(stories_by_topic.get(category.id, [])),
            "x": cx,
            "y": cy,
            "z": cz,
        }
        topics.append(entry)
        shown[category.id] = entry

        children = sorted(registry.children_of(category.id), key=lambda n: n.id)
        child_points = _sphere_points(len(children), DEEP_DIVE_SPHERE_RADIUS)
        for child_index, child in enumerate(children):
            dx, dy, dz = child_points[child_index]
            child_treatment = registry.effective_treatment(child.id, 6)
            child_entry = {
                "id": child.id,
                "display_name": child.display_name,
                "tier": "deep_dive",
                "cluster": cluster_index,
                "parent": category.id,
                "facets": list(child.facets),
                "framing": child_treatment.framing if child_treatment else "",
                "vocabulary": (
                    list(child_treatment.vocabulary) if child_treatment else []
                ),
                "avoid": registry.effective_avoid_list(child.id, 6),
                "stories": len(stories_by_topic.get(child.id, [])),
                "x": round(cx + dx, 2),
                "y": round(cy + dy, 2),
                "z": round(cz + dz, 2),
            }
            topics.append(child_entry)
            shown[child.id] = child_entry

    edges: list[dict[str, Any]] = []
    for topic in topics:
        if topic["parent"]:
            edges.append(
                {
                    "source": topic["parent"],
                    "target": topic["id"],
                    "kind": "subtopic",
                    "cross": False,
                }
            )
    seen_pairs: set[tuple[str, str]] = set()
    for topic_id in shown:
        node = registry.get_node(topic_id)
        for neighbor_id in node.edges.adjacent:
            if neighbor_id not in shown:
                continue
            first, second = sorted((topic_id, neighbor_id))
            pair = (first, second)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append(
                {
                    "source": first,
                    "target": second,
                    "kind": "adjacent",
                    "cross": shown[first]["cluster"] != shown[second]["cluster"],
                }
            )

    shown_stories = [
        story for story in stories if story["topics"]["knowledge_domain"] in shown
    ]
    return {
        "topics": topics,
        "edges": edges,
        "stories": shown_stories,
        "categories": [
            {"id": cid, "cluster": i, "display_name": shown[cid]["display_name"]}
            for i, cid in enumerate(PILOT_CATEGORIES)
        ],
    }


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Buju Story Explorer</title>
<style>
  :root {
    --blue:#0A5CD1; --blue-soft:#5C9BE9; --blue-pale:#CAE0F8;
    --orange:#F66700; --orange-soft:#FF9F58; --orange-pale:#FFD9BD;
    --green:#0BA671; --green-soft:#42CDA6; --green-pale:#C8ECE2;
    --black:#1A1A1A; --almond:#FFF3EA; --line:#ece6e0;
  }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html,body { margin:0; height:100%; }
  body { display:flex; overflow:hidden; color:var(--black);
    background:var(--almond);
    font-family:Poppins,Quicksand,-apple-system,"Segoe UI",Roboto,sans-serif; }
  h1,h2,h3,h4 { font-family:Quicksand,Poppins,sans-serif; font-weight:700; }
  #left { flex:1 1 56%; position:relative;
    background:radial-gradient(circle at 42% 38%, #ffffff 0%, #fdf6ef 52%, #f6ece2 100%); }
  #right { flex:1 1 44%; overflow-y:auto; padding:22px 26px 70px;
    background:var(--almond); border-left:1px solid var(--line); }
  svg#map { width:100%; height:100%; display:block; cursor:grab; touch-action:none; }
  svg#map.drag { cursor:grabbing; }
  #maptop { position:absolute; top:16px; left:20px; pointer-events:none; }
  #maptop h1 { font-size:20px; margin:0; letter-spacing:-.2px; }
  #maptop .tag { font-size:11.5px; color:#8d857a; margin-top:2px; }
  .float { position:absolute; background:rgba(255,255,255,.86);
    backdrop-filter:blur(6px); border:1px solid rgba(0,0,0,.05);
    border-radius:14px; font-size:11.5px; color:#7f776c; padding:8px 12px;
    pointer-events:none; }
  .float.clickable { pointer-events:auto; cursor:pointer; }
  #maphint { left:20px; bottom:16px; }
  #legend { right:20px; bottom:16px; line-height:1.7; }
  #legend .sw { display:inline-block; width:10px; height:10px; border-radius:50%;
    margin-right:5px; vertical-align:-1px; }
  #resetview { right:20px; top:16px; cursor:pointer; font-weight:600; color:var(--blue); }
  h2 { font-size:21px; margin:0 0 6px; }
  .chip { display:inline-block; border-radius:20px; padding:3px 11px; font-size:11.5px;
    margin:0 5px 5px 0; background:#fff; border:1px solid var(--line);
    color:#5b544b; font-weight:600; }
  .chip.tier { background:var(--green-pale); border-color:transparent; color:#065c40; }
  .chip.warn { background:var(--orange-pale); border-color:transparent; color:#8a3b00; }
  .chip.vocab { background:var(--blue-pale); border-color:transparent; color:#0b3d84; }
  .framing { background:#fff; border:1px solid var(--line); border-left:5px solid var(--blue);
    border-radius:12px; padding:13px 16px; font-size:14.5px; margin:12px 0 16px;
    box-shadow:0 2px 10px rgba(26,26,26,.04); }
  .lab { font-size:10.5px; text-transform:uppercase; letter-spacing:.09em;
    color:#a29a8e; margin:16px 0 7px; font-weight:700; }
  .card { background:#fff; border:1px solid var(--line); border-radius:16px;
    padding:15px 17px; margin-bottom:11px; cursor:pointer;
    box-shadow:0 2px 10px rgba(26,26,26,.04); transition:transform .12s, box-shadow .12s; }
  .card:hover { transform:translateY(-2px); box-shadow:0 6px 18px rgba(10,92,209,.12); }
  .card h3 { margin:0 0 8px; font-size:16.5px; }
  .empty-note { color:#a29a8e; font-size:13.5px; font-style:italic; }
  #tabs { display:flex; gap:8px; margin:6px 0 16px; }
  .tab { border:1.5px solid var(--line); background:#fff; border-radius:20px;
    padding:7px 16px; font-size:13px; cursor:pointer; font-weight:600; color:#6b645b;
    font-family:inherit; }
  .tab.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .seg { background:#fff; border:1px solid var(--line); border-radius:16px;
    padding:19px 21px; font-size:16.5px; line-height:1.72; margin-bottom:12px;
    box-shadow:0 2px 10px rgba(26,26,26,.04); }
  .question { font-size:16px; font-weight:700; margin:16px 0 11px;
    font-family:Quicksand,Poppins,sans-serif; }
  .opt { display:block; width:100%; text-align:left; background:#fff; font-family:inherit;
    border:2px solid var(--blue); color:var(--black); border-radius:16px; padding:13px 17px;
    font-size:15.5px; margin-bottom:9px; cursor:pointer; }
  .opt:hover { background:var(--blue-pale); }
  .opt .say { color:#8d857a; font-size:12.5px; }
  #sayrow { display:flex; gap:8px; margin-top:4px; }
  #saybox { flex:1; border:1.5px solid #ded6cd; border-radius:14px; padding:11px 14px;
    font-size:14.5px; font-family:inherit; }
  #saygo { border:none; background:var(--green); color:#fff; border-radius:14px;
    padding:0 20px; font-size:14px; cursor:pointer; font-family:inherit; font-weight:600; }
  .namebox { background:#fff; border:1px solid var(--orange-soft);
    border-left:5px solid var(--orange); border-radius:14px; padding:15px 17px;
    margin-bottom:14px; }
  .namebox input { border:1.5px solid var(--orange-soft); border-radius:10px;
    padding:9px 12px; font-size:15px; margin-right:8px; font-family:inherit; }
  .btn { border:none; background:var(--blue); color:#fff; border-radius:14px;
    padding:11px 19px; font-size:14.5px; cursor:pointer; margin:4px 8px 0 0;
    font-family:inherit; font-weight:600; }
  .btn.ghost { background:#f1ebe4; color:var(--black); }
  .ending { background:var(--green-pale); border:1px solid var(--green-soft);
    border-radius:16px; padding:17px 19px; margin-top:6px; }
  .recap { color:#3f6d5b; font-size:13.5px; margin-top:8px; }
  #back { color:var(--blue); cursor:pointer; font-size:13.5px; margin-bottom:12px;
    display:none; font-weight:600; }
  .dec { background:#fff; border:1px solid var(--line); border-radius:16px;
    padding:15px 18px; margin-bottom:12px; box-shadow:0 2px 10px rgba(26,26,26,.04); }
  .dec h4 { margin:0 0 10px; font-size:14.5px; }
  .dec p { margin:5px 0; font-size:14px; line-height:1.55; }
  .kv { font-size:13.5px; margin:5px 0; }
  .kv b { color:#5b544b; font-weight:600; }
  .bar { display:flex; align-items:center; gap:9px; margin:5px 0; font-size:12.5px; }
  .bar .nm { width:122px; color:#5b544b; }
  .bar .track { flex:1; background:#f2ece5; border-radius:7px; height:16px; }
  .bar .fill { background:var(--blue-soft); height:100%; border-radius:7px; }
  .bar.win .fill { background:linear-gradient(90deg,var(--blue),var(--blue-soft)); }
  .bar.out .fill { background:#e2dad1; }
  .bar .val { width:40px; text-align:right; color:#8d857a; }
  .why { color:#7f776c; font-size:12.5px; margin:2px 0 8px 0; font-style:italic; }
  .why.ind { margin-left:131px; }
  ul.tight { margin:5px 0; padding-left:20px; font-size:13.5px; line-height:1.58; }
  .braid { background:#fff; border:1px solid var(--line); border-radius:16px; padding:17px; }
  .pass { color:#065c40; font-weight:700; }
  .alltopics { display:flex; flex-direction:column; gap:10px; }
  .tgroup-name { font-size:11.5px; font-weight:700; margin-bottom:4px;
    font-family:Quicksand,Poppins,sans-serif; }
  .tpill { display:inline-block; border:1.5px solid var(--line); background:#fff;
    border-radius:20px; padding:3px 10px; font-size:11.5px; margin:0 5px 5px 0;
    cursor:pointer; color:#8d857a; }
  .tpill.has { font-weight:700; }
  .tpill:hover { background:var(--blue-pale); }
  .tpill.on { background:var(--black); border-color:var(--black); color:#fff; }
  @media (max-width:820px) {
    body { flex-direction:column; }
    #left { flex:0 0 52vh; }
    #right { flex:1 1 auto; border-left:none; border-top:1px solid var(--line); }
    #legend { display:none; }
  }
</style>
</head>
<body>
<div id="left">
  <svg id="map" viewBox="-575 -410 1150 820"></svg>
  <div id="maptop"><h1>Buju Story Explorer</h1>
    <div class="tag">drag to orbit &middot; scroll or pinch to zoom &middot; tap a topic</div></div>
  <div class="float clickable" id="resetview">reset view</div>
  <div class="float" id="maphint">click a disc &middot; numbered discs have stories</div>
  <div class="float" id="legend"></div>
</div>
<div id="right">
  <div id="back">&larr; back to the shelf</div>
  <div id="browse"></div>
  <div id="player" style="display:none"></div>
</div>
<script>
const DATA = __EXPLORER_DATA_JSON__;
const PALETTE = [
  { solid:"#0A5CD1", light:"#5C9BE9", pale:"#CAE0F8" },
  { solid:"#0BA671", light:"#42CDA6", pale:"#C8ECE2" },
  { solid:"#1574E1", light:"#7FB2EE", pale:"#DCEAFB" },
  { solid:"#00BC87", light:"#6BD9B8", pale:"#D6F4EA" },
  { solid:"#F66700", light:"#FF9F58", pale:"#FFD9BD" }
];
const storiesByTopic = {};
for (const s of DATA.stories) (storiesByTopic[s.topics.knowledge_domain] ||= []).push(s);
const storyById = Object.fromEntries(DATA.stories.map(s => [s.id, s]));
const topicById = Object.fromEntries(DATA.topics.map(t => [t.id, t]));
const paletteOf = t => PALETTE[t.cluster % PALETTE.length];
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("map");

const legend = DATA.categories.map(c =>
  '<span class="sw" style="background:' + PALETTE[c.cluster % PALETTE.length].solid +
  '"></span>' + c.display_name).join("<br>") +
  '<br><span class="sw" style="background:#e7ded4"></span>pale = no story yet';
document.getElementById("legend").innerHTML = legend;

// ---- gradients, one pair per cluster -------------------------------------
const defs = document.createElementNS(NS, "defs");
// Discs are flat and face the viewer: one soft vertical wash per colour,
// no specular highlight, so they read as chips rather than balls.
PALETTE.forEach((p, i) => {
  for (const kind of ["solid", "pale"]) {
    const g = document.createElementNS(NS, "linearGradient");
    g.setAttribute("id", "grad" + i + kind);
    g.setAttribute("x1", "0%"); g.setAttribute("y1", "0%");
    g.setAttribute("x2", "0%"); g.setAttribute("y2", "100%");
    const a = document.createElementNS(NS, "stop");
    a.setAttribute("offset", "0%");
    a.setAttribute("stop-color", kind === "solid" ? p.light : "#ffffff");
    const b = document.createElementNS(NS, "stop");
    b.setAttribute("offset", "100%");
    b.setAttribute("stop-color", kind === "solid" ? p.solid : p.pale);
    g.appendChild(a); g.appendChild(b);
    defs.appendChild(g);
  }
});
svg.appendChild(defs);
const edgeLayer = document.createElementNS(NS, "g");
const nodeLayer = document.createElementNS(NS, "g");
svg.appendChild(edgeLayer); svg.appendChild(nodeLayer);

// ---- build the svg elements once, then move them every frame ------------
const nodeEls = DATA.topics.map(t => {
  const pal = paletteOf(t);
  const isCat = t.tier === "curriculum";
  const has = t.stories > 0;
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "node");
  g.style.cursor = "pointer";
  const hit = document.createElementNS(NS, "circle");
  hit.setAttribute("fill", "transparent");
  const halo = document.createElementNS(NS, "circle");
  halo.setAttribute("fill", pal.solid);
  const ball = document.createElementNS(NS, "circle");
  ball.setAttribute("fill", "url(#grad" + (t.cluster % PALETTE.length) +
    (has ? "solid" : "pale") + ")");
  ball.setAttribute("stroke", has ? "rgba(255,255,255,.9)" : pal.light);
  const count = document.createElementNS(NS, "text");
  count.setAttribute("text-anchor", "middle");
  count.setAttribute("font-weight", "700");
  count.setAttribute("fill", has ? "#fff" : pal.solid);
  count.textContent = t.stories ? String(t.stories) : "";
  const label = document.createElementNS(NS, "text");
  label.setAttribute("text-anchor", "middle");
  label.setAttribute("font-family", "Quicksand,Poppins,sans-serif");
  label.setAttribute("font-weight", "700");
  label.setAttribute("paint-order", "stroke");
  label.setAttribute("stroke", "#fdf7f1");
  label.setAttribute("stroke-width", "3.5");
  label.setAttribute("fill", isCat ? "#241f1a" : "#5a5249");
  label.textContent = t.display_name;
  g.appendChild(hit); g.appendChild(halo); g.appendChild(ball);
  g.appendChild(count); g.appendChild(label);
  // A click counts unless the pointer really travelled: trackpads jitter a
  // few pixels between press and release, and that must not eat the click.
  g.addEventListener("click", () => { if (movedBy <= CLICK_SLOP) showTopic(t.id); });
  g.addEventListener("mouseenter", () => { hovered = t.id; needsDraw = true; });
  g.addEventListener("mouseleave", () => {
    if (hovered === t.id) { hovered = null; needsDraw = true; }
  });
  nodeLayer.appendChild(g);
  return { topic:t, g, hit, halo, ball, count, label, isCat, has, pal };
});
const edgeEls = DATA.edges.map(e => {
  const line = document.createElementNS(NS, "line");
  const pal = paletteOf(topicById[e.source]);
  line.setAttribute("stroke", e.cross ? "#b9ada0" : pal.light);
  line.setAttribute("stroke-linecap", "round");
  if (e.cross) line.setAttribute("stroke-dasharray", "7 7");
  edgeLayer.appendChild(line);
  return { edge:e, line };
});

// ---- 3D orbit ------------------------------------------------------------
const cam = { yaw:0.5, pitch:-0.25, zoom:1, focal:820 };
const CLICK_SLOP = 10;
let hovered = null, selected = null, movedBy = 0, needsDraw = true;

function project(t) {
  const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  const x1 = t.x * cy - t.z * sy;
  const z1 = t.x * sy + t.z * cy;
  const y1 = t.y * cp - z1 * sp;
  const z2 = t.y * sp + z1 * cp;
  const depth = cam.focal / (cam.focal + z2);
  return { sx: x1 * depth * cam.zoom, sy: y1 * depth * cam.zoom, depth, z: z2 };
}

function frame() {
  // The map only ever moves when the viewer moves it: no idle drift.
  if (!needsDraw) { requestAnimationFrame(frame); return; }
  needsDraw = false;
  const pts = {};
  for (const n of nodeEls) pts[n.topic.id] = project(n.topic);

  const near = new Set();
  const focus = hovered || selected;
  if (focus) {
    near.add(focus);
    for (const { edge } of edgeEls) {
      if (edge.source === focus) near.add(edge.target);
      if (edge.target === focus) near.add(edge.source);
    }
  }

  for (const { edge, line } of edgeEls) {
    const a = pts[edge.source], b = pts[edge.target];
    line.setAttribute("x1", a.sx); line.setAttribute("y1", a.sy);
    line.setAttribute("x2", b.sx); line.setAttribute("y2", b.sy);
    const d = (a.depth + b.depth) / 2;
    const lit = focus && near.has(edge.source) && near.has(edge.target);
    line.setAttribute("stroke-width", (edge.cross ? 1.1 : 1.7) * d * (lit ? 2.1 : 1));
    let op = (edge.cross ? 0.34 : 0.5) * Math.max(0.12, (d - 0.55) * 2.1);
    if (focus) op = lit ? Math.min(0.95, op * 2.4) : op * 0.3;
    line.setAttribute("stroke-opacity", op);
  }

  const sorted = nodeEls.slice().sort((p, q) => pts[q.topic.id].z - pts[p.topic.id].z);
  for (const n of sorted) {
    nodeLayer.appendChild(n.g);
    const p = pts[n.topic.id];
    const base = n.isCat ? 30 : 17.5;
    const r = base * p.depth * cam.zoom;
    const lit = !focus || near.has(n.topic.id);
    const isFocus = focus === n.topic.id;
    n.hit.setAttribute("cx", p.sx); n.hit.setAttribute("cy", p.sy);
    n.hit.setAttribute("r", Math.max(20, r * 1.7));
    n.halo.setAttribute("cx", p.sx); n.halo.setAttribute("cy", p.sy);
    n.halo.setAttribute("r", r * (isFocus ? 1.85 : 1.45));
    n.halo.setAttribute("opacity", (isFocus ? 0.3 : 0.13) * (lit ? 1 : 0.25));
    n.ball.setAttribute("cx", p.sx); n.ball.setAttribute("cy", p.sy);
    n.ball.setAttribute("r", r);
    n.ball.setAttribute("stroke-width", (isFocus ? 4 : (n.has ? 2 : 1.6)) * p.depth);
    n.ball.setAttribute("stroke", isFocus ? "#1A1A1A"
      : (n.has ? "rgba(255,255,255,.9)" : n.pal.light));
    n.ball.setAttribute("opacity", Math.max(0.3, (p.depth - 0.52) * 2.3) * (lit ? 1 : 0.35));
    n.count.setAttribute("x", p.sx); n.count.setAttribute("y", p.sy + r * 0.33);
    n.count.setAttribute("font-size", r * 0.78);
    n.count.setAttribute("opacity", lit ? 1 : 0.3);
    n.label.setAttribute("x", p.sx); n.label.setAttribute("y", p.sy + r + 15 * p.depth);
    n.label.setAttribute("font-size", (n.isCat ? 15 : 12) * Math.max(0.72, p.depth));
    const labelOn = n.isCat || isFocus || (focus && near.has(n.topic.id)) ||
      (!focus && p.depth > 0.98);
    n.label.setAttribute("opacity", labelOn ? Math.max(0.35, (p.depth - 0.5) * 2.2) : 0);
  }
  requestAnimationFrame(frame);
}

function pointer(ev) {
  const t = ev.touches && ev.touches.length ? ev.touches[0] : ev;
  return { x: t.clientX, y: t.clientY };
}
let dragFrom = null, pinchFrom = null;
function startDrag(ev) {
  if (ev.touches && ev.touches.length === 2) {
    pinchFrom = { d: touchDist(ev), zoom: cam.zoom };
    return;
  }
  dragFrom = pointer(ev); movedBy = 0;
}
function touchDist(ev) {
  const a = ev.touches[0], b = ev.touches[1];
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}
function moveDrag(ev) {
  if (pinchFrom && ev.touches && ev.touches.length === 2) {
    ev.preventDefault();
    cam.zoom = Math.min(2.6, Math.max(0.45, pinchFrom.zoom * touchDist(ev) / pinchFrom.d));
    needsDraw = true; return;
  }
  if (!dragFrom) return;
  const p = pointer(ev);
  const dx = p.x - dragFrom.x, dy = p.y - dragFrom.y;
  movedBy += Math.abs(dx) + Math.abs(dy);
  if (movedBy > CLICK_SLOP) svg.classList.add("drag");
  cam.yaw += dx * 0.006;
  cam.pitch = Math.max(-1.15, Math.min(1.15, cam.pitch + dy * 0.005));
  dragFrom = p; needsDraw = true;
  if (ev.touches) ev.preventDefault();
}
function endDrag() {
  dragFrom = null; pinchFrom = null; svg.classList.remove("drag");
  setTimeout(() => { movedBy = 0; }, 0);
}
svg.addEventListener("mousedown", startDrag);
window.addEventListener("mousemove", moveDrag);
window.addEventListener("mouseup", endDrag);
svg.addEventListener("touchstart", startDrag, { passive:false });
svg.addEventListener("touchmove", moveDrag, { passive:false });
window.addEventListener("touchend", endDrag);
svg.addEventListener("wheel", ev => {
  ev.preventDefault();
  cam.zoom = Math.min(2.6, Math.max(0.45, cam.zoom * Math.exp(-ev.deltaY * 0.0013)));
  needsDraw = true;
}, { passive:false });

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));
}
function chips(items, cls) {
  return (items || []).map(v =>
    '<span class="chip ' + (cls || "") + '">' + esc(v) + "</span>").join("");
}

function showTopic(id) {
  closePlayer();
  selected = id; needsDraw = true;
  const t = topicById[id];
  const pal = paletteOf(t);
  let h = "<h2>" + esc(t.display_name) + "</h2>";
  h += '<span class="chip tier">' +
    (t.tier === "curriculum" ? "category" : "deep dive") + "</span>";
  if (t.parent) {
    h += '<span class="chip">under ' + esc(topicById[t.parent].display_name) + "</span>";
  }
  const links = DATA.edges.filter(e =>
    e.kind === "adjacent" && (e.source === id || e.target === id));
  const crossing = links.filter(e => e.cross).map(e => {
    const other = topicById[e.source === id ? e.target : e.source];
    return other.display_name + " (" +
      topicById[other.parent || other.id].display_name + ")";
  });
  h += '<div class="framing" style="border-left-color:' + pal.solid + '">At age 6: ' +
    esc(t.framing) + "</div>";
  if (t.facets && t.facets.length) {
    h += '<div class="lab">Facets stories can rotate through</div>' + chips(t.facets);
  }
  if (t.vocabulary && t.vocabulary.length) {
    h += '<div class="lab">Vocabulary for this age</div>' + chips(t.vocabulary, "vocab");
  }
  if (crossing.length) {
    h += '<div class="lab">Reaches across into</div>' + chips(crossing);
  }
  if (t.avoid && t.avoid.length) {
    h += '<div class="lab">Stories must avoid (own + inherited)</div>' +
      chips(t.avoid, "warn");
  }
  const shelf = storiesByTopic[id] || [];
  h += '<div class="lab">' + (shelf.length ? "Stories on this topic"
    : "No story here yet &mdash; nearby stories in this family") + "</div>";
  const offer = shelf.length ? shelf : familyStories(t);
  if (!offer.length) {
    h += '<div class="empty-note">No stories in this family yet.</div>';
  }
  for (const s of offer) {
    const home = topicById[s.topics.knowledge_domain];
    h += '<div class="card" data-act="story" data-story="' + s.id + '"><h3>' +
      esc(s.title) + "</h3>" +
      chips(["age " + s.age_band, s.pattern, s.teller,
        s.tone.dominant + (s.tone.accent ? " + " + s.tone.accent : "")]);
    if (!shelf.length && home) {
      h += '<div class="why">from ' + esc(home.display_name) + "</div>";
    }
    h += "</div>";
  }
  h += allTopicsList(id);
  document.getElementById("browse").innerHTML = h;
  document.getElementById("right").scrollTop = 0;
}

function familyStories(topic) {
  const root = topic.parent || topic.id;
  const family = DATA.topics.filter(t => t.id === root || t.parent === root);
  const out = [];
  for (const t of family) for (const s of (storiesByTopic[t.id] || [])) out.push(s);
  return out;
}
function allTopicsList(currentId) {
  let h = '<div class="lab">Every topic on the map</div><div class="alltopics">';
  for (const c of DATA.categories) {
    const pal = PALETTE[c.cluster % PALETTE.length];
    const members = [topicById[c.id]].concat(
      DATA.topics.filter(t => t.parent === c.id));
    h += '<div class="tgroup"><div class="tgroup-name" style="color:' + pal.solid +
      '">' + esc(c.display_name) + "</div>";
    for (const t of members) {
      const on = t.id === currentId;
      h += '<span class="tpill' + (on ? " on" : "") + (t.stories ? " has" : "") +
        '" data-act="topic" data-topic="' + t.id + '" style="' +
        (t.stories ? "border-color:" + pal.solid + ";color:" + pal.solid + ";" : "") +
        '">' + esc(t.display_name) + (t.stories ? " &middot; " + t.stories : "") +
        "</span>";
    }
    h += "</div>";
  }
  return h + "</div>";
}

let play = null, tab = "play";
function playStory(id) {
  const story = storyById[id];
  play = { story, slots:{}, recap:[], pending:[], trail:"", body:"",
           path:[story.start_segment] };
  for (const k of Object.keys(story.slots)) {
    play.slots[k] = story.slots[k].default;
    if (story.slots[k].ask_child) play.pending.push(k);
  }
  tab = "play";
  document.getElementById("browse").style.display = "none";
  document.getElementById("player").style.display = "block";
  document.getElementById("back").style.display = "block";
  document.getElementById("right").scrollTop = 0;
  if (play.pending.length) renderNaming(); else startSegments();
}
function head() {
  const s = play.story;
  let h = "<h2>" + esc(s.title) + "</h2>" +
    chips(["age " + s.age_band, s.pattern, s.teller]);
  h += '<div id="tabs">';
  h += '<button class="tab' + (tab === "play" ? " on" : "") +
    '" data-act="tab" data-tab="play">Play</button>';
  h += '<button class="tab' + (tab === "why" ? " on" : "") +
    '" data-act="tab" data-tab="why">Why this story</button>';
  h += '<button class="tab' + (tab === "braid" ? " on" : "") +
    '" data-act="tab" data-tab="braid">Braid</button>';
  h += "</div>";
  return h;
}
function setTab(t) {
  tab = t;
  const el = document.getElementById("player");
  if (t === "play") el.innerHTML = head() + play.body;
  else el.innerHTML = head() + (t === "why" ? renderWhy() : renderBraid());
  document.getElementById("right").scrollTop = 0;
}
function renderNaming() {
  const k = play.pending[0];
  const spec = play.story.slots[k];
  const word = play.story.topics.knowledge_domain.split(".")[1].replace(/_/g, " ");
  play.body = '<div class="namebox"><b>This story has ' + esc(spec.role) + ".</b><br>" +
    "What should we call them?<br><br>" +
    '<input id="nm" value="' + esc(spec.default) + '">' +
    '<button class="btn" data-act="setname" data-slot="' + k + '">that is the name</button>' +
    '<div class="why">Naming slot &mdash; stored per topic family, so it carries into ' +
    "every later story about " + esc(word) + " and its deep dives.</div></div>";
  document.getElementById("player").innerHTML = head() + play.body;
}
function setName(k) {
  const box = document.getElementById("nm");
  const v = (box ? box.value : "").trim();
  if (v) play.slots[k] = v;
  play.pending.shift();
  if (play.pending.length) renderNaming(); else startSegments();
}
function fill(t) {
  let out = t;
  for (const k of Object.keys(play.slots)) {
    out = out.split("{" + k + "}").join(play.slots[k]);
  }
  return out;
}
function startSegments() { play.trail = ""; renderSegment(play.story.start_segment); }
function renderSegment(segId) {
  const story = play.story;
  const seg = story.segments.find(s => s.id === segId);
  if (!play.path.includes(segId)) play.path.push(segId);
  play.trail += '<div class="seg">' + esc(fill(seg.text)) + "</div>";
  if (seg.next === null) {
    const recap = play.recap.length
      ? '<div class="recap">Path taken: ' + play.recap.map(esc).join(" &rarr; ") + "</div>"
      : "";
    play.body = play.trail +
      '<div class="ending"><b>The end</b> &mdash; warm and fully resolved. ' + recap +
      '<br><button class="btn" data-act="story" data-story="' + story.id +
      '">play again, choose differently</button>' +
      '<button class="btn ghost" data-act="close">back to the shelf</button></div>';
    document.getElementById("player").innerHTML = head() + play.body;
    return;
  }
  if (seg.next.kind === "segment") { renderSegment(seg.next.id); return; }
  const c = story.choice_points.find(x => x.id === seg.next.id);
  let h = play.trail + '<div class="question">' + esc(fill(c.question)) + "</div>";
  c.options.forEach((o, i) => {
    h += '<button class="opt" data-act="pick" data-choice="' + c.id +
      '" data-index="' + i + '">' + esc(o.label) +
      ' <span class="say">say: ' + esc(o.say_word) + " &middot; " + esc(o.tone_lean) +
      " &middot; " + esc(o.curiosity_lean) + "</span></button>";
  });
  h += '<div id="sayrow"><input id="saybox" placeholder="or type what you would say out loud">' +
    '<button id="saygo" data-act="hear" data-choice="' + c.id + '">say it</button></div>';
  play.body = h;
  document.getElementById("player").innerHTML = head() + play.body;
}
function pick(cid, i) {
  const c = play.story.choice_points.find(x => x.id === cid);
  const o = c.options[Number(i)];
  Object.assign(play.slots, o.sets_slots);
  play.recap.push(o.label);
  renderSegment(o.next_segment);
}
function hear(cid) {
  const box = document.getElementById("saybox");
  const said = (box ? box.value : "").toLowerCase();
  const c = play.story.choice_points.find(x => x.id === cid);
  let best = -1;
  c.options.forEach((o, i) => {
    const words = (o.say_word + " " + o.label).toLowerCase().split(/[^a-z]+/);
    if (words.some(w => w.length > 2 && said.includes(w))) best = i;
  });
  if (best >= 0) pick(cid, best);
  else if (box) { box.value = ""; box.placeholder = "hmm &mdash; which one do you mean?"; }
}
function renderWhy() {
  const r = play.story.build_record;
  if (!r) return '<div class="dec"><p>No decision record on this story yet.</p></div>';
  let h = '<div class="dec"><h4>The request</h4>';
  h += '<div class="kv"><b>Topic:</b> ' + esc(r.request.topic) + " (" +
    esc(r.request.topic_tier || "curriculum") + ")</div>";
  if (r.request.parent_topic) {
    h += '<div class="kv"><b>Under:</b> ' + esc(r.request.parent_topic) + "</div>";
  }
  h += '<div class="kv"><b>Age:</b> ' + esc(r.request.age_band) + "</div>";
  h += '<div class="kv"><b>Family context:</b> ' + esc(r.request.family_context) +
    "</div></div>";
  const pc = r.pattern_choice;
  h += '<div class="dec"><h4>1 &middot; Story pattern &rarr; ' + esc(pc.chosen) + "</h4>";
  h += "<p>" + esc(pc.why) + "</p>";
  const max = Math.max.apply(null, pc.candidates.map(c => c.final_weight));
  for (const c of pc.candidates) {
    const win = c.pattern === pc.chosen;
    h += '<div class="bar ' + (win ? "win" : (c.sampled ? "" : "out")) + '">';
    h += '<span class="nm">' + esc(c.pattern) + (win ? " &check;" : "") + "</span>";
    h += '<span class="track"><span class="fill" style="width:' +
      Math.round(100 * c.final_weight / max) + '%"></span></span>';
    h += '<span class="val">' + c.final_weight.toFixed(2) + "</span></div>";
    const notes = [];
    if (c.shelf_nudge && c.shelf_nudge !== 1) notes.push("shelf nudge x" + c.shelf_nudge);
    if (c.family_nudge && c.family_nudge !== 1) notes.push("family nudge x" + c.family_nudge);
    if (!c.sampled) notes.push("not sampled");
    if (c.rejected_because) notes.push(c.rejected_because);
    if (notes.length) h += '<div class="why ind">' + esc(notes.join(" | ")) + "</div>";
  }
  h += "<p><b>Backup plan:</b> " + esc(pc.backup) + "</p></div>";
  const tc = r.tone_choice;
  h += '<div class="dec"><h4>2 &middot; Tone recipe</h4>';
  h += chips([tc.chosen.dominant + " (dominant)"]);
  if (tc.chosen.accent) h += chips([tc.chosen.accent + " (accent)"]);
  if (tc.accent_carrier) {
    h += '<div class="kv"><b>Accent carried by:</b> ' + esc(tc.accent_carrier) + "</div>";
  }
  h += "<p>" + esc(tc.why) + "</p>";
  for (const x of (tc.rejected || [])) {
    h += '<div class="why">rejected ' + esc(x.recipe) + " &mdash; " + esc(x.because) + "</div>";
  }
  h += "</div>";
  const te = r.teller_choice;
  h += '<div class="dec"><h4>3 &middot; Teller &rarr; ' + esc(te.chosen) + "</h4><p>" +
    esc(te.why) + "</p>";
  for (const x of (te.rejected || [])) {
    h += '<div class="why">rejected ' + esc(x.teller) + " &mdash; " + esc(x.because) + "</div>";
  }
  h += "</div>";
  h += '<div class="dec"><h4>4 &middot; Cast</h4>';
  for (const c of (r.cast || [])) {
    h += '<div class="kv"><b>' + esc(c.role) + ":</b> " + (c.reused ? "reused" : "new");
    if (c.reused_from) h += " from " + esc(c.reused_from);
    if (c.slot) h += " &middot; slot " + esc(c.slot);
    h += '<div class="why">' + esc(c.why) + "</div></div>";
  }
  h += "</div>";
  h += '<div class="dec"><h4>5 &middot; Value lesson &rarr; ' +
    (r.value_decision.included ? esc(r.value_decision.value || "included") : "none") +
    "</h4><p>" + esc(r.value_decision.why) + "</p></div>";
  h += '<div class="dec"><h4>6 &middot; Materials</h4>';
  h += '<div class="lab">Used in this story</div><ul class="tight">';
  for (const m of (r.materials.selected || [])) h += "<li>" + esc(m) + "</li>";
  h += '</ul><div class="lab">Gathered, kept for the next story here</div><ul class="tight">';
  for (const m of (r.materials.gathered_but_unused || [])) h += "<li>" + esc(m) + "</li>";
  h += "</ul></div>";
  h += '<div class="dec"><h4>7 &middot; Why the choices sit where they do</h4>';
  for (const b of (r.branch_design || [])) {
    h += "<p><b>" + esc(b.choice) + "</b> &mdash; " + (b.rejoins ? "rejoins" : "splits") +
      ". " + esc(b.why_here) + '</p><ul class="tight">';
    const crit = b.criteria || {};
    for (const k of Object.keys(crit)) {
      h += "<li><b>" + esc(k.replace(/_/g, " ")) + ":</b> " + esc(crit[k]) + "</li>";
    }
    h += "</ul>";
  }
  h += "</div>";
  h += '<div class="dec"><h4>8 &middot; Quality gates</h4>';
  for (const g of (r.gates || [])) {
    h += '<div class="kv"><span class="pass">' + esc(g.result) + "</span> &middot; <b>" +
      esc(g.gate) + '</b><div class="why">' + esc(g.notes) + "</div></div>";
  }
  if ((r.writers_notes || []).length) {
    h += '<div class="lab">Notes carried forward between writing rounds</div><ul class="tight">';
    for (const n of r.writers_notes) h += "<li>" + esc(n) + "</li>";
    h += "</ul>";
  }
  h += '<div class="why">' + esc(r.authored_by || "") + "</div></div>";
  return h;
}
function renderBraid() {
  const s = play.story;
  const walked = {};
  for (const p of play.path) walked[p] = true;
  const pos = { s1:[300,45], s2a:[150,155], s2b:[450,155], s3:[300,265],
                s4a:[150,375], s4b:[450,375] };
  const links = [["s1","s2a"],["s1","s2b"],["s2a","s3"],["s2b","s3"],
                 ["s3","s4a"],["s3","s4b"]];
  let h = '<div class="braid"><svg viewBox="0 0 600 430" style="width:100%;height:auto">';
  for (const pair of links) {
    const a = pos[pair[0]], b = pos[pair[1]];
    if (!a || !b) continue;
    const on = walked[pair[0]] && walked[pair[1]];
    h += '<line x1="' + a[0] + '" y1="' + (a[1] + 23) + '" x2="' + b[0] +
      '" y2="' + (b[1] - 23) + '" stroke="' + (on ? "#0A5CD1" : "#e4dcd3") +
      '" stroke-width="' + (on ? 3.5 : 2) + '" stroke-linecap="round"/>';
  }
  for (const id of Object.keys(pos)) {
    const seg = s.segments.find(g => g.id === id);
    if (!seg) continue;
    const p = pos[id], on = walked[id], ending = seg.next === null;
    h += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="23" fill="' +
      (on ? "#0A5CD1" : "#fff") + '" stroke="' + (ending ? "#0BA671" : "#5C9BE9") +
      '" stroke-width="' + (ending ? 3.5 : 2) + '"/>';
    h += '<text x="' + p[0] + '" y="' + (p[1] + 5) +
      '" text-anchor="middle" font-size="13" font-weight="700" fill="' +
      (on ? "#fff" : "#0A5CD1") + '">' + id + "</text>";
  }
  h += '<text x="300" y="118" text-anchor="middle" font-size="12" fill="#8d857a">' +
    "c1 &middot; rejoins at s3</text>";
  h += '<text x="300" y="332" text-anchor="middle" font-size="12" fill="#8d857a">' +
    "c2 &middot; splits into two endings</text></svg>";
  h += '<div class="why">Blue = the path you walked. Green ring = an ending.</div>';
  h += '<div class="lab">Slots in this story</div>';
  for (const k of Object.keys(s.slots)) {
    const v = s.slots[k];
    h += '<div class="kv"><b>{' + esc(k) + "}</b> &mdash; " + esc(v.role) + " &middot; " +
      esc(v.kind) + (v.ask_child ? " &middot; child names it" : "") +
      " &middot; now: <b>" + esc(play.slots[k]) + "</b></div>";
  }
  h += "</div>";
  return h;
}
function closePlayer() {
  play = null;
  const p = document.getElementById("player");
  p.style.display = "none"; p.innerHTML = "";
  document.getElementById("back").style.display = "none";
  document.getElementById("browse").style.display = "block";
}
document.getElementById("right").addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  if (act === "story") playStory(el.dataset.story);
  else if (act === "topic") showTopic(el.dataset.topic);
  else if (act === "tab") setTab(el.dataset.tab);
  else if (act === "setname") setName(el.dataset.slot);
  else if (act === "pick") pick(el.dataset.choice, el.dataset.index);
  else if (act === "hear") hear(el.dataset.choice);
  else if (act === "close") closePlayer();
});
document.getElementById("resetview").addEventListener("click", () => {
  cam.yaw = 0.5; cam.pitch = -0.25; cam.zoom = 1; needsDraw = true;
});
document.getElementById("back").addEventListener("click", closePlayer);
showTopic(DATA.categories[0].id);
frame();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate only")
    args = parser.parse_args()

    registry = load_default_registry()
    topic_ids = set(registry.nodes_by_id)
    stories = load_stories()

    all_issues: list[str] = []
    for story in stories:
        all_issues.extend(validate_story(story, topic_ids))
    if all_issues:
        print(f"FAIL: {len(all_issues)} issue(s) in {len(stories)} stories")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1
    print(f"OK: {len(stories)} stories valid")
    if args.check:
        return 0

    data = build_explorer_data(stories)
    html = _HTML_TEMPLATE.replace(
        _DATA_PLACEHOLDER, json.dumps(data, ensure_ascii=False)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(
        f"wrote explorer with {len(data['topics'])} topics, "
        f"{len(data['stories'])} stories to {OUTPUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
