import requests
import time

# ------------------------------------------------------------------
# PARAMETRES A ADAPTER
# ------------------------------------------------------------------
mail = "vallat.mathieu@gmail.com"
password = "M@thgyver240781*/"
mealie_url = "http://192.168.1.200:9000"   # sans slash final
parser = "nlp"                             # "nlp" (recommande) ou "brute"
per_page = 50
# ------------------------------------------------------------------

DEBUG_SEEN = set()  # evite de spammer la console avec le meme message d'erreur


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


def get_all_recipe_slugs(token, mealie_url):
    headers = {"Authorization": "Bearer " + token, "accept": "application/json"}
    slugs = []
    page = 1
    while True:
        resp = requests.get(
            f"{mealie_url}/api/recipes",
            headers=headers,
            params={"page": page, "perPage": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        slugs.extend(item["slug"] for item in items)
        total_pages = data.get("total_pages") or data.get("totalPages") or page
        if page >= total_pages:
            break
        page += 1
    return slugs


def get_recipe_slugs_by_tag(token, mealie_url, tag_name):
    """Ne recupere que les recettes portant le tag demande (nom ou slug, insensible a la casse)."""
    headers = {"Authorization": "Bearer " + token, "accept": "application/json"}
    tag_key = tag_name.strip().lower()
    slugs = []
    page = 1
    while True:
        resp = requests.get(
            f"{mealie_url}/api/recipes",
            headers=headers,
            # On tente le filtre cote serveur (gain de perf s'il est supporte)...
            params={"page": page, "perPage": per_page, "tags": tag_name},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        # ... et on revalide cote client au cas ou le serveur ignore le parametre
        for item in items:
            item_tags = item.get("tags") or []
            names = {t.get("name", "").strip().lower() for t in item_tags}
            slugs_of_tags = {t.get("slug", "").strip().lower() for t in item_tags}
            if tag_key in names or tag_key in slugs_of_tags:
                slugs.append(item["slug"])
        total_pages = data.get("total_pages") or data.get("totalPages") or page
        if page >= total_pages:
            break
        page += 1
    return slugs


def _debug_once(key, message):
    if key not in DEBUG_SEEN:
        DEBUG_SEEN.add(key)
        print(f"\n   [debug] {message}")


def get_or_create_id(item_type, name, token, mealie_url, cache):
    """item_type: 'units' ou 'foods'. Cherche par nom, cree si absent, renvoie l'id (ou None)."""
    if not name or not name.strip():
        return None

    key = f"{item_type}:{name.strip().lower()}"
    if key in cache:
        return cache[key]

    headers = {"Authorization": "Bearer " + token, "accept": "application/json"}
    found_id = None

    try:
        search_resp = requests.get(
            f"{mealie_url}/api/{item_type}",
            headers=headers,
            params={"search": name, "perPage": 5},
        )
        if search_resp.ok:
            for item in search_resp.json().get("items", []):
                if item.get("name", "").strip().lower() == name.strip().lower():
                    found_id = item.get("id")
                    break
        else:
            _debug_once(
                key + ":search",
                f"recherche {item_type} '{name}' echouee ({search_resp.status_code}) : {search_resp.text[:200]}",
            )
    except Exception as e:
        _debug_once(key + ":search_exc", f"recherche {item_type} '{name}' exception : {e}")

    if not found_id:
        try:
            create_resp = requests.post(
                f"{mealie_url}/api/{item_type}",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": name.strip()},
            )
            if create_resp.ok:
                found_id = create_resp.json().get("id")
            else:
                _debug_once(
                    key + ":create",
                    f"creation {item_type} '{name}' echouee ({create_resp.status_code}) : {create_resp.text[:200]}",
                )
        except Exception as e:
            _debug_once(key + ":create_exc", f"creation {item_type} '{name}' exception : {e}")

    cache[key] = found_id  # peut valoir None : on evite de retenter pour rien
    return found_id


def resolve_reference(item_type, obj, token, mealie_url, cache):
    """Renvoie soit un dict {'id':..., 'name':...} valide, soit None.
    Ne laisse JAMAIS passer un objet partiel sans id (source du crash cote Mealie)."""
    if not obj:
        return None
    if obj.get("id"):
        return obj

    name = (obj.get("name") or "").strip()
    if not name:
        return None

    obj_id = get_or_create_id(item_type, name, token, mealie_url, cache)
    if obj_id:
        return {"id": obj_id, "name": name}
    return None


def parse_and_update_recipe(slug, token, mealie_url, parser, unit_cache, food_cache):
    headers = {
        "Authorization": "Bearer " + token,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    get_resp = requests.get(f"{mealie_url}/api/recipes/{slug}", headers=headers)
    if not get_resp.ok:
        return False, f"GET echoue ({get_resp.status_code})"

    recipe = get_resp.json()
    ingredients = recipe.get("recipeIngredient") or []
    if not ingredients:
        return True, "aucun ingredient"

    # Texte brut de chaque ligne (avant parsing, Mealie le stocke dans "note" ou "display")
    raw_lines = [
        (ing.get("note") or ing.get("display") or ing.get("originalText") or "").strip()
        for ing in ingredients
    ]

    if not any(raw_lines):
        return True, "rien a parser"

    parse_resp = requests.post(
        f"{mealie_url}/api/parser/ingredients",
        headers=headers,
        json={"parser": parser, "ingredients": raw_lines},
    )
    if not parse_resp.ok:
        return False, f"parsing echoue ({parse_resp.status_code}) : {parse_resp.text}"

    parsed_list = parse_resp.json()

    updated = 0
    for i, parsed in enumerate(parsed_list):
        structured = parsed.get("ingredient") if isinstance(parsed, dict) else None
        if not structured or i >= len(ingredients):
            continue

        unit_obj = resolve_reference("units", structured.get("unit"), token, mealie_url, unit_cache)
        food_obj = resolve_reference("foods", structured.get("food"), token, mealie_url, food_cache)

        # On fusionne avec la ligne d'origine (au lieu de la remplacer) pour conserver
        # les champs internes (referenceId, etc.) que le parseur ne renvoie pas
        orig = ingredients[i]
        orig["quantity"] = structured.get("quantity", orig.get("quantity"))
        orig["unit"] = unit_obj
        orig["food"] = food_obj
        orig["note"] = structured.get("note") or orig.get("note", "")
        ingredients[i] = orig
        updated += 1

    if updated == 0:
        return True, "aucune ligne modifiee"

    recipe["recipeIngredient"] = ingredients
    put_resp = requests.put(f"{mealie_url}/api/recipes/{slug}", headers=headers, json=recipe)
    if not put_resp.ok:
        return False, f"sauvegarde echouee ({put_resp.status_code}) : {put_resp.text[:300]}"

    return True, f"{updated}/{len(ingredients)} ingredients structures"


def main():
    tag_to_process = input(
        "Quel tag/mot-cle voulez-vous analyser (seules les recettes portant ce tag "
        "seront traitees) ? Laissez vide pour analyser TOUTES les recettes : "
    ).strip()

    token = authentication(mail, password, mealie_url)

    if tag_to_process:
        print(f"Recuperation des recettes taguees '{tag_to_process}'...")
        slugs = get_recipe_slugs_by_tag(token, mealie_url, tag_to_process)
    else:
        print("Recuperation de TOUTES les recettes...")
        slugs = get_all_recipe_slugs(token, mealie_url)

    total = len(slugs)
    print(f"{total} recettes trouvees.\n")

    # slugs = slugs[:20]  # decommentez pour tester sur un echantillon d'abord

    ok_count = 0
    fail_count = 0
    unit_cache = {}
    food_cache = {}

    for i, slug in enumerate(slugs, start=1):
        print(f"[{i}/{total}] {slug}...", end=" ")
        try:
            success, message = parse_and_update_recipe(
                slug, token, mealie_url, parser, unit_cache, food_cache
            )
        except Exception as e:
            success, message = False, str(e)

        print(("OK - " if success else "ECHEC - ") + message)
        if success:
            ok_count += 1
        else:
            fail_count += 1

        time.sleep(0.3)  # pause polie pour ne pas saturer le serveur

    print("\n=== Resume ===")
    print(f"Reussies : {ok_count}/{total}")
    print(f"Echouees : {fail_count}/{total}")


if __name__ == "__main__":
    main()