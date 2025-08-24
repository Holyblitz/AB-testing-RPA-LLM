# rpa_runner.py (OK: wait sur le titre, champs optionnels, + cache pour LLM)
import json, time, sys, re, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

OUT = Path("results/results_rpa.jsonl")
SS_DIR = Path("results/screens")
CACHE_DIR = Path("cache")
for d in [OUT.parent, SS_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SEL_TITLE    = "h1, h2, [data-testid='job-title'], .job-title, .two-line-clamp"
SEL_COMPANY  = "[data-testid='company'], [data-qa*='company'], a[href*='/companies/'], [itemprop='hiringOrganization'], .employer, .company"
SEL_LOCATION = "[data-testid='location'], [class*='location'], li[aria-label*='Lieu'], [itemprop='address'], [data-testid*='address']"
SEL_SALARY   = "[data-testid='salary'], [class*='salary'], [itemprop='salary']"
SEL_SKILLS   = "[data-testid*='skills'] li, ul li"

def clean(s: str) -> str:
    if not s: return ""
    return re.sub(r"\s+", " ", s).strip()

def safe_name(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]

def accept_cookies(page):
    for txt in ["Tout accepter","Accepter tout","Accept all","J'accepte"]:
        btn = page.get_by_role("button", name=txt)
        if btn.count() > 0:
            try:
                btn.first.click(timeout=1500)
                break
            except:
                pass

def get_text(page, selector, timeout_ms=0):
    """Essaie de lire du texte sans bloquer. Si pas trouvé → ''. """
    try:
        loc = page.locator(selector).first
        if timeout_ms and timeout_ms > 0:
            return clean(loc.text_content(timeout=timeout_ms) or "")
        return clean(loc.text_content(timeout=1) or "")
    except Exception:
        return ""

def extract(page):
    title   = get_text(page, SEL_TITLE, timeout_ms=100)  # déjà attendu avant
    company = get_text(page, SEL_COMPANY)
    location= get_text(page, SEL_LOCATION)
    salary  = get_text(page, SEL_SALARY)
    # skills (optionnel)
    skills = []
    try:
        raw = [clean(s) for s in page.locator(SEL_SKILLS).all_text_contents()]
        seen=set()
        for s in raw:
            if not s or len(s) > 50: 
                continue
            k=s.lower()
            if k not in seen:
                seen.add(k); skills.append(s)
            if len(skills) >= 10: break
    except Exception:
        pass
    return {"title": title, "company": company, "location": location, "salary": salary, "skills": skills}

def run_one(url: str, timeout_ms=15000, retries=1, headless=True):
    t0 = time.time(); success=False; err=""; pred={}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            attempt=0
            while attempt <= retries and not success:
                attempt += 1
                try:
                    page.goto(url, timeout=timeout_ms)
                    page.wait_for_load_state("domcontentloaded")
                    accept_cookies(page)
                    # 👇 On attend UNIQUEMENT le titre
                    page.wait_for_selector(SEL_TITLE, timeout=timeout_ms)
                    time.sleep(0.4)  # petite hydratation
                    pred = extract(page)

                    # --- CACHE TEXTE POUR LLM (écrit ici, où 'page' et 'url' existent) ---
                    try:
                        node = page.locator("[data-testid='job-description'], [role='main'], main, article").first
                        if node.count() == 0:
                            node = page.locator("body")
                        main_text = node.inner_text(timeout=800)
                    except Exception:
                        try:
                            main_text = page.locator("body").inner_text(timeout=500)
                        except Exception:
                            main_text = ""
                    (CACHE_DIR / f"{safe_name(url)}.txt").write_text(main_text, encoding="utf-8")
                    # --- FIN CACHE ---

                    success = True
                except TimeoutError as e:
                    err = f"timeout:{e} (try {attempt}/{retries})"
                    if attempt > retries: raise
                except Exception as e:
                    err = f"{type(e).__name__}: {e} (try {attempt}/{retries})"
                    if attempt > retries: raise
        except Exception:
            # screenshot nominatif
            try:
                page.screenshot(path=str(SS_DIR / f"{safe_name(url)}.png"))
            except Exception:
                pass
        finally:
            browser.close()

    rec = {
        "id": url, "variant": "A_RPA",
        "latency_s": round(time.time()-t0,3),
        "success": success, "error": err, "pred": pred
    }
    OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
    print(f"[RPA] {url} -> {success} ({rec['latency_s']}s) err={err}")
    return rec

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv)>1 else "https://example.org"
    headless = (sys.argv[2].lower() != "false") if len(sys.argv) > 2 else True
    run_one(url, headless=headless)



