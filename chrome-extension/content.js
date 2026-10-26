chrome.runtime.onMessage.addListener((msg, _sender, _respond) => {
  if (msg.type !== "ANNOTATE") return;
  annotate(msg.payload);
});

function annotate(data) {
  document.querySelectorAll("mark.cbc").forEach((m) => {
    m.replaceWith(...m.childNodes);
  });

  for (const c of data.claims || []) {
    const snippet = (c.claim || "").slice(0, 60).replace(/\s+/g, " ").trim();
    if (snippet.length < 20) continue;
    highlight(snippet, c);
  }
}

function highlight(text, info) {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest("mark.cbc")) continue;
    const i = node.nodeValue.indexOf(text);
    if (i === -1) continue;

    try {
      const range = document.createRange();
      range.setStart(node, i);
      range.setEnd(node, i + text.length);

      const mark = document.createElement("mark");
      mark.className = "cbc";
      const v = (info.verdict || "").toLowerCase();
      const bad = /false|misleading|incorrect|pants|fake/.test(v);
      mark.style.background = bad ? "#ffd6d6" : "#d6ffd6";
      mark.title = info.factchecks?.[0]
        ? `${info.verdict} — ${info.factchecks[0].publisher}\n${info.factchecks[0].review_url}`
        : info.verdict;
      range.surroundContents(mark);
    } catch (e) {
      // range crossed element boundaries — skip
    }
    return;
  }
}