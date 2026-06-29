# services/api/app/routes/compare.py
"""Compare endpoint: runs N pipelines sequentially and scores results."""
from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.rag.compare import judge, overlap
from app.rag.compare import runner as compare_runner
from app.rag.pipelines.registry import PIPELINES

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    query: str
    collections: list[str]
    quota: int = 4
    pipelines: list[str]

    @field_validator("pipelines")
    @classmethod
    def validate_pipeline_names(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in PIPELINES]
        if invalid:
            raise ValueError(f"Unknown pipelines: {invalid}. Valid: {sorted(PIPELINES)}")
        if not v:
            raise ValueError("At least one pipeline required")
        return v


async def _optional_auth(request: Request) -> AuthUser | None:
    if settings.app_env == "development":
        return None
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from app.auth.verify import verify_supabase_jwt
    bearer = HTTPBearer(auto_error=False)
    credentials: HTTPAuthorizationCredentials | None = await bearer(request)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return await verify_supabase_jwt(credentials.credentials)


@router.post("/search/compare")
async def compare_search(
    body: CompareRequest,
    user: AuthUser | None = Depends(_optional_auth),
) -> dict:
    user_id = user.user_id if user else None
    try:
        pipeline_results = await compare_runner.run(
            query=body.query,
            collections=body.collections,
            quota=body.quota,
            pipeline_names=body.pipelines,
            user_id=user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    overlap_report = overlap.run(pipeline_results)
    judge_report = await judge.run(body.query, pipeline_results, overlap_report)

    return {
        "query": body.query,
        "pipeline_results": [dataclasses.asdict(r) for r in pipeline_results],
        "overlap": dataclasses.asdict(overlap_report),
        "judge": dataclasses.asdict(judge_report),
    }


_HTML_VIEWER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipeline Compare</title>
<style>
  body { font-family: monospace; background: #090E1A; color: #EAE6DC; margin: 0; padding: 16px; }
  h1 { color: #C4972A; }
  form { margin-bottom: 24px; }
  label { display: block; margin: 8px 0 4px; color: #7A8099; }
  input[type=text] { width: 600px; padding: 8px; background: #111829; border: 1px solid #C4972A; color: #EAE6DC; }
  input[type=number] { width: 80px; padding: 8px; background: #111829; border: 1px solid #C4972A; color: #EAE6DC; }
  .checks { display: flex; gap: 16px; flex-wrap: wrap; }
  .checks label { display: flex; align-items: center; gap: 6px; color: #EAE6DC; cursor: pointer; }
  button { margin-top: 16px; padding: 10px 24px; background: #C4972A; color: #090E1A; border: none; cursor: pointer; font-weight: bold; font-size: 14px; }
  button:hover { background: #d4a73a; }
  #status { color: #7A8099; margin: 8px 0; }
  #results { margin-top: 24px; }
  .pipeline-col { display: inline-block; vertical-align: top; width: 48%; margin: 1%; background: #111829; padding: 12px; box-sizing: border-box; }
  .pipeline-col h2 { color: #C4972A; margin: 0 0 8px; }
  .chunk { background: #0d1420; padding: 8px; margin: 8px 0; border-left: 3px solid #7A8099; }
  .chunk.shared { border-left-color: #55cc88; }
  .chunk.unique { border-left-color: #e8c040; }
  .chunk-ref { color: #C4972A; font-size: 12px; }
  .chunk-score { color: #7A8099; font-size: 11px; float: right; }
  .chunk-content { margin-top: 6px; font-size: 13px; line-height: 1.4; }
  .section { background: #111829; padding: 12px; margin: 16px 0; }
  .section h3 { color: #C4972A; margin: 0 0 8px; }
  .score-bar { background: #0d1420; padding: 8px; margin: 4px 0; }
  .score-fill { height: 8px; background: #55cc88; display: inline-block; }
  .judge-score { color: #EAE6DC; }
  .judge-reasoning { color: #7A8099; font-size: 12px; margin-top: 4px; }
  .overlap-tag { display: inline-block; padding: 2px 6px; font-size: 11px; margin: 2px; background: #55cc8844; border: 1px solid #55cc88; }
  details { margin: 8px 0; }
  summary { cursor: pointer; color: #7A8099; }
  pre { background: #0d1420; padding: 12px; overflow-x: auto; font-size: 11px; max-height: 400px; }
</style>
</head>
<body>
<h1>Pipeline Compare</h1>
<form id="compareForm">
  <label>Query</label>
  <input type="text" id="query" placeholder="what does the Church teach about suffering?" value="">
  <label>Collections</label>
  <div class="checks" id="collectionChecks"></div>
  <label>Pipelines</label>
  <div class="checks" id="pipelineChecks"></div>
  <label>Quota (per collection)</label>
  <input type="number" id="quota" value="4" min="1" max="10">
  <br>
  <button type="submit">Run Compare</button>
</form>
<div id="status"></div>
<div id="results"></div>

<script>
const COLLECTIONS = ["bible","catechism","summa","encyclicals","councils","church-fathers","medieval","canon-law","apostolic-exhortations","papal-documents"];
const PIPELINES = ["s2_5_cohere","s2_5_haiku","s4_cohere","s4_haiku"];

const collDiv = document.getElementById("collectionChecks");
COLLECTIONS.forEach(c => {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" value="${c}" ${["bible","catechism","summa"].includes(c) ? "checked" : ""}> ${c}`;
  collDiv.appendChild(l);
});
const pipeDiv = document.getElementById("pipelineChecks");
PIPELINES.forEach(p => {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" value="${p}" ${["s2_5_haiku","s4_haiku"].includes(p) ? "checked" : ""}> ${p}`;
  pipeDiv.appendChild(l);
});

document.getElementById("compareForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = document.getElementById("query").value.trim();
  const quota = parseInt(document.getElementById("quota").value);
  const collections = [...document.querySelectorAll("#collectionChecks input:checked")].map(i => i.value);
  const pipelines = [...document.querySelectorAll("#pipelineChecks input:checked")].map(i => i.value);
  if (!query || !collections.length || !pipelines.length) return;

  document.getElementById("status").textContent = "Running pipelines sequentially...";
  document.getElementById("results").innerHTML = "";

  try {
    const res = await fetch("/v1/search/compare", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, collections, quota, pipelines}),
    });
    if (!res.ok) { document.getElementById("status").textContent = `Error: ${res.status} ${await res.text()}`; return; }
    const data = await res.json();
    document.getElementById("status").textContent = `Done. ${data.pipeline_results.length} pipelines compared.`;
    renderResults(data);
  } catch(err) {
    document.getElementById("status").textContent = `Error: ${err.message}`;
  }
});

function renderResults(data) {
  const sharedIds = new Set(data.overlap.shared || []);
  const uniqueIds = new Set(Object.keys(data.overlap.unique || {}));
  const out = document.getElementById("results");

  // Pipeline columns
  const colsDiv = document.createElement("div");
  data.pipeline_results.forEach(pr => {
    const col = document.createElement("div");
    col.className = "pipeline-col";
    const timing = pr.total_duration_s.toFixed(2);
    const cost = pr.total_cost.toFixed(5);
    col.innerHTML = `<h2>${pr.pipeline} <small style="color:#7A8099;font-size:12px">${timing}s | $${cost}</small></h2>`;
    (pr.chunks || []).forEach(chunk => {
      const isShared = sharedIds.has(chunk.chunk_id);
      const isUnique = uniqueIds.has(chunk.chunk_id);
      const cls = isShared ? "shared" : isUnique ? "unique" : "";
      const tag = isShared ? "SHARED" : isUnique ? "UNIQUE" : "";
      col.innerHTML += `<div class="chunk ${cls}">
        <span class="chunk-ref">${chunk.source?.reference || chunk.source?.collection || ""}</span>
        <span class="chunk-score">${(chunk.reranker_score||0).toFixed(3)} ${tag}</span>
        <div class="chunk-content">${(chunk.content||"").substring(0,300)}${chunk.content?.length>300?"\\u2026":""}</div>
      </div>`;
    });
    colsDiv.appendChild(col);
  });
  out.appendChild(colsDiv);

  // Overlap section
  const overlapSec = document.createElement("div");
  overlapSec.className = "section";
  overlapSec.innerHTML = `<h3>Overlap</h3>
    <div><strong>Shared (all pipelines):</strong> ${data.overlap.shared?.length || 0} chunks</div>
    <div><strong>Partial:</strong> ${Object.keys(data.overlap.partial||{}).length} chunks</div>
    <div><strong>Unique:</strong> ${Object.keys(data.overlap.unique||{}).length} chunks</div>`;
  out.appendChild(overlapSec);

  // Judge section
  const judgeSec = document.createElement("div");
  judgeSec.className = "section";
  judgeSec.innerHTML = `<h3>Judge (${data.judge.model}) — $${(data.judge.cost||0).toFixed(5)}</h3>`;
  (data.judge.scores||[]).forEach(s => {
    judgeSec.innerHTML += `<div class="score-bar">
      <span class="judge-score">${s.pipeline}: ${s.score.toFixed(2)} </span>
      <span class="score-fill" style="width:${Math.round(s.score*200)}px"></span>
      <div class="judge-reasoning">${s.reasoning}</div>
    </div>`;
  });
  judgeSec.innerHTML += `<div style="margin-top:8px;color:#7A8099">${data.judge.overall_reasoning||""}</div>`;
  out.appendChild(judgeSec);

  // Raw JSON
  const rawSec = document.createElement("details");
  rawSec.innerHTML = `<summary>Raw JSON</summary><pre>${JSON.stringify(data, null, 2)}</pre>`;
  out.appendChild(rawSec);
}
</script>
</body>
</html>"""


@router.get("/search/compare/view", response_class=HTMLResponse)
async def compare_view(request: Request) -> HTMLResponse:
    """Return a self-contained HTML viewer for pipeline comparison.

    Only accessible from localhost in non-development environments.
    """
    if settings.app_env != "development":
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="Localhost only")
    return HTMLResponse(content=_HTML_VIEWER)
