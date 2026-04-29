(function () {
  var TRACE = window.GLASSPIPE_TRACE;
  if (!TRACE) return;

  var RUN = TRACE.run;
  var SPANS = TRACE.spans;
  var activeSpanId = null;

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatJson(obj) {
    if (obj === null || obj === undefined) {
      return '<span style="color:var(--text-3)">null</span>';
    }
    var raw = JSON.stringify(obj, null, 2);
    raw = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    raw = raw.replace(
      /&quot;\[REDACTED\]&quot;/g,
      '<span class="redacted">&quot;[REDACTED]&quot;</span>'
    );
    return raw;
  }

  function kindClass(kind, status) {
    return status === 'error' ? 'kind-error' : 'kind-' + kind;
  }

  function renderDetail(sp) {
    var kc = kindClass(sp.kind, sp.status);
    var statusCls = 'badge-' + (sp.status || 'ok');

    var html = '<div class="detail-header">' +
      '<span class="kind-dot ' + kc + '" style="font-size:10px">&#9679;</span>' +
      '<span class="mono">' + esc(sp.name) + '</span>' +
      '<span class="badge ' + statusCls + '">' + esc(sp.status || 'ok') + '</span>' +
      '</div>' +
      '<dl class="detail-grid">' +
      '<dt>kind</dt><dd class="mono">' + esc(sp.kind) + '</dd>' +
      '<dt>duration</dt><dd class="mono">' + sp.duration_ms + 'ms</dd>';

    if (sp.metadata) {
      var m = sp.metadata;
      if (m.model)
        html += '<dt>model</dt><dd class="mono">' + esc(m.model) + '</dd>';
      if (m.prompt_tokens != null)
        html += '<dt>tokens</dt><dd class="mono">' + m.prompt_tokens + ' in / ' + m.completion_tokens + ' out</dd>';
      if (m.cost_usd != null)
        html += '<dt>cost</dt><dd class="mono">$' + Number(m.cost_usd).toFixed(6) + '</dd>';
    }

    html += '</dl>';

    if (sp.input !== null && sp.input !== undefined) {
      html += '<div class="detail-section">' +
        '<div class="detail-section-label">input</div>' +
        '<pre class="detail-json">' + formatJson(sp.input) + '</pre>' +
        '</div>';
    }
    if (sp.output !== null && sp.output !== undefined) {
      html += '<div class="detail-section">' +
        '<div class="detail-section-label">output</div>' +
        '<pre class="detail-json">' + formatJson(sp.output) + '</pre>' +
        '</div>';
    }

    return html;
  }

  function buildWaterfall() {
    var pane = document.getElementById('demo-waterfall');
    if (!pane) return;

    var durationMs = RUN.duration_ms;
    var spanList = [];
    var keys = Object.keys(SPANS);
    for (var i = 0; i < keys.length; i++) {
      spanList.push(SPANS[keys[i]]);
    }

    var ticks = [
      Math.round(durationMs * 0),
      Math.round(durationMs * 0.25),
      Math.round(durationMs * 0.5),
      Math.round(durationMs * 0.75),
      Math.round(durationMs)
    ];

    var rulerHtml = '<div class="ruler">';
    for (var t = 0; t < ticks.length; t++) {
      rulerHtml += '<span>' + ticks[t] + 'ms</span>';
    }
    rulerHtml += '</div>';

    var rowsHtml = '';
    for (var s = 0; s < spanList.length; s++) {
      var sp = spanList[s];
      var kc = kindClass(sp.kind, sp.status);
      rowsHtml += '<div class="span-row">' +
        '<div class="span-label mono" title="' + esc(sp.name) + '">' + esc(sp.name) + '</div>' +
        '<div class="span-track">' +
        '<div class="span-bar ' + kc + '" ' +
        'style="left:' + sp.start_pct + '%;width:' + sp.width_pct + '%" ' +
        'data-span-id="' + sp.id + '" ' +
        'title="' + esc(sp.name) + ' &middot; ' + sp.duration_ms + 'ms">' +
        '</div></div></div>';
    }

    pane.innerHTML = rulerHtml + rowsHtml;

    var bars = pane.querySelectorAll('.span-bar');
    for (var b = 0; b < bars.length; b++) {
      bars[b].addEventListener('click', onSpanClick);
    }
  }

  function onSpanClick() {
    var id = this.getAttribute('data-span-id');
    var panel = document.getElementById('demo-detail');
    if (!panel) return;

    var prev = document.querySelectorAll('.span-bar.active');
    for (var i = 0; i < prev.length; i++) {
      prev[i].classList.remove('active');
    }

    if (activeSpanId === id) {
      activeSpanId = null;
      panel.innerHTML = '<p class="detail-hint">&larr; Click a span to inspect it</p>';
      return;
    }

    activeSpanId = id;
    this.classList.add('active');
    panel.innerHTML = renderDetail(SPANS[id]);
  }

  function buildRunCard() {
    var card = document.getElementById('demo-run-card');
    if (!card) return;

    var spanCount = Object.keys(SPANS).length;
    card.innerHTML = '<div class="run-card-left">' +
      '<div class="run-card-header">' +
      '<h1 class="run-name">' + esc(RUN.name) + '</h1>' +
      '<span class="badge badge-ok">ok</span>' +
      '</div>' +
      '<div class="run-meta">' +
      '<span class="mono">' + RUN.duration_ms + 'ms</span>' +
      '<span class="sep">&middot;</span>' +
      '<span>' + spanCount + ' spans</span>' +
      '<span class="sep">&middot;</span>' +
      '<span>5 kinds: custom, tool, llm</span>' +
      '</div></div>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      buildRunCard();
      buildWaterfall();
    });
  } else {
    buildRunCard();
    buildWaterfall();
  }
})();
