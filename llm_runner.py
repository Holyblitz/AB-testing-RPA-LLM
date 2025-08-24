# llm_runner.py — rapide & robuste (Ollama + Mistral) — LECTURE CACHE OK
import json, time, sys, re, multiprocessing, urllib.request, urllib.error
from pathlib import Path
from hashlib import sha1

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- éviter les warnings d'encodage en console
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ========= CONFIG =========
MODEL = "mistral"                   # reste sur Mistral comme d'hab
OUT = Path("results/results_llm.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SYSTEM = (
    "Tu es un extracteur. Réponds UNIQUEMENT en JSON valide au format EXACT:\n"
    "{\"title\":\"str\",\"company\":\"str\",\"location\":\"str\",\"salary\":\"str\",\"skills\":[\"str\",...]}\n"
    "Pas d'explications."
)

USER_TMPL = (
    "Extrait ces champs depuis le texte ci-dessous.\n"
    "Texte:\n----\n{content}\n----\n"
    "Rappels: Si un champ est introuvable, mets une chaîne vide. "
    "Limite skills à 10 items courts."
)

MAX_CHARS_IN   = 6000               # borne stricte d'entrée pour accélérer en CPU
OLLAMA_URL     = "http://localhost:11434/api/generate"
READ_TIMEOUT_S = 60                 # timeout lecture réponse LLM
CONNECT_TIMEOUT_S = 15              # timeout connexion API
MAX_RUNTIME_S  = 60                 # garde-fou total par URL

# ========= CACHE (lecture) =========
def safe_name(url: str) -> str:
    return sha1(url.encode("utf-8")).hexdigest()[:12]

def read_cached_text(url: str, limit=MAX_CHARS_IN) -> str:
    p = CACHE_DIR / f"{safe_name(url)}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")[:limit]
    return ""

# ========= FETCH & TEXTE =========
def _requests_html(url: str, timeout=12):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def _playwright_text(url: str, timeout_ms=15000):
    # Fallback si anti-bot / DOM dynamique
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        page.goto(url, timeout=timeout_ms)
        page.wait_for_load_state("domcontentloaded")
        try:
            page.wait_for_timeout(400)  # hydratation éventuelle
            node = page.locator("[role='main'], main, article, [data-testid='job-description']").first
            if node.count() == 0:
                node = page.locator("body")
            text = node.inner_text(timeout=1000)
        finally:
            browser.close()
    return text

def html_to_text(url: str, timeout=12):
    try:
        html = _requests_html(url, timeout=timeout)
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script","style","noscript"]):
            t.extract()

        candidates = []
        for sel in ["[data-testid='job-description']", "article", "[role='main']",
                    "main", "[class*='description']"]:
            for n in soup.select(sel):
                txt = n.get_text(separator="\n", strip=True)
                if txt and len(txt) > 200:
                    candidates.append(txt)

        text = max(candidates, key=len) if candidates else soup.get_text(separator="\n")
    except Exception:
        # fallback Playwright (anti-bot / DOM dynamique)
        try:
            text = _playwright_text(url)
        except PWTimeout:
            text = ""

    # nettoyage & borne
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:MAX_CHARS_IN]

# ========= OLLAMA CALL =========
def call_ollama(model: str, prompt: str):
    payload = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM,
        "format": "json",              # force JSON
        "options": {
            "temperature": 0,
            "num_predict": 80,         # sortie courte
            "num_thread": multiprocessing.cpu_count(),
            "num_ctx": 2048,           # contexte réduit pour CPU
            "top_p": 0.9
        },
        "stream": False,
        "keep_alive": "5m"
    }
    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
    )
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
    return r.json()["response"]

def force_json(s: str):
    # sécurité au cas où (format:"json" devrait suffire)
    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}

# ========= RUNNER =========
def run_one(url: str):
    t0 = time.time()
    success, err, pred = True, "", {}
    try:
        # 1) lire le cache si dispo, sinon fallback HTML
        content = read_cached_text(url, limit=MAX_CHARS_IN)
        if not content:
            content = html_to_text(url)
        if not content:
            raise RuntimeError("empty_content")

        # garde-fou budget temps avant LLM
        if time.time() - t0 > MAX_RUNTIME_S:
            raise TimeoutError("budget_exhausted_before_llm")

        user = USER_TMPL.format(content=content)
        raw = call_ollama(MODEL, user)
        pred = force_json(raw)

        # Normaliser les clés attendues
        pred = {
            "title": pred.get("title",""),
            "company": pred.get("company",""),
            "location": pred.get("location",""),
            "salary": pred.get("salary",""),
            "skills": pred.get("skills", [])[:10] if isinstance(pred.get("skills"), list) else []
        }
    except Exception as e:
        success = False
        err = repr(e)

    rec = {
        "id": url,
        "variant": "B_LLM",
        "latency_s": round(time.time() - t0, 3),
        "success": success,
        "error": err,
        "pred": pred
    }
    OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[LLM] {url} -> {success} ({rec['latency_s']}s) err={err}")
    return rec

if __name__ == "__main__":
    # si pas d’argument: prend la 1ʳᵉ URL de data/urls.txt
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        try:
            url = next(u for u in Path("data/urls.txt").read_text(encoding="utf-8").splitlines() if u.strip())
        except Exception:
            url = "https://example.org"
    run_one(url)






