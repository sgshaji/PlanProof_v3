/* PlanProof Research Demo — SSE client and dynamic stage rendering. */

(function () {
  "use strict";

  const stagesEl = document.getElementById("pipeline-stages");
  const uploadZone = document.getElementById("upload-zone");
  const fileInput = document.getElementById("file-input");

  let stageCounter = 0;

  // ── File Upload ──

  if (uploadZone && fileInput) {
    uploadZone.addEventListener("click", () => fileInput.click());

    uploadZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", () => {
      uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadZone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        uploadFiles(e.dataTransfer.files);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        uploadFiles(fileInput.files);
      }
    });
  }

  async function uploadFiles(files) {
    const formData = new FormData();
    for (const f of files) {
      formData.append("files", f);
    }

    showLoading("Uploading files...");

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (data.run_id) {
        connectSSE(data.run_id);
      }
    } catch (err) {
      showError("Upload failed: " + err.message);
    }
  }

  // ── Test Set Selection ──

  window.runTestSet = async function (setId) {
    stageCounter = 0;
    stagesEl.innerHTML = "";
    showLoading("Starting pipeline on " + setId + "...");

    try {
      const res = await fetch("/api/run-test-set/" + encodeURIComponent(setId));
      const data = await res.json();
      if (data.run_id) {
        connectSSE(data.run_id);
      } else if (data.error) {
        showError(data.error);
      }
    } catch (err) {
      showError("Failed to start: " + err.message);
    }
  };

  // ── SSE Connection ──

  function connectSSE(runId) {
    stageCounter = 0;
    stagesEl.innerHTML = "";
    showLoading("Running pipeline...");

    const source = new EventSource("/api/stream/" + runId);

    source.onmessage = function (event) {
      const msg = JSON.parse(event.data);

      if (msg.error) {
        removeLoading();
        showError(msg.error);
        source.close();
        return;
      }

      if (msg.stage === "complete") {
        removeLoading();
        stagesEl.insertAdjacentHTML(
          "beforeend",
          '<div class="complete-banner">Pipeline complete</div>'
        );
        source.close();
        return;
      }

      removeLoading();
      renderStage(msg);
      showLoading("Processing next stage...");
    };

    source.onerror = function () {
      removeLoading();
      source.close();
    };
  }

  // ── Stage Rendering ──

  function renderStage(msg) {
    stageCounter++;
    const renderer = stageRenderers[msg.stage];
    if (!renderer) return;

    const stageClass = "stage-" + msg.stage;
    const html = `
      <div class="stage ${stageClass}">
        <div class="stage-header">
          <span class="stage-badge">${stageCounter}</span>
          <span class="stage-title">${escapeHtml(msg.title)}</span>
        </div>
        <div class="stage-body">${renderer(msg.data)}</div>
      </div>`;
    stagesEl.insertAdjacentHTML("beforeend", html);
  }

  const stageRenderers = {
    classification: renderClassification,
    extraction: renderExtraction,
    snkg: renderSNKG,
    reconciliation: renderReconciliation,
    sable: renderSABLE,
    verdicts: renderVerdicts,
    ablation: renderAblation,
  };

  // ── Classification ──

  function renderClassification(data) {
    if (!data.documents || !data.documents.length) {
      return '<p class="text-muted">No documents found.</p>';
    }
    let html = '<div class="card-grid">';
    for (const doc of data.documents) {
      const badgeClass = "badge-" + doc.doc_type.toLowerCase();
      html += `
        <div class="card">
          <div style="font-weight:600; font-size:0.85rem; margin-bottom:0.4rem;">
            ${escapeHtml(doc.filename)}
          </div>
          <span class="badge ${badgeClass}">${escapeHtml(doc.doc_type)}</span>
          <span style="font-size:0.78rem; color:var(--text-muted); margin-left:0.5rem;">
            conf: ${doc.confidence}
          </span>
          ${doc.has_text_layer ? '<span style="font-size:0.7rem; color:var(--green); margin-left:0.5rem;">TEXT</span>' : ""}
        </div>`;
    }
    html += "</div>";
    return html;
  }

  // ── Extraction ──

  function renderExtraction(data) {
    if (!data.entities || !data.entities.length) {
      return '<p style="color:var(--text-muted)">No entities extracted.</p>';
    }
    let html = '<table class="entity-table"><thead><tr>';
    html += "<th>Attribute</th><th>Value</th><th>Unit</th><th>Confidence</th><th>Source</th><th>Method</th>";
    html += "</tr></thead><tbody>";
    for (const e of data.entities) {
      const conf = e.confidence;
      const confClass = conf >= 0.8 ? "conf-high" : conf >= 0.5 ? "conf-medium" : "conf-low";
      const confBar = conf != null
        ? `${conf} <span class="confidence-bar"><span class="confidence-fill ${confClass}" style="width:${Math.round(conf * 100)}%"></span></span>`
        : "N/A";
      html += `<tr>
        <td><strong>${escapeHtml(e.attribute || "")}</strong></td>
        <td>${escapeHtml(String(e.value || ""))}</td>
        <td>${escapeHtml(e.unit || "-")}</td>
        <td>${confBar}</td>
        <td style="font-size:0.75rem">${escapeHtml(e.source || "")}</td>
        <td style="font-size:0.75rem">${escapeHtml(e.method || "")}</td>
      </tr>`;
    }
    html += "</tbody></table>";
    return html;
  }

  // ── SNKG ──

  function renderSNKG(data) {
    if (!data.nodes || !data.nodes.length) {
      return '<p style="color:var(--text-muted)">No graph data.</p>';
    }
    let html = '<div class="snkg-container">';
    for (const node of data.nodes) {
      const cls = node.type ? node.type.toLowerCase() : "";
      html += `<span class="snkg-node ${cls}">${escapeHtml(node.label)}</span>`;
    }
    html += "</div>";
    if (data.edges && data.edges.length) {
      html += `<p style="text-align:center; font-size:0.75rem; color:var(--text-muted); margin-top:0.5rem;">
        ${data.edges.length} relationships &middot; ${data.nodes.length} nodes
      </p>`;
    }
    return html;
  }

  // ── Reconciliation ──

  function renderReconciliation(data) {
    if (!data.items || !data.items.length) {
      return '<p style="color:var(--text-muted)">No reconciliation results.</p>';
    }
    let html = '<table class="entity-table"><thead><tr>';
    html += "<th>Attribute</th><th>Status</th><th>Best Value</th><th>Sources</th>";
    html += "</tr></thead><tbody>";
    for (const item of data.items) {
      const badgeClass = "badge-" + item.status.toLowerCase();
      html += `<tr>
        <td><strong>${escapeHtml(item.attribute)}</strong></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(item.status)}</span></td>
        <td>${escapeHtml(item.best_value || "-")}</td>
        <td>${item.source_count}</td>
      </tr>`;
    }
    html += "</tbody></table>";
    return html;
  }

  // ── SABLE ──

  function renderSABLE(data) {
    if (!data.rules || !data.rules.length) {
      return '<p style="color:var(--text-muted)">No SABLE results.</p>';
    }
    let html = '<div class="gauge-grid">';
    for (const rule of data.rules) {
      const belief = rule.belief || 0;
      const plausibility = rule.plausibility || 0;
      const statusClass = "status-" + rule.status.toLowerCase();
      const svg = makeGaugeSVG(belief, plausibility);
      html += `
        <div class="gauge">
          <div class="gauge-label">${escapeHtml(rule.rule_id)}</div>
          ${svg}
          <div class="gauge-status ${statusClass}">${escapeHtml(rule.status)}</div>
          <div style="font-size:0.7rem; color:var(--text-muted); margin-top:0.25rem;">
            Bel: ${belief.toFixed(3)} &middot; Pl: ${plausibility.toFixed(3)}
          </div>
          ${rule.blocking_reason && rule.blocking_reason !== "NONE"
            ? `<div style="font-size:0.65rem; color:var(--red); margin-top:0.15rem;">${escapeHtml(rule.blocking_reason)}</div>`
            : ""}
        </div>`;
    }
    html += "</div>";
    return html;
  }

  function makeGaugeSVG(belief, plausibility) {
    const size = 70;
    const cx = size / 2;
    const cy = size / 2;
    const r = 28;
    const circumference = 2 * Math.PI * r;
    const beliefOffset = circumference * (1 - belief);
    const plausOffset = circumference * (1 - plausibility);

    const beliefColor = belief >= 0.7 ? "#059669" : belief >= 0.4 ? "#d97706" : "#dc2626";

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e5e7eb" stroke-width="5"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#d1d5db" stroke-width="5"
        stroke-dasharray="${circumference}" stroke-dashoffset="${plausOffset}"
        transform="rotate(-90 ${cx} ${cy})" opacity="0.4"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${beliefColor}" stroke-width="5"
        stroke-dasharray="${circumference}" stroke-dashoffset="${beliefOffset}"
        transform="rotate(-90 ${cx} ${cy})" stroke-linecap="round"/>
      <text x="${cx}" y="${cy + 1}" text-anchor="middle" dominant-baseline="middle"
        font-size="11" font-weight="700" fill="#1a1a2e">${(belief * 100).toFixed(0)}%</text>
    </svg>`;
  }

  // ── Verdicts ──

  function renderVerdicts(data) {
    if (!data.verdicts || !data.verdicts.length) {
      return '<p style="color:var(--text-muted)">No verdicts.</p>';
    }
    let html = '<div class="verdict-grid">';
    for (const v of data.verdicts) {
      const outcome = v.outcome.toLowerCase();
      const cardClass =
        outcome === "pass" ? "verdict-pass" :
        outcome === "fail" ? "verdict-fail" :
        outcome === "partially_assessable" ? "verdict-pa" :
        outcome === "not_assessable" ? "verdict-na" :
        "verdict-error";
      const outcomeColor =
        outcome === "pass" ? "var(--green)" :
        outcome === "fail" ? "var(--red)" :
        outcome === "partially_assessable" ? "var(--amber)" :
        "var(--text-muted)";

      html += `
        <div class="verdict-card ${cardClass}">
          <div class="verdict-rule">${escapeHtml(v.rule_id)}</div>
          ${v.description ? `<div class="verdict-desc">${escapeHtml(v.description)}</div>` : ""}
          <div class="verdict-outcome" style="color:${outcomeColor}">${escapeHtml(v.outcome)}</div>
          <div class="verdict-explanation">${escapeHtml(v.explanation)}</div>
        </div>`;
    }
    html += "</div>";
    return html;
  }

  // ── Ablation ──

  function renderAblation(data) {
    if (!data || Object.keys(data).length === 0) {
      return '<p style="color:var(--text-muted)">No ablation data available.</p>';
    }

    const labels = {
      full_system: "Full System (with SABLE)",
      ablation_d: "Without SABLE (Ablation D)",
    };

    let html = '<div class="ablation-grid">';
    for (const [config, stats] of Object.entries(data)) {
      html += `
        <div class="ablation-card">
          <h4>${escapeHtml(labels[config] || config)}</h4>
          <div class="ablation-stat"><span class="label">PASS</span><span class="value" style="color:var(--green)">${stats.pass}</span></div>
          <div class="ablation-stat"><span class="label">True FAIL</span><span class="value" style="color:var(--red)">${stats.true_fail}</span></div>
          <div class="ablation-stat"><span class="label">False FAIL</span><span class="value" style="color:#f43f5e">${stats.false_fail}</span></div>
          <div class="ablation-stat"><span class="label">Partially Assessable</span><span class="value" style="color:var(--amber)">${stats.pa}</span></div>
          <div class="ablation-stat"><span class="label">Not Assessable</span><span class="value" style="color:var(--text-muted)">${stats.na}</span></div>
        </div>`;
    }
    html += "</div>";
    return html;
  }

  // ── Figures Gallery ──

  window.openLightbox = function (src) {
    const lb = document.getElementById("lightbox");
    const img = document.getElementById("lightbox-img");
    if (lb && img) {
      img.src = src;
      lb.classList.add("active");
    }
  };

  window.closeLightbox = function () {
    const lb = document.getElementById("lightbox");
    if (lb) lb.classList.remove("active");
  };

  // ── Utilities ──

  function showLoading(message) {
    removeLoading();
    stagesEl.insertAdjacentHTML(
      "beforeend",
      `<div class="loading" id="loading-indicator"><span class="spinner"></span>${escapeHtml(message)}</div>`
    );
    scrollToBottom();
  }

  function removeLoading() {
    const el = document.getElementById("loading-indicator");
    if (el) el.remove();
  }

  function showError(message) {
    stagesEl.insertAdjacentHTML(
      "beforeend",
      `<div class="warning-banner">${escapeHtml(message)}</div>`
    );
  }

  function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  function escapeHtml(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }
})();
