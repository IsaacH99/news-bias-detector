const $ = (id) => document.getElementById(id);

function badgeClass(verdict) {
  const v = (verdict || "").toLowerCase();
  // Red for false stuff
  if (/false|misleading|incorrect|pants|fake|contradicted/.test(v)) return "red";
  // Green for true stuff
  if (/true|correct|accurate|supported/.test(v)) return "green";
  // Gray for unknown
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

    // Note: Using 127.0.0.1 to match your server.py
    const res = await fetch("http://127.0.0.1:8000/analyze", {
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
      
      // Show the LLM's reason
      const reason = c.reason ? `<br><small style="color:#444;"><i>${c.reason}</i></small>` : "";
      
      div.innerHTML = `${c.claim}${badge}${reason}`;
      results.appendChild(div);
    });

    if (data.bias && !data.bias.stub) {
      const biased = data.bias.label === "LABEL_1";
      const b = document.createElement("div");
      b.className = "bias";
      b.innerHTML =
        `<b>Sentiment/Bias:</b> ${biased ? "Negative" : "Neutral/Positive"} (score ${data.bias.score?.toFixed?.(2) ?? data.bias.score})`;
      results.appendChild(b);
    }
  } catch (e) {
    status.textContent = "Failed to fetch — is the backend running?";
    console.error(e);
  }
};