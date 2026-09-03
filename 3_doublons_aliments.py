import re
import unicodedata
import difflib
import requests

# ------------------------------------------------------------------
# PARAMETRES A ADAPTER
# ------------------------------------------------------------------
mail = "mail de connection"
password = "mot de passe"
mealie_url = "URL de mealie"   # sans slash final
per_page = 100
similarity_threshold = 0.85   # 0.0 a 1.0 : plus haut = moins de faux positifs
output_file = "rapport_doublons_aliments.txt"
# ------------------------------------------------------------------


def authentication(mail, password, mealie_url):
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "", "username": mail, "password": password,
        "scope": "", "client_id": "", "client_secret": "",
    }
    auth = requests.post(mealie_url + "/api/auth/token", headers=headers, data=data)
    auth.raise_for_status()
    return auth.json()["access_token"]


def get_all_foods(token, mealie_url):
    headers = {"Authorization": "Bearer " + token, "accept": "application/json"}
    foods = []
    page = 1
    while True:
        resp = requests.get(
            f"{mealie_url}/api/foods",
            headers=headers,
            params={"page": page, "perPage": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        foods.extend({"id": item["id"], "name": item["name"]} for item in items)
        total_pages = data.get("total_pages") or data.get("totalPages") or page
        if page >= total_pages:
            break
        page += 1
    return foods


def normalize(name):
    """minuscule, sans accents, sans ponctuation, espaces normalises."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def singularize(text):
    """retire un 's' final simple (heuristique basique, pas parfaite en francais)."""
    if len(text) > 3 and text.endswith("s") and not text.endswith("ss"):
        return text[:-1]
    return text


def main():
    token = authentication(mail, password, mealie_url)

    print("Recuperation de la liste des aliments...")
    foods = get_all_foods(token, mealie_url)
    print(f"{len(foods)} aliments trouves.\n")

    for f in foods:
        norm = normalize(f["name"])
        f["norm"] = norm
        f["key"] = singularize(norm)

    # --- 1) Doublons quasi certains : meme forme normalisee/singulier ---
    groups = {}
    for f in foods:
        groups.setdefault(f["key"], []).append(f)
    certain_groups = [g for g in groups.values() if len(g) > 1]

    # --- 2) Paires suspectes par similarite textuelle (uniquement inter-groupes) ---
    # on bucket par les 3 premiers caracteres pour limiter le nombre de comparaisons
    buckets = {}
    for f in foods:
        bucket_key = f["norm"][:3] if f["norm"] else ""
        buckets.setdefault(bucket_key, []).append(f)

    seen_keys = set()
    suspect_pairs = []
    for bucket in buckets.values():
        n = len(bucket)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = bucket[i], bucket[j]
                if a["key"] == b["key"]:
                    continue  # deja dans les doublons certains
                pair_key = tuple(sorted([a["id"], b["id"]]))
                if pair_key in seen_keys:
                    continue
                seen_keys.add(pair_key)
                score = difflib.SequenceMatcher(None, a["norm"], b["norm"]).ratio()
                if score >= similarity_threshold:
                    suspect_pairs.append((score, a, b))

    suspect_pairs.sort(key=lambda x: x[0], reverse=True)

    # --- Ecriture du rapport ---
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Aliments totaux : {len(foods)}\n")
        f.write(f"Groupes quasi-certains : {len(certain_groups)}\n")
        f.write(f"Paires suspectes (seuil {similarity_threshold}) : {len(suspect_pairs)}\n\n")

        f.write("=" * 70 + "\n")
        f.write("DOUBLONS QUASI CERTAINS (meme mot, casse/accents/pluriel differents)\n")
        f.write("=" * 70 + "\n\n")
        for group in sorted(certain_groups, key=lambda g: g[0]["key"]):
            names = " | ".join(f'{item["name"]} (id: {item["id"]})' for item in group)
            f.write(names + "\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("PAIRES SUSPECTES (similarite textuelle, a verifier manuellement)\n")
        f.write("=" * 70 + "\n\n")
        for score, a, b in suspect_pairs:
            f.write(f"{score:.2f}  {a['name']} (id: {a['id']})  <->  {b['name']} (id: {b['id']})\n")

    print(f"Rapport ecrit dans {output_file}")
    print(f"  - {len(certain_groups)} groupes quasi certains")
    print(f"  - {len(suspect_pairs)} paires suspectes a verifier")
    print("\nAstuce : ouvrez le fichier et allez fusionner les doublons pertinents")
    print("dans Mealie via Classification > Aliments.")


if __name__ == "__main__":
    main()
