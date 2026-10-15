"""Human-facing HTML report for Skill Assay folders."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def render_owner_report_html(report: dict[str, Any], *, repo_root: Path) -> str:
    from vibe_control.skill_assay.storage import assay_dir

    assay_id = str(report.get("assay_id") or "")
    host = str(report.get("host_id") or "unknown")
    checks = dict(report.get("checks_summary") or {})
    pass_rate = checks.get("pass_rate")
    root = assay_dir(repo_root, assay_id)
    hyps = [h for h in list(report.get("hypotheses") or []) if isinstance(h, dict)]
    facts = list(report.get("facts") or [])
    unknowns = list(report.get("unknowns") or [])
    excerpts = [e for e in list(report.get("run_excerpts") or []) if isinstance(e, dict)]

    hyp_rows = []
    for hyp in hyps:
        verdict = str(hyp.get("verdict") or "unknown")
        claim = str(hyp.get("claim") or "")
        hyp_rows.append(
            f'<li class="verdict-{_esc(verdict)}"><strong>{_esc(verdict)}</strong> — {_esc(claim)}</li>'
        )
    if not hyp_rows:
        hyp_rows.append("<li>（无结论）</li>")

    fact_rows = "".join(f"<li>{_esc(f)}</li>" for f in facts) or "<li>（无）</li>"
    unk_rows = "".join(f"<li>{_esc(u)}</li>" for u in unknowns) or "<li>（无）</li>"

    excerpt_blocks = []
    for item in excerpts:
        excerpt_blocks.append(
            "<section class='excerpt'>"
            f"<h3>第 {_esc(item.get('run_index'))} 轮"
            f"（模型：{_esc(item.get('model_resolved'))}）</h3>"
            f"<pre>{_esc(item.get('excerpt') or '')}</pre>"
            "</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Skill Assay 报告 — {_esc(host)}</title>
  <style>
    :root {{
      --bg: #f6f3ee;
      --ink: #1c1917;
      --muted: #57534e;
      --card: #fffdf8;
      --line: #d6d3d1;
      --pass: #166534;
      --fail: #991b1b;
      --partial: #9a3412;
      --unknown: #57534e;
      --accent: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Songti SC", serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, #dcefea 0%, transparent 55%),
        radial-gradient(900px 400px at 100% 0%, #f0e7d8 0%, transparent 50%),
        var(--bg);
      line-height: 1.55;
    }}
    main {{
      max-width: 880px;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 4rem;
    }}
    header h1 {{
      font-size: clamp(1.8rem, 4vw, 2.4rem);
      margin: 0 0 0.4rem;
      letter-spacing: -0.02em;
    }}
    .meta {{
      color: var(--muted);
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.95rem;
    }}
    .meta code {{
      background: #efebe4;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
    }}
    section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 1.1rem 1.2rem;
      margin-top: 1.1rem;
    }}
    h2 {{
      margin: 0 0 0.7rem;
      font-size: 1.15rem;
      font-family: ui-sans-serif, system-ui, sans-serif;
    }}
    ul {{ margin: 0; padding-left: 1.2rem; }}
    li {{ margin: 0.35rem 0; }}
    .verdict-pass {{ color: var(--pass); }}
    .verdict-fail {{ color: var(--fail); }}
    .verdict-partial {{ color: var(--partial); }}
    .verdict-unknown {{ color: var(--unknown); }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #1c1917;
      color: #f5f5f4;
      padding: 0.9rem 1rem;
      border-radius: 10px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.82rem;
      overflow-x: auto;
    }}
    .share {{
      border-left: 4px solid var(--accent);
    }}
    .pill {{
      display: inline-block;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.8rem;
      padding: 0.15rem 0.55rem;
      border-radius: 999px;
      background: #ccfbf1;
      color: #115e59;
      margin-right: 0.4rem;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="pill">给人看</div>
      <div class="pill">宿主 {_esc(host)}</div>
      <h1>Skill Assay 报告</h1>
      <p class="meta">
        测试编号 <code>{_esc(assay_id)}</code><br/>
        规则检查通过率 <code>{_esc(pass_rate)}</code><br/>
        本地目录 <code>{_esc(root.as_posix())}</code>
      </p>
    </header>

    <section>
      <h2>结论（先看这里）</h2>
      <ul>
        {''.join(hyp_rows)}
      </ul>
    </section>

    <section>
      <h2>已确认的事实</h2>
      <ul>{fact_rows}</ul>
    </section>

    <section>
      <h2>还不知道 / 未测到的事</h2>
      <ul>{unk_rows}</ul>
    </section>

    <section>
      <h2>回复摘录</h2>
      {''.join(excerpt_blocks) or '<p class="meta">无摘录</p>'}
    </section>

    <section class="share">
      <h2>怎么用这份结果</h2>
      <ol>
        <li>人先打开本 HTML，确认结论是否说得通。</li>
        <li>有问题就反馈（这会反过来改进 Skill Assay 场景与检查）。</li>
        <li>没问题就把<strong>整个测试文件夹</strong>打成 zip 发给 skill 维护者；
            或只把 <code>AGENT_PACKET.json</code> 丢给对方的 coding agent。</li>
        <li>同目录还有机器材料：<code>report.json</code> / <code>evidence.json</code> /
            <code>runs/*.assistant_text</code>。</li>
      </ol>
      <p class="meta">打包命令示例：
        <code>vibe skill-assay pack --assay {_esc(assay_id)} --json</code>
      </p>
    </section>
  </main>
</body>
</html>
"""


def write_owner_report_html(repo_root: Path, assay_id: str, html_text: str) -> Path:
    from vibe_control.skill_assay.storage import assay_dir

    path = assay_dir(repo_root, assay_id) / "OWNER_REPORT.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path
