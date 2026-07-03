"""Render a static HTML report from AggregateStats."""
from __future__ import annotations

import html as _html

from compare_batch.aggregate import AggregateStats, DIMENSIONS

_DIM_LABELS = {
    "retrieval_relevance":    "Retrieval Relevance",
    "best_passage_selection": "Best-Passage Selection",
    "multi_angle_coverage":   "Multi-Angle Coverage",
    "doctrinal_completeness": "Doctrinal Completeness",
    "redundancy_rate":        "Redundancy Rate",
}

_DIM_WEIGHTS = {
    "retrieval_relevance":    0.30,
    "best_passage_selection": 0.20,
    "multi_angle_coverage":   0.20,
    "doctrinal_completeness": 0.15,
    "redundancy_rate":        0.15,
}


def _score_color(val: float) -> str:
    if val >= 0.75:
        return "#55cc88"
    if val >= 0.50:
        return "#e8c040"
    return "#e84040"


def _score_td(val: float) -> str:
    color = _score_color(val)
    bar = int(val * 80)
    return (
        f'<td style="text-align:right;padding:4px 10px;color:{color}">'
        f'{val:.3f}'
        f'<div style="display:inline-block;width:80px;height:6px;background:#1a2035;'
        f'vertical-align:middle;margin-left:6px">'
        f'<div style="width:{bar}px;height:6px;background:{color}"></div>'
        f'</div></td>'
    )


def render_report(stats: AggregateStats, records: list[dict]) -> str:
    pipelines = [p.pipeline for p in stats.pipelines]
    p_map = {p.pipeline: p for p in stats.pipelines}

    total_cost = sum(
        (r.get("judge") or {}).get("cost", 0.0)
        + sum(pr.get("total_cost", 0.0) for pr in (r.get("pipeline_results") or []))
        for r in records
    )

    th = lambda label: f'<th style="padding:6px 12px;color:#C4972A">{label}</th>'
    pipeline_headers = "".join(th(p) for p in pipelines)

    def stat_row(label, cell_fn):
        cells = "".join(cell_fn(p_map[p]) for p in pipelines)
        return f'<tr><td style="padding:4px 8px;color:#7A8099">{label}</td>{cells}</tr>'

    # ── Leaderboard ────────────────────────────────────────────────────────
    leaderboard = stat_row("Mean Score (weighted)", lambda p: _score_td(p.mean_total))
    leaderboard += stat_row("Win Rate", lambda p: _score_td(p.win_rate))
    leaderboard += stat_row("Queries scored (n)", lambda p: f'<td style="text-align:right;padding:4px 10px">{p.n}</td>')
    leaderboard += stat_row("Mean duration", lambda p: f'<td style="text-align:right;padding:4px 10px">{p.mean_duration_s:.1f}s</td>')
    leaderboard += stat_row("Mean pipeline cost", lambda p: f'<td style="text-align:right;padding:4px 10px">${p.mean_cost:.5f}</td>')

    # ── Dimension breakdown ────────────────────────────────────────────────
    dim_rows = ""
    for dim in DIMENSIONS:
        label = f'{_DIM_LABELS[dim]} <span style="color:#7A8099;font-size:11px">({int(_DIM_WEIGHTS[dim]*100)}%)</span>'
        dim_rows += stat_row(label, lambda p, d=dim: _score_td(p.mean_dimensions.get(d, 0.0)))

    # ── Category breakdown ─────────────────────────────────────────────────
    cat_rows = ""
    for cat in stats.categories:
        cells = "".join(_score_td(p_map[p].mean_total_by_category.get(cat, 0.0)) for p in pipelines)
        cat_rows += f'<tr><td style="padding:4px 8px;color:#7A8099">{cat}</td>{cells}</tr>'

    cat_win_rows = ""
    for cat in stats.categories:
        cells = "".join(_score_td(p_map[p].win_rate_by_category.get(cat, 0.0)) for p in pipelines)
        cat_win_rows += f'<tr><td style="padding:4px 8px;color:#7A8099">{cat}</td>{cells}</tr>'

    # ── Per-query detail ───────────────────────────────────────────────────
    query_rows = ""
    for r in sorted(records, key=lambda x: x.get("query_idx", 0)):
        scores = {s["pipeline"]: s for s in ((r.get("judge") or {}).get("scores") or [])}
        score_cells = "".join(
            _score_td(scores[p]["weighted_total"]) if p in scores else '<td style="text-align:right;padding:4px 10px;color:#7A8099">—</td>'
            for p in pipelines
        )
        q_text = _html.escape(r.get("query", ""))
        cat = r.get("category", "")
        dur = r.get("duration_s", 0)
        query_rows += (
            f'<tr>'
            f'<td style="padding:4px 8px;font-size:12px">{q_text}</td>'
            f'<td style="padding:4px 8px;color:#7A8099;font-size:11px">{cat}</td>'
            f'<td style="padding:4px 8px;color:#7A8099;font-size:11px">{dur:.0f}s</td>'
            f'{score_cells}'
            f'</tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Compare Batch Report — {stats.n_queries} queries</title>
<style>
  body {{ font-family: monospace; background: #090E1A; color: #EAE6DC; margin: 0; padding: 24px; }}
  h1, h2 {{ color: #C4972A; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align: right; border-bottom: 1px solid #1a2035; }}
  th:first-child {{ text-align: left; }}
  tr:hover td {{ background: #0d1420; }}
  .section {{ background: #111829; padding: 16px 20px; margin: 20px 0; border-left: 3px solid #C4972A; }}
  .meta {{ color: #7A8099; margin-bottom: 24px; font-size: 13px; }}
</style>
</head>
<body>
<h1>Pipeline Compare — Batch Report</h1>
<div class="meta">
  {stats.n_queries} queries &nbsp;·&nbsp; {len(pipelines)} pipelines &nbsp;·&nbsp;
  Total cost: <strong style="color:#C4972A">${total_cost:.2f}</strong>
</div>

<div class="section">
  <h2>Leaderboard</h2>
  <table>
    <tr><th style="text-align:left;padding:6px 12px"></th>{pipeline_headers}</tr>
    {leaderboard}
  </table>
</div>

<div class="section">
  <h2>Dimension Breakdown (means across all queries)</h2>
  <table>
    <tr><th style="text-align:left;padding:6px 12px">Dimension</th>{pipeline_headers}</tr>
    {dim_rows}
  </table>
</div>

<div class="section">
  <h2>Mean Score by Category</h2>
  <table>
    <tr><th style="text-align:left;padding:6px 12px">Category</th>{pipeline_headers}</tr>
    {cat_rows}
  </table>
</div>

<div class="section">
  <h2>Win Rate by Category</h2>
  <table>
    <tr><th style="text-align:left;padding:6px 12px">Category</th>{pipeline_headers}</tr>
    {cat_win_rows}
  </table>
</div>

<div class="section">
  <h2>Per-Query Results</h2>
  <table>
    <tr>
      <th style="text-align:left;padding:6px 12px">Query</th>
      <th style="text-align:left;padding:6px 12px">Category</th>
      <th style="padding:6px 12px">Duration</th>
      {pipeline_headers}
    </tr>
    {query_rows}
  </table>
</div>
</body>
</html>"""
