const $ = (id) => document.getElementById(id);

function badgeClass(verdict) {
  const v = (verdict || "").toLowerCase();
  if (/false|misleading|incorrect|pants|fake/.test(v)) return "red";
  if (/true|correct|accurate/.test(v)) return "green";
  return "gray";
}

$("go").onclick = async () => {
  const status = $("status");
  const results = $("results");
  results.innerHTML = "";
  status.textContent = "Analyzing… (10–40 s)";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
      status.textContent = "Open a news article (http/https) first.";
      return;
    }

    const res = await fetch("http://localhost:8000/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: tab.url }),
    });

    if (!res.ok) {
      status.textContent = "Backend error: " + res.status;
      console.error(await res.text());
      return;
    }

    const data = await res.json();

    if (data.error) {
      status.textContent = "Error: " + data.error;
      return;
    }

    chrome.tabs.sendMessage(tab.id, { type: "ANNOTATE", payload: data });

    status.textContent = "";

    const title = document.createElement("div");
    title.innerHTML =
      `<b>${data.meta?.title || "(no title)"}</b><br><small>${data.meta?.hostname || ""}</small>`;
    results.appendChild(title);

    (data.claims || []).forEach((c) => {
      const div = document.createElement("div");
      div.className = "card";
      const badge = `<span class="badge ${badgeClass(c.verdict)}">${c.verdict}</span>`;
      const source = c.factchecks?.[0]
        ? `<br><small><a href="${c.factchecks[0].review_url}" target="_blank">${c.factchecks[0].publisher}</a></small>`
        : "";
      div.innerHTML = `${c.claim}${badge}${source}`;
      results.appendChild(div);
    });

    if (data.bias && !data.bias.stub) {
      const biased = data.bias.label === "LABEL_1";
      const b = document.createElement("div");
      b.className = "bias";
      b.innerHTML =
        `<b>Bias:</b> ${biased ? "Biased" : "Neutral"} (score ${data.bias.score?.toFixed?.(2) ?? data.bias.score})`;
      results.appendChild(b);
    }
  } catch (e) {
    status.textContent = "Failed to fetch — is the backend running?";
    console.error(e);
  }
};