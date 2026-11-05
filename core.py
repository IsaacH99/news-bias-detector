import os
import json
import requests
import trafilatura
from llama_cpp import Llama
from ddgs import DDGS
from transformers import pipeline

try:
    from laya import Router
except ImportError:
    class Router:
        def __init__(self, *a, **kw): pass
        def predict(self, state, questions): return {"stub": "laya not installed"}

# ---------- model singletons ----------
_MODEL_PATH = os.getenv("LLM_PATH", "./LFM.gguf")
_LLM = None
_ROUTER = None
_bias_clf = None

def get_llm():
    global _LLM
    if _LLM is None:
        _LLM = Llama(model_path=_MODEL_PATH, n_gpu_layers=-1, n_ctx=2048, verbose=False)
    return _LLM

def get_router():
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router(preload=True)
    return _ROUTER

def get_bias_clf():
    global _bias_clf
    if _bias_clf is None:
        # Using a more reliable sentiment/bias model from Cardiff NLP
        _bias_clf = pipeline("text-classification", model="cardiffnlp/twitter-roberta-base-sentiment-latest", tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest")
    return _bias_clf

# ---------- prompts ----------
CLAIM_SP = """You read a news article and extract the checkable factual claims.
Return JSON ONLY in this exact shape:
{
  "claims": [
    {"claim": "...", "importance": "high|medium|low", "type": "factual|opinion"}
  ]
}
Rules:
- Only include statements that could be verified (statistics, dates, events, quotes).
- Skip pure opinion / rhetorical sentences.
- Max 5 claims, ordered by importance."""

VERIFY_SP = """You are a fact-checker. You will be given a CLAIM and a few SEARCH RESULTS from the web.
Determine if the search results SUPPORT the claim, CONTRADICT the claim, or if there is NOT ENOUGH INFO.
Return JSON ONLY in this exact shape:
{
  "verdict": "supported|contradicted|not enough info",
  "reason": "One short sentence explaining why based on the search results."
}
"""

# ---------- helpers ----------
def search_duckduckgo(query, max_results=3):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}" for r in results])
    except Exception as e:
        print("search error:", e)
        return ""

def get_json_from_llama(system_prompt, user_prompt):
    llm = get_llm()
    resp = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=512,
    )
    txt = resp["choices"][0]["message"]["content"]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "raw": txt}

def articledata(url):
    dl = trafilatura.fetch_url(url)
    if not dl: return None, None
    meta = trafilatura.extract_metadata(dl).as_dict()
    text = trafilatura.extract(dl)
    return text, meta

def verify_claim_with_search(claim):
    # 1. Search DuckDuckGo
    search_context = search_duckduckgo(claim)
    if not search_context:
        return {"verdict": "no review found", "reason": "Search failed or returned no results."}
    
    # 2. Ask Local LLM to verify
    prompt = f"CLAIM: {claim}\n\nSEARCH RESULTS:\n{search_context}"
    result = get_json_from_llama(VERIFY_SP, prompt)
    
    if "error" in result:
        return {"verdict": "no review found", "reason": "LLM failed to process."}
        
    return {
        "verdict": result.get("verdict", "unknown").capitalize(),
        "reason": result.get("reason", "No reason provided.")
    }

def detect_bias(text, title):
    clf = get_bias_clf()
    # Analyze just the first 1500 chars to avoid token limits
    result = clf(text[:1500])[0]
    # Map sentiment to a "bias" style label (rough approximation)
    label = result["label"]
    score = result["score"]
    if label == "positive": biased = False
    elif label == "negative": biased = True
    else: biased = False
    return {"label": "LABEL_1" if biased else "LABEL_0", "score": score}

# ---------- main pipeline ----------
def analyze_url(url, max_claims=4):
    text, meta = articledata(url)
    if not text:
        return {"error": "could not fetch / extract article"}

    # Stage 1: claim extraction
    claims_json = get_json_from_llama(CLAIM_SP, text[:6000])
    claims = (claims_json.get("claims") or [])[:max_claims]

    # Stage 2: search & verify claims
    enriched = []
    for c in claims:
        verification = verify_claim_with_search(c.get("claim", ""))
        enriched.append({
            **c,
            "verdict": verification["verdict"],
            "reason": verification["reason"],
            # Fake a factcheck object so the frontend popup doesn't break
            "factchecks": [{"publisher": "Web Search", "review_url": "#", "reason": verification["reason"]}]
        })

    # Stage 3: bias
    bias = detect_bias(text, meta.get("title", ""))

    return {
        "meta": {
            "title": meta.get("title"),
            "date": meta.get("date"),
            "hostname": meta.get("hostname"),
            "url": url,
        },
        "claims": enriched,
        "bias": bias,
        "text": text,
    }