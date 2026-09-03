# Mealie Mass Import & Processing Scripts

> 🚀 Un ensemble de scripts utilitaires en Python pour automatiser l'importation en masse, le traitement et la gestion de vos recettes sur [Mealie](https://mealie.io/).

---

## 📋 Table des matières
- [À propos](#-à-propos)
- [Fonctionnalités](#-fonctionnalités)
- [Prérequis](#-prérequis)
- [Installation & Configuration](#-installation--configuration)
- [Utilisation](#-utilisation)
- [Structure du dépôt](#-structure-du-dépôt)
- [Contribution](#-contribution)
- [Licence](#-licence)

---

## 🎯 À propos

Ce dépôt regroupe des scripts conçus pour faciliter la transition, l'enrichissement ou la migration de gros volumes de recettes vers une instance Mealie auto-hébergée. Que ce soit pour importer des listes d'URLs en lot ou pour effectuer des traitements de masse, ces outils s'appuient sur l'API REST de Mealie pour automatiser les tâches répétitives.

---

## ✨ Fonctionnalités

- **Import en masse par URL** : Permet d'injecter rapidement une liste de liens de recettes directement dans Mealie.
- **Traitement et nettoyage de données** *(selon tes scripts)* : Scripts complémentaires pour manipuler, formater ou nettoyer les données de recettes avant ou après leur intégration.
- **Automatisation via l'API** : Utilisation des tokens d'authentification et des endpoints officiels de Mealie (`/api/recipes/...`).

---

## ⚙️ Prérequis

- Python 3.8+
- Une instance Mealie opérationnelle (v1.x ou supérieure recommandée)
- Un compte utilisateur administrateur (ou disposant des droits nécessaires) sur votre instance Mealie.

---

## 📥 Installation & Configuration

1. **Cloner le dépôt :**
   ```bash
   git clone [https://github.com/Mathgyver/Mealie_mass_import.git](https://github.com/Mathgyver/Mealie_mass_import.git)
   cd Mealie_mass_import

2. Installer les dépendances requises (par exemple requests) :

   ```bash
   pip install requests


3. Configurer les paramètres de connexion :

   Modifiez les variables de configuration au début des scripts (ou via un fichier de configuration / variables d'environnement selon votre implémentation) :

        MEALIE_URL : L'URL d'accès à votre instance (ex: http://192.168.1.50:9000 ou https://mealie.mondomaine.com)

        USERNAME : Votre identifiant / email Mealie

        PASSWORD : Votre mot de passe Mealie

---

## 🚀 Utilisation

Lancez les scripts directement depuis votre terminal selon vos besoins.

Exemple d'exécution pour l'import d'une liste de recettes :

   ```bash
   python3 0_scapper_url
   ```
   ```bash
   python3 1_import.py
   ```
   ```bash
   python3 2_analyse_aliments
   ```
   ```bash
   python3 3_doublons_aliments
   ```

---

## 📁 Structure du dépôt

```Plaintext

.
├── 0_scrapper_url.py         # Script pour scrapper les URLs de recette et generer le fichier recettes.txt
├── 1_import.py               # Script principal d'import en masse
├── 2_analyse_aliments.py     # Script permetant d'analyser les aliment des recettes importées
├── 3_doublons_aliments.py    # Script permetant d'analyser les doublons potentiels, genere un fichier doublons_aliments.txt pour fusionner                                     manuelement apres analyse
├── requirements.txt          # Dépendances Python du projet
└── README.md                 # Documentation du projet
```

---

🤝 Contribution

Les contributions, suggestions et améliorations sont les bienvenues ! N'hésitez pas à ouvrir une Issue ou à proposer une Pull Request.

    Forkez le projet

    Créez votre branche (git checkout -b feature/AmazingFeature)

    Committez vos changements (git commit -m 'Add some AmazingFeature')

    Poussez vers la branche (git push origin feature/AmazingFeature)

    Ouvrez une Pull Request

---

📜 Licence

Distribué sous la licence MIT. Voir le fichier LICENSE pour plus d'informations.
