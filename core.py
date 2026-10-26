import os
import json
import requests
import trafilatura
from llama_cpp import Llama
from ddgs import DDGS

try:
    from laya import Router
except ImportError:
    class Router:
        def __init__(self, *a, **kw):
            pass
        def predict(self, state, questions):
            return {"stub": "laya not installed — bias step skipped"}


# ---------- model singletons (load once) ----------
_MODEL_PATH = os.getenv("LLM_PATH", "./LFM.gguf")
_LLM = None
_ROUTER = None


def get_llm():
    global _LLM
    if _LLM is None:
        _LLM = Llama(
            model_path=_MODEL_PATH,
            n_gpu_layers=-1,
            n_ctx=2048,
            verbose=False,
        )
    return _LLM


def get_router():
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router(preload=True)
    return _ROUTER


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
- Skip pure opinion / rhetorical sentences but you may list them with type "opinion" and importance "low".
- Max 8 claims, ordered by importance."""

BIAS_QUESTIONS = {
    "objectivity": {
        "type": "noul",
        "instructions": "Is the text written in an objective tone? Answer yes/no with a one-line reason.",
    },
    "polarization": {
        "type": "noul",
        "instructions": "Does the text use extreme language that could polarize readers? Quote up to 3 phrases.",
    },
}


# ---------- helpers ----------
def search_duckduckgo(query, max_results=5):
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print("search error:", e)
        return []


def get_json_from_llama(system_prompt, user_prompt):
    llm = get_llm()
    resp = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
    )
    txt = resp["choices"][0]["message"]["content"]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "raw_output": txt}


def articledata(url):
    dl = trafilatura.fetch_url(url)
    if not dl:
        return None, None
    meta = trafilatura.extract_metadata(dl).as_dict()
    text = trafilatura.extract(dl)
    return text, meta


def fact_check_search(query, api_key=None):
    api_key = api_key or os.getenv("GOOGLE_FACTCHECK_KEY")
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={"query": query, "key": api_key},
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        print("fact check error:", e)
        return []
    out = []
    for c in r.json().get("claims", []):
        for rev in c.get("claimReview", []):
            out.append({
                "claim_text": c.get("text", ""),
                "rating": rev.get("textualRating", ""),
                "publisher": rev.get("publisher", {}).get("name", ""),
                "review_url": rev.get("url", ""),
                "review_date": rev.get("reviewDate", ""),
            })
    return out


def detect_bias(text, title):
    router = get_router()
    state = {"title": title, "text": text}
    return router.predict(state, BIAS_QUESTIONS)


# ---------- main pipeline ----------
def analyze_url(url, google_key=None, max_claims=5):
    text, meta = articledata(url)
    if not text:
        return {"error": "could not fetch / extract article"}

    # Stage 1: claim extraction
    claims_json = get_json_from_llama(CLAIM_SP, text[:6000])
    claims = (claims_json.get("claims") or [])[:max_claims]

    # Stage 2: fact check
    enriched = []
    for c in claims:
        hits = fact_check_search(c.get("claim", ""), google_key)
        enriched.append({
            **c,
            "factchecks": hits,
            "verdict": hits[0]["rating"] if hits else "no review found",
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