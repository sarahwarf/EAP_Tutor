import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright

_cache: str = ""


def _same_site(base: str, url: str) -> bool:
    base_parsed = urlparse(base)
    url_parsed = urlparse(url)
    site_root = "/".join(base_parsed.path.split("/")[:3])  # /view/sitename
    return (
        url_parsed.netloc == base_parsed.netloc
        and url_parsed.path.startswith(site_root)
    )


async def fetch_course_materials(url: str = "") -> str:
    """Crawl all pages of the Google Site and return combined text."""
    global _cache
    target = url or os.environ.get("GOOGLE_SITE_URL", "")
    print(f"[scraper] target URL: '{target}'")
    if not target:
        print("[scraper] No URL set — check GOOGLE_SITE_URL in .env")
        return ""
    if _cache:
        return _cache

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            visited = set()
            to_visit = [target]
            all_text = []

            while to_visit:
                current = to_visit.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                page = await browser.new_page()
                await page.goto(current, wait_until="networkidle", timeout=30000)

                text = await page.inner_text("body")
                page_title = await page.title()
                all_text.append(f"=== {page_title} ===\n{text}")

                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                for link in links:
                    clean = link.split("?")[0].split("#")[0]
                    if _same_site(target, clean) and clean not in visited:
                        to_visit.append(clean)

                await page.close()

            await browser.close()

        _cache = "\n\n".join(all_text)
        return _cache

    except Exception as e:
        import traceback
        print(f"[scraper] FAILED: {e}")
        traceback.print_exc()
        return ""


def clear_cache():
    global _cache
    _cache = ""
