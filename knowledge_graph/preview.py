"""
Self-contained HTML preview of the knowledge graph — the admin/review tool
the developmental psychologist uses, and a de-risking prototype for the
parent app's Topic Map.

Force-directed canvas with axis-layer toggles and an age slider (5→10) to
eyeball the per-year morphing. No network access needed; graph data for all
six ages is embedded at build time.

    python -m jubu_datastore.knowledge_graph.preview \
        [--output knowledge_graph_definitions/preview/knowledge_graph_preview.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jubu_datastore.knowledge_graph.age_view import build_age_view
from jubu_datastore.knowledge_graph.graph_loader import (
    default_definitions_root,
    load_default_registry,
)
from jubu_datastore.knowledge_graph.graph_schema import MAX_AGE_YEARS, MIN_AGE_YEARS

_GRAPH_DATA_PLACEHOLDER = "__GRAPH_DATA_JSON__"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Buju Knowledge Graph — draft preview</title>
<style>
  :root { --panel-bg:#ffffff; --ink:#1f2430; --muted:#6b7280; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,'Segoe UI',Roboto,sans-serif; color:var(--ink); background:#f3f4f8; overflow:hidden; }
  #topbar { position:fixed; top:0; left:0; right:0; z-index:5; display:flex; gap:18px; align-items:center; padding:10px 16px; background:var(--panel-bg); border-bottom:1px solid #e3e5ee; flex-wrap:wrap; }
  #topbar h1 { font-size:15px; margin:0 8px 0 0; font-weight:600; }
  .draft-banner { background:#fff3cd; color:#7a5b00; border:1px solid #ffe08a; border-radius:6px; padding:2px 10px; font-size:12px; }
  .axis-toggle { display:inline-flex; align-items:center; gap:5px; font-size:13px; cursor:pointer; padding:3px 10px; border-radius:14px; border:1px solid transparent; }
  .axis-toggle input { accent-color:currentColor; }
  #agebox { display:flex; align-items:center; gap:10px; font-size:13px; }
  #agebox input { width:180px; }
  #ageval { font-weight:700; font-size:16px; min-width:22px; text-align:center; }
  #counts { color:var(--muted); font-size:12px; }
  canvas { display:block; cursor:grab; }
  #panel { position:fixed; top:56px; right:0; bottom:0; width:340px; background:var(--panel-bg); border-left:1px solid #e3e5ee; padding:16px; overflow-y:auto; display:none; z-index:4; }
  #panel h2 { margin:0 0 2px; font-size:18px; }
  #panel .meta { color:var(--muted); font-size:12px; margin-bottom:12px; }
  #panel .section-label { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:14px 0 4px; }
  #panel .framing { font-size:14px; line-height:1.45; }
  .chip { display:inline-block; background:#eef1f8; border-radius:10px; padding:2px 9px; font-size:12px; margin:2px 3px 2px 0; }
  .chip.avoid { background:#fdeaea; color:#8f2020; }
  #panel .close { float:right; cursor:pointer; color:var(--muted); font-size:18px; border:none; background:none; }
  #legendnote { position:fixed; left:12px; bottom:10px; font-size:11px; color:var(--muted); z-index:4; background:rgba(243,244,248,.85); padding:4px 8px; border-radius:6px; }
</style>
</head>
<body>
<div id="topbar">
  <h1>Buju Knowledge Graph</h1>
  <span class="draft-banner">DRAFT for review — content coverage map, never child evaluation</span>
  <span id="toggles"></span>
  <span id="agebox">Age <input type="range" id="age" min="3" max="10" step="1" value="6"><span id="ageval">6</span></span>
  <span id="counts"></span>
</div>
<div id="panel"></div>
<div id="legendnote">solid line = adjacent territory &nbsp;·&nbsp; dashed arrow = gentler entry first &nbsp;·&nbsp; drag nodes · scroll to zoom</div>
<canvas id="c"></canvas>
<script>
const GRAPH_BY_AGE = __GRAPH_DATA_JSON__;
const AXES = [
  {id:"knowledge_domain", name:"Knowledge domains", color:"#2f6fd6"},
  {id:"sel_theme",        name:"Feelings & friends", color:"#d64f7c"},
  {id:"value_lesson",     name:"Values",             color:"#d68a2f"},
  {id:"story_element",    name:"Story hooks",        color:"#7a4fd6"},
];
const axisColor = Object.fromEntries(AXES.map(a=>[a.id,a.color]));
const enabled = {knowledge_domain:true, sel_theme:true, value_lesson:true, story_element:true};
let age = 6, selectedId = null;

// Persistent positions so the layout morphs (rather than reshuffles) with age.
const pos = {};   // id -> {x,y,vx,vy}
let seed = 42;
function rand(){ seed = (seed*1103515245+12345)%2147483648; return seed/2147483648; }

const canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
let W=0, H=0, cam = {x:0, y:0, k:1};
function resize(){ W=innerWidth; H=innerHeight; canvas.width=W*devicePixelRatio; canvas.height=H*devicePixelRatio; canvas.style.width=W+"px"; canvas.style.height=H+"px"; ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
addEventListener("resize", resize); resize();

// Axis home zones spread the four layers apart; regions cluster within them.
const axisHome = {knowledge_domain:[-320,-40], sel_theme:[340,-220], value_lesson:[380,180], story_element:[60,330]};
const regionCenter = {};
function regionKey(n){ return n.axis + "/" + (n.region || "core"); }

let nodes=[], links=[], nodeById={};
function rebuild(){
  const view = GRAPH_BY_AGE[String(age)];
  nodes = view.nodes.filter(n=>enabled[n.axis]);
  nodeById = Object.fromEntries(nodes.map(n=>[n.id,n]));
  links = view.edges.filter(e=>nodeById[e.source] && nodeById[e.target]);
  const regions = [...new Set(nodes.map(regionKey))];
  regions.forEach((r,i)=>{
    if(!regionCenter[r]){
      const axis = r.split("/")[0], [hx,hy]=axisHome[axis];
      const angle = i*2.399963;  // golden angle keeps clusters spread
      regionCenter[r]=[hx+Math.cos(angle)*150, hy+Math.sin(angle)*110];
    }
  });
  for(const n of nodes){
    if(!pos[n.id]){
      const [cx,cy]=regionCenter[regionKey(n)];
      pos[n.id]={x:cx+(rand()-0.5)*120, y:cy+(rand()-0.5)*120, vx:0, vy:0};
    }
  }
  document.getElementById("counts").textContent = nodes.length+" territories · "+links.length+" paths";
  if(selectedId && !nodeById[selectedId]) closePanel();
  if(selectedId) showPanel(selectedId);
  heat = 1.0;
}

let heat = 1.0;
function tick(){
  if(heat < 0.005) return;
  heat *= 0.985;
  const ids = nodes.map(n=>n.id);
  // repulsion (O(n^2) is fine at ~180 nodes)
  for(let i=0;i<ids.length;i++){
    const a=pos[ids[i]];
    for(let j=i+1;j<ids.length;j++){
      const b=pos[ids[j]];
      let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy;
      if(d2<1) {dx=rand()-0.5; dy=rand()-0.5; d2=1;}
      if(d2>90000) continue;
      const f=1400/d2;
      const fx=dx*f, fy=dy*f;
      a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
    }
  }
  // springs
  for(const e of links){
    const a=pos[e.source], b=pos[e.target];
    const dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1;
    const f=(d-90)*0.012;
    a.vx+=dx/d*f; a.vy+=dy/d*f; b.vx-=dx/d*f; b.vy-=dy/d*f;
  }
  // gentle pull to region cluster centers
  for(const n of nodes){
    const p=pos[n.id], [cx,cy]=regionCenter[regionKey(n)];
    p.vx+=(cx-p.x)*0.004; p.vy+=(cy-p.y)*0.004;
  }
  for(const n of nodes){
    const p=pos[n.id];
    if(dragNode===n.id) {p.vx=0;p.vy=0;continue;}
    p.x+=p.vx*heat; p.y+=p.vy*heat; p.vx*=0.6; p.vy*=0.6;
  }
}

function nodeRadius(n){ return selectedId===n.id ? 10 : 6.5; }
function draw(){
  ctx.clearRect(0,0,W,H);
  ctx.save();
  ctx.translate(W/2+cam.x, H/2+cam.y); ctx.scale(cam.k,cam.k);
  const neighbor = new Set();
  if(selectedId) for(const e of links){ if(e.source===selectedId) neighbor.add(e.target); if(e.target===selectedId) neighbor.add(e.source); }
  for(const e of links){
    const a=pos[e.source], b=pos[e.target];
    const active = selectedId && (e.source===selectedId||e.target===selectedId);
    ctx.strokeStyle = active ? "#374151" : "rgba(120,130,150,0.28)";
    ctx.lineWidth = active ? 1.6 : 0.8;
    ctx.setLineDash(e.kind==="prerequisite" ? [5,4] : []);
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
    if(e.kind==="prerequisite"){ // arrowhead toward the dependent node
      const dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      const tx=b.x-dx/d*11, ty=b.y-dy/d*11;
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(tx-dy/d*3.5, ty+dx/d*3.5); ctx.lineTo(b.x-dx/d*5, b.y-dy/d*5); ctx.lineTo(tx+dy/d*3.5, ty-dx/d*3.5); ctx.stroke();
    }
  }
  ctx.setLineDash([]);
  for(const n of nodes){
    const p=pos[n.id];
    const dim = selectedId && n.id!==selectedId && !neighbor.has(n.id);
    ctx.globalAlpha = dim ? 0.35 : 1;
    ctx.fillStyle = axisColor[n.axis];
    ctx.beginPath(); ctx.arc(p.x,p.y,nodeRadius(n),0,7); ctx.fill();
    if(n.id===selectedId){ ctx.strokeStyle="#111"; ctx.lineWidth=2; ctx.stroke(); }
    if(cam.k>0.75 || n.id===selectedId || neighbor.has(n.id)){
      ctx.fillStyle = dim ? "#9aa1ad" : "#333a46";
      ctx.font = "10.5px sans-serif"; ctx.textAlign="center";
      ctx.fillText(n.display_name, p.x, p.y-nodeRadius(n)-4);
    }
    ctx.globalAlpha = 1;
  }
  ctx.restore();
}
function loop(){ tick(); draw(); requestAnimationFrame(loop); }

function screenToWorld(mx,my){ return [(mx-W/2-cam.x)/cam.k, (my-H/2-cam.y)/cam.k]; }
function hit(mx,my){
  const [x,y]=screenToWorld(mx,my);
  let best=null, bestD=13/cam.k;
  for(const n of nodes){ const p=pos[n.id], d=Math.hypot(p.x-x,p.y-y); if(d<bestD){best=n.id;bestD=d;} }
  return best;
}
let dragNode=null, panning=false, lastX=0, lastY=0, moved=false;
canvas.addEventListener("mousedown",e=>{ lastX=e.clientX; lastY=e.clientY; moved=false; dragNode=hit(e.clientX,e.clientY); panning=!dragNode; });
addEventListener("mousemove",e=>{
  if(!dragNode&&!panning) return;
  const dx=e.clientX-lastX, dy=e.clientY-lastY; lastX=e.clientX; lastY=e.clientY;
  if(Math.abs(dx)+Math.abs(dy)>2) moved=true;
  if(dragNode){ const p=pos[dragNode]; p.x+=dx/cam.k; p.y+=dy/cam.k; heat=Math.max(heat,0.15); }
  else { cam.x+=dx; cam.y+=dy; }
});
addEventListener("mouseup",e=>{
  if(!moved){ const id=hit(e.clientX,e.clientY); if(id){selectedId=id; showPanel(id);} else closePanel(); }
  dragNode=null; panning=false;
});
canvas.addEventListener("wheel",e=>{ e.preventDefault(); const f=Math.exp(-e.deltaY*0.0012); cam.k=Math.min(3,Math.max(0.3,cam.k*f)); },{passive:false});

function esc(s){ return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function showPanel(id){
  const n=nodeById[id]; if(!n) return;
  const t=n.treatment;
  const axis=AXES.find(a=>a.id===n.axis);
  let html = '<button class="close" onclick="closePanel()">×</button>';
  html += '<h2>'+esc(n.display_name)+'</h2>';
  html += '<div class="meta">'+esc(axis.name)+(n.region? ' · '+esc(n.region.replace(/_/g," ")):'')+' · '+esc(n.status)+'</div>';
  if(t){
    if(t.depth) html += '<div class="section-label">Depth at age '+age+'</div><span class="chip">'+esc(t.depth.replace(/_/g," "))+'</span>';
    html += '<div class="section-label">At age '+age+', this territory is…</div><div class="framing">'+esc(t.framing)+'</div>';
    if(t.vocabulary && t.vocabulary.length) html += '<div class="section-label">Vocabulary</div>'+t.vocabulary.map(v=>'<span class="chip">'+esc(v)+'</span>').join('');
    if(t.avoid && t.avoid.length) html += '<div class="section-label">Stories must avoid</div>'+t.avoid.map(v=>'<span class="chip avoid">'+esc(v)+'</span>').join('');
  } else {
    html += '<div class="section-label">Treatment</div><div class="framing">Age-invariant story hook (no per-age treatment authored).</div>';
  }
  const adj = links.filter(e=>e.kind==="adjacent"&&(e.source===id||e.target===id)).map(e=>nodeById[e.source===id?e.target:e.source].display_name);
  if(adj.length) html += '<div class="section-label">Adjacent territories</div>'+adj.map(v=>'<span class="chip">'+esc(v)+'</span>').join('');
  const panel=document.getElementById("panel"); panel.innerHTML=html; panel.style.display="block";
}
function closePanel(){ selectedId=null; document.getElementById("panel").style.display="none"; }

const togglesEl=document.getElementById("toggles");
for(const a of AXES){
  const label=document.createElement("label");
  label.className="axis-toggle"; label.style.color=a.color; label.style.borderColor=a.color+"55";
  label.innerHTML='<input type="checkbox" checked> '+a.name;
  label.querySelector("input").addEventListener("change",e=>{ enabled[a.id]=e.target.checked; rebuild(); });
  togglesEl.appendChild(label);
}
document.getElementById("age").addEventListener("input",e=>{
  age=+e.target.value; document.getElementById("ageval").textContent=age; rebuild();
});

rebuild();
for(let i=0;i<250;i++) tick();  // settle before first paint
loop();
</script>
</body>
</html>
"""


def build_preview_html() -> str:
    """Render the preview HTML with all six age views embedded."""
    registry = load_default_registry()
    views_by_age = {
        str(age): build_age_view(age, registry).model_dump(exclude_none=True)
        for age in range(MIN_AGE_YEARS, MAX_AGE_YEARS + 1)
    }
    return _HTML_TEMPLATE.replace(
        _GRAPH_DATA_PLACEHOLDER, json.dumps(views_by_age, ensure_ascii=False)
    )


def default_preview_path() -> Path:
    return default_definitions_root() / "preview" / "knowledge_graph_preview.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_preview_path())
    args = parser.parse_args()
    html = build_preview_html()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"wrote preview to {args.output} ({len(html) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
