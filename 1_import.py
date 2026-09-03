import requests
import time

# ------------------------------------------------------------------
# PARAMETRES A ADAPTER SI BESOIN
# ------------------------------------------------------------------
input_file = "recettes.txt"                      # fichier avec 1 URL par ligne, dans le meme dossier
mail = "mail de connection"
password = "mot de passe"
mealie_url = "URL de mealie"   # sans slash final

# Filtrage par mot-cle sur l'URL (le nom de la recette y figure generalement).
# Laissez la liste vide [] pour tout importer sans filtre.
keywords = []                                     # ex: ["poulet", "curry"]
match_mode = "any"                                # "any" = au moins un mot-cle present, "all" = tous presents
# ------------------------------------------------------------------


def authentication(mail, password, mealie_url):
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "",
        "username": mail,
        "password": password,
        "scope": "",
        "client_id": "",
        "client_secret": "",
    }
    auth = requests.post(mealie_url + "/api/auth/token", headers=headers, data=data)
    auth.raise_for_status()
    return auth.json()["access_token"]


def slugify(name):
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def sanitize_ingredients_for_put(recipe):
    """Retire les references food/unit incompletes (sans id) qui font planter
    l'API Mealie lors d'un PUT complet de la recette (bug connu cote serveur)."""
    ingredients = recipe.get("recipeIngredient") or []
    for ing in ingredients:
        unit_obj = ing.get("unit")
        if unit_obj and not unit_obj.get("id"):
            ing["unit"] = None
        food_obj = ing.get("food")
        if food_obj and not food_obj.get("id"):
            ing["food"] = None
    recipe["recipeIngredient"] = ingredients
    return recipe


def add_tag_to_recipe(slug, tag_name, token, mealie_url):
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # 1) On récupère la recette complète (plus fiable qu'un PATCH partiel,
    #    qui plante avec "Recipe already exists" sur les recettes préexistantes)
    get_resp = requests.get(f"{mealie_url}/api/recipes/{slug}", headers=headers)
    if not get_resp.ok:
        return get_resp

    recipe = get_resp.json()
    tag_slug = slugify(tag_name)
    existing_tags = recipe.get("tags") or []

    # Ne rajoute pas le tag s'il est déjà présent
    if not any(t.get("slug") == tag_slug for t in existing_tags):
        existing_tags.append({"name": tag_name, "slug": tag_slug})
        recipe["tags"] = existing_tags
        recipe = sanitize_ingredients_for_put(recipe)
        # 2) On renvoie la recette complète en PUT
        return requests.put(f"{mealie_url}/api/recipes/{slug}", headers=headers, json=recipe)

    # Tag déjà présent : rien à faire, on simule un succès
    get_resp.status_code = 200
    return get_resp


def url_matches_keywords(url, keywords, match_mode="any"):
    """Verifie si le nom de recette contenu dans l'URL correspond aux mots-cles."""
    if not keywords:
        return True

    import unicodedata

    text = url.lower().replace("-", " ").replace("_", " ").replace("/", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    checks = [unicodedata.normalize("NFKD", kw.lower()).encode("ascii", "ignore").decode("ascii") in text
              for kw in keywords]

    return any(checks) if match_mode == "any" else all(checks)


def import_from_file(input_file, token, mealie_url, cookbook_tag, keywords=None, match_mode="any"):
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    with open(input_file, encoding="utf-8") as fp:
        all_urls = [line.strip() for line in fp if line.strip()]

    urls = [u for u in all_urls if url_matches_keywords(u, keywords, match_mode)]

    if keywords:
        print(f"Filtrage par mot-cle {keywords} ({match_mode}) : "
              f"{len(urls)}/{len(all_urls)} URLs retenues.\n")

    total = len(urls)
    ok_count = 0
    fail_count = 0

    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{total}] Import : {url}")
        data = {"url": url, "includeTags": False}
        response = requests.post(mealie_url + "/api/recipes/create/url", headers=headers, json=data)

        if not response.ok:
            print(f"  -> ECHEC import ({response.status_code}) : {response.text}")
            fail_count += 1
            continue

        try:
            slug = response.json()
        except ValueError:
            slug = response.text.strip('"')

        print(f"  -> Recette creee : {slug}")
        ok_count += 1

        if cookbook_tag:
            tag_response = add_tag_to_recipe(slug, cookbook_tag, token, mealie_url)
            if tag_response.ok:
                print(f"  -> Tag '{cookbook_tag}' ajoute")
            else:
                print(f"  -> ECHEC ajout du tag ({tag_response.status_code}) : {tag_response.text}")

        time.sleep(0.5)  # petite pause pour ne pas surcharger le serveur / le scraper

    print("\n=== Resume ===")
    print(f"Reussies : {ok_count}/{total}")
    print(f"Echouees : {fail_count}/{total}")


if __name__ == "__main__":
    cookbook_tag = input(
        "Quel mot-cle (tag) voulez-vous attribuer a toutes les recettes importees ? "
        "(laisser vide pour aucun tag) : "
    ).strip()

    token = authentication(mail, password, mealie_url)
    import_from_file(input_file, token, mealie_url, cookbook_tag, keywords, match_mode)
