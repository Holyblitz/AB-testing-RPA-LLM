# build_urls_wttj.py
# Usage:
#   python build_urls_wttj.py "https://www.welcometothejungle.com/fr/jobs?query=data%20analyst&sortBy=mostRelevant" 120
#
# Arg1 = URL de recherche WTTJ (tu peux changer la query)
# Arg2 = (optionnel) nombre max d'URLs à collecter (défaut 100)

import sys, time, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

MAX_DEFAULT = 100
OUT_PATH = Path("data/urls.txt")

def is_job_url(href: str) -> bool:
    if not href: return False
    # Heuristique simple : URLs d’offres contiennent généralement /jobs/
    return "/jobs/" in href and not href.endswith(("/companies", "/fr/jobs"))

def normalize_url(base: str, href: str) -> str:
    if not href: return ""
    if href.startswith("http"): return href
    return urljoin(base, href)

def collect_job_urls(page, base_url: str) -> set:
    urls = set()
    # Plusieurs sélecteurs potentiels selon la version du site :
    selectors = [
        "a[href*='/jobs/']",
        "a[data-testid='job-card-link']",
        "article a[href*='/jobs/']",
    ]
    for sel in selectors:
        for a in page.locator(sel).element_handles():
            href = a.get_attribute("href")
            url = normalize_url(base_url, href)
            if is_job_url(url):
                urls.add(url)
    return urls

def scroll_and_collect(page, base_url: str, max_urls: int):
    seen = set()
    last_count = -1
    stable_rounds = 0

    # essaie d’appuyer sur "Voir plus" si présent
    def click_voir_plus():
        for txt in ["Voir plus", "Voir davantage", "See more", "Load more"]:
            loc = page.get_by_text(txt, exact=False)
            if loc.count() > 0:
                try:
                    loc.first.click(timeout=1500)
                    return True
                except:
                    pass
        return False

    for i in range(50):  # limite dure pour éviter les boucles infinies
        # scroll bas
        page.mouse.wheel(0, 4000)
        time.sleep(0.8)

        # tenter un bouton "voir plus"
        clicked = click_voir_plus()
        if clicked:
            time.sleep(0.8)

        # collecter
        batch = collect_job_urls(page, base_url)
        seen |= batch

        # condition d’arrêt
        if len(seen) >= max_urls:
            break
        if len(seen) == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = len(seen)

        if stable_rounds >= 4:
            # plus de nouvelles cartes malgré plusieurs scrolls
            break

    return seen

def main():
    if len(sys.argv) < 2:
        print("Usage: python build_urls_wttj.py '<search_url>' [max_urls]")
        sys.exit(1)
    search_url = sys.argv[1]
    max_urls = int(sys.argv[2]) if len(sys.argv) >= 3 else MAX_DEFAULT

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(search_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        # accepter les cookies si une bannière apparaît
        try:
            for t in ["Tout accepter", "Accepter tout", "Accept all"]:
                btn = page.get_by_role("button", name=t)
                if btn.count() > 0:
                    btn.first.click(timeout=1500)
                    break
        except:
            pass

        urls = scroll_and_collect(page, search_url, max_urls)
        browser.close()

    # Dédup + tri
    urls = sorted(set(urls))
    # Filtre basique : on ne garde que le domaine WTTJ
    urls = [u for u in urls if "welcometothejungle.com" in urlparse(u).netloc]

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")

    print(f"✅ Écrit {len(urls)} URLs dans {OUT_PATH}")

if __name__ == "__main__":
    main()

