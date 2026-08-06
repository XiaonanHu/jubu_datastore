"""
Build the print-ready story review packet for the expert reviewer.

    python scripts/build_review_packet.py

Writes story_definitions/preview/story_review_packet.html: the questions we
want answered, the v1 and v2.1 versions of the volcano story for comparison,
two new v2.1 stories, and the craft-audit numbers as an appendix.
"""

import html
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
PILOT = ROOT / "story_definitions/stories/pilot"


def load(name):
    return json.loads((PILOT / name).read_text())


def fill(text, slots):
    for k, v in slots.items():
        text = text.replace("{" + k + "}", v)
    return text


def default_slots(story, extra=None):
    s = {k: v["default"] for k, v in story["slots"].items()}
    if extra:
        s.update(extra)
    return s


def path_html(story, branch1, branch2, label):
    seg = {s["id"]: s for s in story["segments"]}
    ch = {c["id"]: c for c in story["choice_points"]}
    slots = default_slots(story)
    out = [f"<h4>{html.escape(label)}</h4>"]
    order = ["s1", branch1, "s3", branch2]
    # apply slot values set by the chosen options
    for cid, chosen in (("c1", branch1), ("c2", branch2)):
        for o in ch[cid]["options"]:
            if o["next_segment"] == chosen:
                slots.update(o.get("sets_slots", {}))
    words = 0
    for sid in order:
        text = fill(seg[sid]["text"], slots)
        words += len(text.split())
        paras = "".join(f"<p>{html.escape(p)}</p>" for p in text.split("\n"))
        out.append(f'<div class="seg"><span class="sid">{sid}</span>{paras}</div>')
        nxt = seg[sid]["next"]
        if nxt and nxt["kind"] == "choice":
            c = ch[nxt["id"]]
            opts = "".join(
                '<li%s>%s <span class="say">(say: %s)</span></li>'
                % (
                    ' class="taken"' if o["next_segment"] in (branch1, branch2) else "",
                    html.escape(o["label"]),
                    html.escape(o["say_word"]),
                )
                for o in c["options"]
            )
            out.append(
                '<div class="choice"><p class="q">%s</p><ul>%s</ul>'
                '<p class="meta">%s</p></div>'
                % (
                    html.escape(fill(c["question"], slots)),
                    opts,
                    "rejoins at s3" if c["rejoins"] else "splits into two endings",
                )
            )
    out.append(f'<p class="wc">{words} words on this path</p>')
    return "\n".join(out)


def story_block(story, title_note, paths):
    h = [
        f'<h2>{html.escape(story["title"])} <span class="note">{title_note}</span></h2>'
    ]
    h.append(
        '<p class="meta">age %s &middot; pattern <b>%s</b> &middot; teller <b>%s</b> '
        "&middot; tone %s%s</p>"
        % (
            story["age_band"],
            story["pattern"],
            story["teller"],
            story["tone"]["dominant"],
            " + " + story["tone"]["accent"] if story["tone"].get("accent") else "",
        )
    )
    if story["slots"]:
        names = ", ".join(
            "%s (%s%s)"
            % (v["role"], v["kind"], ", child names it" if v.get("ask_child") else "")
            for v in story["slots"].values()
        )
        h.append(f'<p class="meta">Blanks the child fills: {html.escape(names)}</p>')
    for b1, b2, label in paths:
        h.append(path_html(story, b1, b2, label))
    return "\n".join(h)


v1 = json.loads(
    (ROOT / "story_definitions/stories/archive_v1/volcanoes.json").read_text()
)
v2 = load("volcanoes.json")
turtles = load("sea_turtles.json")
bees = load("bees.json")

audit = subprocess.run(
    ["python3", "scripts/audit_story_craft.py", "--compare"],
    cwd=ROOT,
    capture_output=True,
    text=True,
).stdout
audit_tail = audit[audit.index("=====") :] if "=====" in audit else audit

QUESTIONS = [
    (
        "Did the rewrite fix what you marked?",
        "Same story, same choices, same structure — only the writing changed. Does the opening now tell you who we are and why we are there? Are the descriptions doing work, or still in the way?",
    ),
    (
        "Is anything now missing?",
        "We cut a great deal: the ash hat business, the smoke ring, the squeaky rumble, the spark on the nose. Did we cut something that was actually helping?",
    ),
    (
        "Repetition: right, or babyish?",
        '"Listen. Listen." and "You came! You came!" are pitched at five. Where does this tip into babyish for a six-year-old?',
    ),
    (
        "Does the quiet story hold a child?",
        "The Night the Sand Went Soft has almost no event for its first two thirds. Does a five-year-old stay with it, or do we need to give up on this kind of story?",
    ),
    (
        "Safety as competence, not warning",
        "In three places a grown-up simply knows where to stand: the cold black stone path, behind the rock at the rim, the torch going into the pocket. No one says anything is dangerous. Is this the right way to handle a real place a child might visit — and is once enough?",
    ),
    (
        "Naming a feeling",
        'Our current rule: at five or six a feeling may be named plainly only if the body shows it too ("He is a little scared. He swims closer anyway"). Too loose, too strict, or right?',
    ),
    (
        "The named hero",
        "In Somebody Told the Bees the child names the hero and then watches her from outside. Is that distance useful at this age, or would being inside the story be better?",
    ),
    (
        "Both endings",
        "Every story has two endings and we ask that both feel warm and finished. Please read both of each. Does either one feel like the lesser one?",
    ),
]

css = """
@media print { body{font-size:11pt} .seg,.choice{page-break-inside:avoid} h2{page-break-before:always} h1+*{page-break-before:avoid} }
body{font-family:Georgia,'Times New Roman',serif;max-width:760px;margin:40px auto;padding:0 26px;line-height:1.55;color:#1c2233}
h1{font-size:26px;border-bottom:2px solid #1c2233;padding-bottom:8px}
h2{font-size:20px;margin-top:34px;border-bottom:1px solid #ccd2e0;padding-bottom:5px}
h3{font-size:16px;margin-top:26px}
h4{font-size:14px;color:#4a5468;margin:22px 0 8px;text-transform:uppercase;letter-spacing:.05em}
.note{font-size:13px;color:#7a8296;font-weight:normal;font-style:italic}
.meta{font-size:12.5px;color:#5a6478;margin:4px 0}
.seg{border-left:3px solid #d7dce8;padding:2px 0 2px 16px;margin:10px 0;position:relative}
.seg p{margin:8px 0}
.sid{position:absolute;left:-42px;top:4px;font-size:10px;color:#a4abbd;font-family:monospace}
.choice{background:#f3f6fc;border-radius:8px;padding:10px 16px;margin:12px 0}
.choice .q{font-weight:bold;margin:4px 0}
.choice ul{margin:6px 0;padding-left:20px;font-size:14px}
.choice li.taken{font-weight:bold}
.choice .say{color:#7a8296;font-size:12px}
.choice .meta{font-size:11.5px;margin:4px 0 0}
.wc{font-size:11.5px;color:#7a8296;text-align:right;margin:2px 0 18px}
.q-card{background:#fffaf3;border:1px solid #f0dfc8;border-radius:8px;padding:12px 16px;margin:10px 0}
.q-card b{display:block;margin-bottom:4px}
pre{background:#f4f6fa;padding:14px;border-radius:8px;font-size:11px;overflow-x:auto}
blockquote{border-left:3px solid #ccd2e0;margin-left:0;padding-left:16px;color:#454e66;font-style:italic}
"""

parts = [
    f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Buju story review packet</title><style>{css}</style></head><body>'
]
parts.append("<h1>Buju — story review packet</h1>")
parts.append(
    '<p class="meta">Three stories written under a new writing guide, plus the earlier '
    "version of one of them for comparison. Everything is a draft. July 2026.</p>"
)
parts.append("<h3>What we changed, and why</h3>")
parts.append(
    "<p>Your line-by-line notes on <i>The Mountain That Breathes</i> became a written "
    "guide for whoever writes these stories. The main changes: an opening must say who "
    "we are, where we are and what pulls us in, before any door is opened; voices and "
    "action carry more than description; a description has to invite, involve, advance "
    "the story, or make you feel something, or it goes; comparisons come from a child's "
    "own day, so tomato soup and bread in the oven rather than nightlights; one image is "
    "grown through the whole story instead of a new one each paragraph; sentence lengths "
    "rise and fall; and a character asks the choosing question out loud instead of the "
    "narrator. Length is now a limit, not a target — padding counts as a mistake.</p>"
)
parts.append("<h3>What we would most like from you</h3>")
for q, detail in QUESTIONS:
    parts.append(
        f'<div class="q-card"><b>{html.escape(q)}</b>{html.escape(detail)}</div>'
    )
parts.append("<h3>How to read a story here</h3>")
parts.append(
    "<p>Each story has two choosing moments, so there are four ways through it. We have "
    "printed two of the four for each story, which together cover every segment. The "
    "blanks a child fills in are printed with their default names.</p>"
)

parts.append(
    story_block(v1, "the version you reviewed", [("s2b", "s4b", "One way through")])
)
parts.append(
    story_block(
        v2,
        "rewritten under the new guide — same story, same choices",
        [
            ("s2b", "s4b", "The same way through, for comparison"),
            ("s2a", "s4a", "The other way through"),
        ],
    )
)
parts.append(
    story_block(
        turtles,
        "new — a still, quiet story",
        [("s2b", "s4b", "One way through"), ("s2a", "s4a", "The other way through")],
    )
)
parts.append(
    story_block(
        bees,
        "new — a mystery, with a hero the child names",
        [("s2a", "s4a", "One way through"), ("s2b", "s4b", "The other way through")],
    )
)

parts.append("<h2>Appendix — what the automatic checks measure</h2>")
parts.append(
    "<p>These are rough machine counts, not judgements about quality. They are here only "
    "to show that the change is visible in the writing itself.</p>"
)
parts.append(f"<pre>{html.escape(audit_tail)}</pre>")
parts.append("</body></html>")

out = ROOT / "story_definitions/preview/story_review_packet.html"
out.write_text("\n".join(parts), encoding="utf-8")
print("wrote", out, len("\n".join(parts)) // 1024, "KiB")
