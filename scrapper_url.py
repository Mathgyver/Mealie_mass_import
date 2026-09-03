import re
import time
import requests
from urllib.parse import urljoin, urlparse

# ------------------------------------------------------------------
OUTPUT_FILE = "recettes.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
# ------------------------------------------------------------------


def fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Erreur lors de l'accès à {url}: {e}")
        return ""


def is_xml_sitemap(content):
    head = content.lstrip()[:300].lower()
    return head.startswith("<?xml") or "<urlset" in head or "<sitemapindex" in head


def extract_xml_locs(content):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", content)


def extract_sitemap_index_urls(content):
    return re.findall(r"<sitemap>\s*<loc>\s*([^<\s]+)\s*</loc>", content)


def is_valid_recipe_url(url, path_hint):
    """Filtre les URLs pour ne garder que les recettes et éliminer les assets, pages de catégories et pagination."""
    # Exclure les fichiers statiques (images, styles, scripts...)
    bad_extensions = ('.css', '.png', '.jpg', '.jpeg', '.ico', '.js', '.pdf', '.svg', '.webp')
    if url.lower().endswith(bad_extensions) or any(ext in url.lower() for ext in ['.css?', '.png?', '.jpg?']):
        return False

    parsed = urlparse(url)
    path = parsed.path.rstrip('/')

    if path_hint:
        # Le lien doit obligatoirement contenir le hint (ex: /recettes/)
        if path_hint.lower() not in url.lower():
            return False
            
        parts = [p for p in path.split('/') if p]
        hint_parts = [p for p in path_hint.strip('/').split('/') if p]
        
        # Si le chemin s'arrête juste au niveau du hint (ex: /recettes)
        if len(parts) <= len(hint_parts):
            return False
            
        # Si la dernière partie est un nombre (ex: /recettes/50 ou /recettes/2) -> c'est de la pagination/catégorie
        last_part = parts[-1]
        if last_part.isdigit():
            return False
            
    return True


def extract_links(content, base_url, path_hint=None):
    hrefs = re.findall(r'href="([^"]+)"', content)
    links = set()
    for href in hrefs:
        if href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        full = urljoin(base_url, href)
        full = full.split("#")[0] # Nettoyage des ancres
        
        if is_valid_recipe_url(full, path_hint):
            links.add(full)
            
    return links


def find_and_generate_pagination_pages(content, base_url):
    hrefs = re.findall(r'href="([^"]+)"', content)
    pagination_links = set()
    pagination_patterns = re.compile(r"(page[/\-=]\d+|[/\-]\d+/?$|p=\d+|pg=\d+)", re.IGNORECASE)
    
    for href in hrefs:
        full = urljoin(base_url, href)
        if urlparse(full).netloc == urlparse(base_url).netloc:
            if pagination_patterns.search(full):
                pagination_links.add(full)
                
    if not pagination_links:
        return set()

    max_page = 1
    template_url = None

    for link in pagination_links:
        match = re.search(r'(page[/\-=]|p=|/|_)(\d+)/?$', link, re.IGNORECASE)
        if match:
            num = int(match.group(2))
            if num > max_page:
                max_page = num
                template_url = link.replace(match.group(0), match.group(1) + "{}")

    all_generated_pages = set()
    if template_url and max_page > 1:
        print(f"  -> Pagination maximale détectée : page {max_page}. Génération des URLs de 1 à {max_page}...")
        for p in range(1, max_page + 1):
            try:
                all_generated_pages.add(template_url.format(p))
            except Exception:
                pass
    else:
        all_generated_pages.update(pagination_links)

    return all_generated_pages


def process_xml_sitemap(sitemap_url, path_hint, visited_sitemaps=None):
    if visited_sitemaps is None:
        visited_sitemaps = set()
        
    if sitemap_url in visited_sitemaps:
        return set()
    
    visited_sitemaps.add(sitemap_url)
    print(f"Analyse du sitemap XML : {sitemap_url}")
    
    content = fetch(sitemap_url)
    if not content:
        return set()
        
    urls = set()
    sub_sitemaps = extract_sitemap_index_urls(content)
    if sub_sitemaps:
        print(f"  -> Index détecté contenant {len(sub_sitemaps)} sous-sitemaps.")
        for sub_url in sub_sitemaps:
            urls.update(process_xml_sitemap(sub_url, path_hint, visited_sitemaps))
            time.sleep(0.3)
    else:
        locs = extract_xml_locs(content)
        print(f"  -> {len(locs)} URLs brutes trouvées dans ce sitemap.")
        for u in locs:
            if is_valid_recipe_url(u, path_hint):
                urls.add(u)
        
    return urls


def main():
    print("--- Récupérateur de recettes filtré ---")
    sitemap_url = input("URL de la page d'index ou du sitemap : ").strip()
    path_hint = input(
        "Fragment de texte identifiant une recette dans l'URL "
        "(ex: /recettes/ - indispensable pour filtrer proprement) : "
    ).strip()

    print(f"\nConnexion initiale à {sitemap_url} ...")
    content = fetch(sitemap_url)
    if not content:
        print("Impossible de récupérer la page.")
        return

    all_urls = set()

    if is_xml_sitemap(content):
        print("Format Sitemap XML détecté.")
        all_urls = process_xml_sitemap(sitemap_url, path_hint)
    else:
        print("Page HTML détectée.")
        initial_links = extract_links(content, sitemap_url, path_hint)
        all_urls.update(initial_links)
        print(f"  -> {len(initial_links)} liens de recettes valides trouvés sur la page principale.")

        all_pages = find_and_generate_pagination_pages(content, sitemap_url)
        
        if all_pages:
            print(f"  -> {len(all_pages)} pages de pagination à parcourir...")
            for i, page_url in enumerate(sorted(all_pages), start=1):
                print(f"    [{i}/{len(all_pages)}] Scraping : {page_url}")
                sub_content = fetch(page_url)
                if sub_content:
                    found = extract_links(sub_content, page_url, path_hint)
                    all_urls.update(found)
                time.sleep(0.3)

    sorted_urls = sorted(all_urls)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for u in sorted_urls:
            f.write(u + "\n")

    print(f"\nTerminé : {len(sorted_urls)} URLs de recettes uniques écrites dans {OUTPUT_FILE}")

    try:
        from google.colab import files
        files.download(OUTPUT_FILE)
    except ImportError:
        pass


if __name__ == "__main__":
    main()