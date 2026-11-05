const $ = (id) => document.getElementById(id);

function getBadgeClass(verdict) {
  const v = (verdict || "").toLowerCase();
  if (/false|misleading|incorrect|fake|contradicted/.test(v)) return "red";
  if (/true|correct|accurate|supported/.test(v)) return "green";
  return "gray";
}

$("go").onclick = async () => {
  const status = $("status");
  const results = $("results");
  const btn = $("go");
  
  results.innerHTML = "";
  status.textContent = "Analyzing... (This may take 10–30 seconds)";
  btn.disabled = true;
  btn.textContent = "Analyzing...";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
      status.textContent = "Please open a news article (http/https) first.";
      return;
    }

    const res = await fetch("http://127.0.0.1:8000/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: tab.url }),
    });

    if (!res.ok) {
      status.textContent = "Backend error: " + res.status;
      return;
    }

    const data = await res.json();

    if (data.error) {
      status.textContent = "Error: " + data.error;
      return;
    }

    chrome.tabs.sendMessage(tab.id, { type: "ANNOTATE", payload: data });
    status.textContent = "";

    // Article Header
    const header = document.createElement("div");
    header.className = "article-header";
    header.innerHTML = `
      <div class="article-title">${data.meta?.title || "(No title found)"}</div>
      <div class="article-source">${data.meta?.hostname || ""}</div>
    `;
    results.appendChild(header);

    // Claims
    (data.claims || []).forEach((c) => {
      const div = document.createElement("div");
      div.className = "card";
      
      const badge = `<span class="badge ${getBadgeClass(c.verdict)}">${c.verdict}</span>`;
      const reason = c.reason ? `<div class="reason">"${c.reason}"</div>` : "";
      
      div.innerHTML = `
        <div class="claim-text">${c.claim}</div>
        <div class="badge-row">${badge}</div>
        ${reason}
      `;
      results.appendChild(div);
    });

    // Bias / Tone Section
    if (data.bias && !data.bias.stub) {
      const biased = data.bias.label === "LABEL_1";
      const tone = biased ? "Emotional / Negative" : "Neutral / Objective";
      const score = data.bias.score?.toFixed?.(2) ?? data.bias.score;
      
      const b = document.createElement("div");
      b.className = "bias-container";
      b.innerHTML = `
        <div class="bias-label">Article Tone</div>
        <div class="bias-score">${tone} &middot; ${score}</div>
      `;
      results.appendChild(b);
    }

  } catch (e) {
    status.textContent = "Failed to connect. Is the Python server running?";
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze Page";
  }
};