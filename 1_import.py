import requests
import time

# ------------------------------------------------------------------
# PARAMETRES A ADAPTER SI BESOIN
# ------------------------------------------------------------------
input_file = "recettes.txt"                      # fichier avec 1 URL par ligne, dans le meme dossier
mail = "votre_mail"
password = "motdepasse"
mealie_url = "url_de_mealie"          # sans slash final

# Filtrage par mot-cle sur l'URL (le nom de la recette y figure generalement).
# Laissez la liste vide [] pour tout importer sans filtre.
keywords = []                                     # ex: ["poulet", "curry"]
match_mode = "any"                                # "any" = au moins un mot-cle present, "all" = tous presents

# Extraction automatique de la categorie Mealie a partir de l'URL, site par site.
# Pour chaque domaine : un regex avec UN groupe capturant le slug de categorie
# dans l'URL, et (optionnel) un dictionnaire slug -> libelle joli a afficher.
# Si le site n'est pas dans cette liste, ou si le regex ne matche pas, aucune
# categorie n'est ajoutee automatiquement (pas d'erreur, juste ignore).
CATEGORY_URL_RULES = {
    "recette.plus": {
        "pattern": r"recette\.plus/recettes/([a-z0-9-]+)/",
        "labels": {
            "aperitifs": "Apéritifs",
            "entres": "Entrées",
            "plat-principal": "Plat principal",
            "desserts": "Desserts",
            "boissons": "Boissons",
            "recettes-petit-dejeuner": "Petit déjeuner",
            "accompagnement": "Accompagnement",
        },
    },
    # Pour ajouter un autre site, dupliquez un bloc ci-dessus avec son propre
    # regex et sa propre table de libelles.
}


def extract_category_from_url(url):
    """Renvoie le nom de categorie devine a partir de l'URL, ou None si aucune
    regle ne correspond."""
    import re

    for domain, rule in CATEGORY_URL_RULES.items():
        if domain not in url:
            continue
        match = re.search(rule["pattern"], url)
        if not match:
            continue
        category_slug = match.group(1)
        labels = rule.get("labels", {})
        if category_slug in labels:
            return labels[category_slug]
        # Slug inconnu dans la table : on le rend juste plus lisible
        return category_slug.replace("-", " ").capitalize()

    return None
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


def get_or_create_tag(tag_name, token, mealie_url):
    """Recupere l'id du tag s'il existe deja globalement (par slug), sinon le cree.
    Renvoie un dict {"id": ..., "name": ..., "slug": ...} utilisable dans recipe['tags'].
    C'est indispensable : un tag envoye sans id est traite par l'API comme une
    creation, ce qui echoue des la 2e recette puisque le tag (meme slug) existe deja."""
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    tag_slug = slugify(tag_name)

    # 1) Chercher parmi tous les tags existants
    list_resp = requests.get(f"{mealie_url}/api/organizers/tags", headers=headers,
                              params={"perPage": -1})
    if list_resp.ok:
        payload = list_resp.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        for t in items:
            if t.get("slug") == tag_slug:
                return {"id": t["id"], "name": t["name"], "slug": t["slug"]}

    # 2) Sinon, le creer
    create_resp = requests.post(f"{mealie_url}/api/organizers/tags", headers=headers,
                                 json={"name": tag_name})
    if create_resp.ok:
        t = create_resp.json()
        return {"id": t["id"], "name": t["name"], "slug": t["slug"]}

    # En dernier recours (ex: creation concurrente / conflit 400), on retente une recherche
    list_resp = requests.get(f"{mealie_url}/api/organizers/tags", headers=headers,
                              params={"perPage": -1})
    if list_resp.ok:
        payload = list_resp.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        for t in items:
            if t.get("slug") == tag_slug:
                return {"id": t["id"], "name": t["name"], "slug": t["slug"]}

    create_resp.raise_for_status()


def add_tag_to_recipe(slug, tag_name, token, mealie_url):
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # 0) Resoudre le tag vers son id reel (cree seulement s'il n'existe pas encore)
    tag_obj = get_or_create_tag(tag_name, token, mealie_url)

    # 1) On récupère la recette complète (plus fiable qu'un PATCH partiel,
    #    qui plante avec "Recipe already exists" sur les recettes préexistantes)
    get_resp = requests.get(f"{mealie_url}/api/recipes/{slug}", headers=headers)
    if not get_resp.ok:
        return get_resp

    recipe = get_resp.json()
    existing_tags = recipe.get("tags") or []

    # Ne rajoute pas le tag s'il est déjà présent sur CETTE recette
    if not any(t.get("slug") == tag_obj["slug"] for t in existing_tags):
        existing_tags.append(tag_obj)
        recipe["tags"] = existing_tags
        recipe = sanitize_ingredients_for_put(recipe)
        # 2) On renvoie la recette complète en PUT
        return requests.put(f"{mealie_url}/api/recipes/{slug}", headers=headers, json=recipe)

    # Tag déjà présent sur la recette : rien à faire, on simule un succès
    get_resp.status_code = 200
    return get_resp


def get_or_create_category(category_name, token, mealie_url):
    """Equivalent de get_or_create_tag, mais pour les categories Mealie
    (endpoint /api/organizers/categories)."""
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    category_slug = slugify(category_name)

    list_resp = requests.get(f"{mealie_url}/api/organizers/categories", headers=headers,
                              params={"perPage": -1})
    if list_resp.ok:
        payload = list_resp.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        for c in items:
            if c.get("slug") == category_slug:
                return {"id": c["id"], "name": c["name"], "slug": c["slug"]}

    create_resp = requests.post(f"{mealie_url}/api/organizers/categories", headers=headers,
                                 json={"name": category_name})
    if create_resp.ok:
        c = create_resp.json()
        return {"id": c["id"], "name": c["name"], "slug": c["slug"]}

    list_resp = requests.get(f"{mealie_url}/api/organizers/categories", headers=headers,
                              params={"perPage": -1})
    if list_resp.ok:
        payload = list_resp.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        for c in items:
            if c.get("slug") == category_slug:
                return {"id": c["id"], "name": c["name"], "slug": c["slug"]}

    create_resp.raise_for_status()


def add_category_to_recipe(slug, category_name, token, mealie_url):
    """Ajoute une categorie a une recette (champ recipeCategory), en reutilisant
    la categorie existante si elle est deja creee dans Mealie."""
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    category_obj = get_or_create_category(category_name, token, mealie_url)

    get_resp = requests.get(f"{mealie_url}/api/recipes/{slug}", headers=headers)
    if not get_resp.ok:
        return get_resp

    recipe = get_resp.json()
    existing_categories = recipe.get("recipeCategory") or []

    if not any(c.get("slug") == category_obj["slug"] for c in existing_categories):
        existing_categories.append(category_obj)
        recipe["recipeCategory"] = existing_categories
        recipe = sanitize_ingredients_for_put(recipe)
        return requests.put(f"{mealie_url}/api/recipes/{slug}", headers=headers, json=recipe)

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

        category_name = extract_category_from_url(url)
        if category_name:
            category_response = add_category_to_recipe(slug, category_name, token, mealie_url)
            if category_response.ok:
                print(f"  -> Categorie '{category_name}' ajoutee")
            else:
                print(f"  -> ECHEC ajout de la categorie ({category_response.status_code}) : "
                      f"{category_response.text}")

        time.sleep(0.5)  # petite pause pour ne pas surcharger le serveur / le scraper

    print("\n=== Resume ===")
    print(f"Reussies : {ok_count}/{total}")
    print(f"Echouees : {fail_count}/{total}")


def choose_input_file(default_file):
    """Demande a l'utilisateur quel fichier .txt utiliser.
    Propose la liste des .txt trouves dans le dossier courant (numerotes),
    avec le fichier par defaut pre-selectionne si on appuie juste sur Entree.
    On peut aussi taper un nom/chemin de fichier directement."""
    import os

    txt_files = sorted(f for f in os.listdir(".") if f.lower().endswith(".txt"))

    if not txt_files:
        chosen = input(
            f"Aucun fichier .txt trouve dans ce dossier. "
            f"Chemin du fichier a utiliser (Entree = {default_file}) : "
        ).strip()
        return chosen or default_file

    print("Fichiers .txt disponibles :")
    for i, f in enumerate(txt_files, start=1):
        marker = "  <- par defaut" if f == default_file else ""
        print(f"  {i}. {f}{marker}")

    choice = input(
        f"Numero du fichier a importer (Entree = {default_file}) : "
    ).strip()

    if not choice:
        return default_file

    if choice.isdigit() and 1 <= int(choice) <= len(txt_files):
        return txt_files[int(choice) - 1]

    # L'utilisateur a peut-etre tape un nom de fichier directement
    return choice


if __name__ == "__main__":
    chosen_file = choose_input_file(input_file)

    cookbook_tag = input(
        "Quel mot-cle (tag) voulez-vous attribuer a toutes les recettes importees ? "
        "(laisser vide pour aucun tag) : "
    ).strip()

    token = authentication(mail, password, mealie_url)
    import_from_file(chosen_file, token, mealie_url, cookbook_tag, keywords, match_mode)
