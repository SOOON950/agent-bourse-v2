# 📈 Mon agent boursier automatique

Cet agent surveille ta liste d'actions **24h/24**, gratuitement, et t'envoie des **alertes par email**.
Il tourne tout seul sur **GitHub Actions** (les serveurs gratuits de GitHub) — ton ordinateur peut rester éteint.

> ⚠️ **Important.** Cet agent fournit de l'**information d'aide à la décision**, **PAS** un conseil
> d'achat ou de vente. Tu restes seul responsable de tes décisions.

---

## 📬 Ce que tu vas recevoir par email

- ☕ **Un digest chaque matin à 8h** (heure de Paris), avant l'ouverture : un tableau de toutes tes
  valeurs (cours, variations jour/semaine/mois, RSI, score de conviction), la « météo » des marchés
  (VIX, taux 10 ans US, EUR/USD, Nasdaq), et les mouvements marquants.
- 🔴 **Des alertes rouges immédiates** dès qu'une valeur fait un mouvement important
  (variation ≥ son seuil, ou volume ≥ 3× la moyenne).
- 🟠 **Un point de surveillance regroupé** 1 à 2 fois par jour (par défaut 13h et 18h) : signaux
  techniques (croisements de moyennes, RSI, MACD, cassures) et actualités nouvelles.

Une **IA (Google Gemini)** explique « pourquoi » ça bouge sur les vrais événements.

---

## ✅ Ce qu'il te faut avant de commencer (≈ 15-20 min)

1. Une **adresse Gmail** (gratuite). C'est elle qui enverra les emails. Tu peux en créer une dédiée.
2. Pouvoir activer la **validation en 2 étapes** sur ce compte Gmail (on le fera ensemble — c'est le point qui bloque le plus de gens, suis bien l'étape 4).
3. C'est tout. Pas besoin de carte bancaire, pas besoin de savoir coder, pas besoin de terminal.

Tu vas faire **7 étapes**. Prends-les dans l'ordre.

---

## ÉTAPE 1 — Créer un compte GitHub et un dépôt public

1. Va sur **https://github.com** et clique **Sign up** (ou **Se connecter** si tu as déjà un compte).
2. Une fois connecté, clique sur le **+** en haut à droite, puis **New repository**.
3. Remplis :
   - **Repository name** : par exemple `agent-boursier` (le nom que tu veux, sans espace).
   - **Public** : ⚠️ **coche bien « Public »**. C'est ce qui donne des minutes d'exécution
     **illimitées et gratuites**. (Le code ne contient aucun secret, voir étape 5.)
   - Laisse le reste par défaut, ne coche pas « Add a README ».
4. Clique **Create repository**.

Tu arrives sur une page presque vide qui dit « …or upload an existing file ». Parfait, on passe à l'étape 2.

---

## ÉTAPE 2 — Mettre les fichiers dans le dépôt

Tu as reçu un dossier (dézippé) qui contient :

```
agent.py
config.py
requirements.txt
state.json
.gitignore
README.md
.github/
   └── workflows/
          └── agent.yml
```

Il y a **deux types de fichiers** à uploader. Le seul point délicat est le fichier dans
`.github/workflows/` — on le traite à part (point B).

### A) Les fichiers « simples » (glisser-déposer)

1. Sur la page de ton dépôt, clique **Add file** → **Upload files**.
2. Fais **glisser-déposer** ces 6 fichiers depuis ton dossier :
   `agent.py`, `config.py`, `requirements.txt`, `state.json`, `.gitignore`, `README.md`.
   - 💡 Si `.gitignore` n'apparaît pas dans ton explorateur de fichiers, ce n'est pas grave :
     il est facultatif. Tu peux l'ignorer.
3. En bas, clique le bouton vert **Commit changes**.

### B) Le fichier `agent.yml` dans son dossier (méthode « éditeur en ligne »)

Le glisser-déposer ne sait pas recréer le dossier `.github/workflows`. On va donc créer ce fichier
directement dans GitHub, et **GitHub créera les dossiers automatiquement** quand tu tapes des `/`.

1. Sur la page de ton dépôt, clique **Add file** → **Create new file**.
2. Dans la case du **nom du fichier** (tout en haut), tape **exactement** ceci :
   ```
   .github/workflows/agent.yml
   ```
   👉 À mesure que tu tapes les `/`, tu verras GitHub fabriquer les dossiers `.github` puis
   `workflows`. C'est exactement ce qu'on veut.
3. Ouvre le fichier `agent.yml` de ton dossier avec un éditeur de texte (Bloc-notes, TextEdit…),
   **sélectionne tout** (Ctrl+A / Cmd+A), **copie** (Ctrl+C / Cmd+C).
4. Reviens sur GitHub et **colle** (Ctrl+V / Cmd+V) tout le contenu dans la grande zone de texte.
5. En bas, clique **Commit changes** puis confirme.

✔️ À la fin, ton dépôt doit afficher les fichiers, **et** un dossier `.github`. Si tu cliques
dedans puis sur `workflows`, tu dois voir `agent.yml`.

---

## ÉTAPE 3 — Récupérer ta clé IA Google Gemini (gratuite)

1. Va sur **https://aistudio.google.com/apikey** (connecte-toi avec un compte Google).
2. Clique **Create API key** (Créer une clé API). Choisis ou crée un projet si on te le demande.
3. Une longue suite de caractères apparaît : c'est ta clé. **Copie-la** et garde-la de côté
   (on la collera à l'étape 5). Elle ressemble à `AIza...`.

> Le modèle utilisé est `gemini-2.5-flash-lite` : c'est celui qui a le **plus de quota gratuit**
> et qui est le plus stable. L'agent l'appelle **seulement** sur un vrai événement ou pour le
> digest, et **plafonne** le nombre d'appels — donc tu restes très largement dans le gratuit.

---

## ÉTAPE 4 — Créer un « mot de passe d'application » Gmail (⚠️ étape qui bloque le plus)

Gmail **refuse** ton mot de passe habituel pour envoyer des emails depuis un programme (erreur 535).
Il faut un **mot de passe d'application** : un code de **16 lettres** dédié. Et pour pouvoir en créer
un, la **validation en 2 étapes** doit être activée **d'abord**.

### 4.1 — Activer la validation en 2 étapes (obligatoire et préalable)

1. Va sur **https://myaccount.google.com/security**.
2. Dans la section **« Comment vous connecter à Google »**, clique **Validation en deux étapes**
   (2-Step Verification) et **active-la** (suis les écrans, en général un numéro de téléphone).
   - ❗ Si cette étape n'est pas faite, le menu « mots de passe d'application » **n'existera pas**.

### 4.2 — Générer le mot de passe d'application

1. Va sur **https://myaccount.google.com/apppasswords**.
   (Si la page dit que l'option est indisponible, c'est que la 2-étapes n'est pas encore active :
   retourne au 4.1.)
2. Dans **« Nom de l'application »**, tape par exemple `agent-boursier`, puis clique **Créer**.
3. Google affiche un code de **16 lettres**, souvent présenté en 4 blocs (ex. `abcd efgh ijkl mnop`).
4. **Copie ce code et retire les espaces** → tu dois obtenir **16 lettres collées**
   (ex. `abcdefghijklmnop`). C'est lui que tu colleras à l'étape 5 (pas ton mot de passe Gmail normal !).

---

## ÉTAPE 5 — Ajouter tes 4 secrets dans GitHub

Les secrets sont des informations privées (clé, mot de passe…) que GitHub garde **chiffrées**.
Elles **ne sont jamais visibles** dans le code. C'est pour ça que ton dépôt peut rester public sans risque.

1. Sur la page de ton dépôt, clique l'onglet **Settings** (⚙️, en haut).
2. Dans le menu de gauche : **Secrets and variables** → **Actions**.
3. Clique le bouton vert **New repository secret**, et crée **un par un** ces **4 secrets**.
   ⚠️ Les **noms doivent être écrits EXACTEMENT** comme ci-dessous (en majuscules, avec les underscores) :

   | Name (à recopier exactement) | Secret (la valeur à coller) |
   |---|---|
   | `GEMINI_API_KEY` | ta clé Gemini de l'étape 3 (`AIza...`) |
   | `GMAIL_ADDRESS` | ton adresse Gmail complète (ex. `prenom.nom@gmail.com`) |
   | `GMAIL_APP_PASSWORD` | le **mot de passe d'application** de l'étape 4 (16 lettres collées, **sans espaces**) |
   | `RECIPIENT_EMAIL` | l'adresse où tu veux **recevoir** les alertes (ça peut être la même que `GMAIL_ADDRESS`) |

   Pour chacun : tape le **Name**, colle la valeur dans **Secret**, puis **Add secret**.

4. Au final tu dois voir **4 secrets** listés. (Tu ne pourras plus relire leur contenu, c'est normal ;
   tu pourras seulement les **mettre à jour**.)

---

## ÉTAPE 6 — Activer les Actions et faire un premier test

1. Sur ton dépôt, clique l'onglet **Actions** (en haut).
2. Si GitHub affiche un message demandant d'activer les workflows, clique le bouton vert pour les
   **activer** (« I understand my workflows, go ahead and enable them »).
3. Dans la colonne de gauche, clique sur **Agent boursier**.
4. À droite, clique le bouton **Run workflow** → puis encore **Run workflow** (lancement manuel).
5. Patiente ~30 secondes, **rafraîchis la page** : une exécution apparaît. Clique dessus, puis sur
   le bloc **run** pour voir le déroulé en direct.
   - 🟡 point jaune = en cours · ✅ coche verte = réussi · ❌ croix rouge = erreur (voir Dépannage).

📩 **Au tout premier lancement**, l'agent **n'envoie pas** d'alertes (il évite de te spammer avec
tout l'historique). Il se contente d'**enregistrer l'état de départ** et de t'envoyer **un seul email
de confirmation** : « ✅ Agent boursier démarré ». **Vérifie ta boîte mail** (et les spams).
Si tu l'as reçu : tout fonctionne ! 🎉

Ensuite, l'agent se relancera **tout seul toutes les ~5 minutes**.

> ⏱️ **Le cron gratuit de GitHub est souvent en retard** (parfois 5-15 min, surtout aux heures
> rondes). C'est **normal** et hors de notre contrôle. Le digest a une fenêtre de sécurité : s'il
> n'a pas pu partir à 8h pile, il partira au prochain passage avant midi.

---

## ÉTAPE 7 — Lire les logs (pour comprendre / dépanner)

Onglet **Actions** → clique une exécution → bloc **run** → déplie **« Lancer l'agent »**.
Tu y verras des lignes comme :

- `7/9 valeur(s) analysée(s).` → l'agent a bien récupéré les données.
- `[GARDE-FOU] ... variation aberrante ... IGNORÉE.` → une donnée Yahoo douteuse a été écartée (sécurité).
- `2 alerte(s) rouge(s) -> 1 email groupé.` → un email d'alerte vient de partir.
- `[YAHOO] ... HTTP 403 ...` → Yahoo a bloqué une requête ; l'agent réessaie automatiquement.
- `[EMAIL] ... 535 ...` → problème de mot de passe Gmail (voir Dépannage).

---

## ⚙️ Personnaliser l'agent — le fichier `config.py`

Tout se règle dans **`config.py`**. Pour le modifier sur GitHub : ouvre le fichier dans ton dépôt,
clique le **crayon ✏️** (Edit), change ce que tu veux, puis **Commit changes**.

Ce que tu peux changer facilement :

- **La liste des valeurs** (`WATCHLIST`) : ajouter / retirer une ligne. Chaque valeur a :
  - `nom` (libellé affiché), `ticker` (le code Yahoo Finance, ex. `ALKAL.PA`, `SIVE.ST`),
  - `secteur` (texte libre), `seuil` (le % de variation qui déclenche une alerte rouge),
  - `mots_cles` (pour chercher les actualités Google).
  - 💡 Pour trouver un ticker : cherche la valeur sur https://finance.yahoo.com et lis le code entre
    parenthèses (ex. « ALKAL.PA »).
- **Les heures du point orange** (`HEURES_ORANGE`, ex. `[13, 18]`).
- **L'heure du digest** (`HEURE_DIGEST`, par défaut `8`).
- **Le multiplicateur de volume** (`SEUIL_VOLUME`, par défaut `3.0`).
- **Le délai anti-spam** entre deux alertes rouges (`COOLDOWN_MINUTES`, par défaut `60`).
- **Activer / couper l'IA** (`IA_ACTIVE = True` ou `False`).

> 🔁 **Changer d'IA plus tard (ex. passer à Claude)** : tout l'appel à l'IA est isolé dans **une seule
> fonction**, `_appel_ia_brut(prompt)`, tout en haut de la section IA de `agent.py`. Il suffit de
> réécrire cette fonction (et d'ajouter la clé correspondante en secret) pour changer de fournisseur,
> sans toucher au reste.

---

## 🛠️ Dépannage

**Je n'ai reçu aucun email (même pas la confirmation de démarrage).**
- Regarde les **spams / courrier indésirable**.
- Onglet **Actions** : l'exécution est-elle ✅ verte ? Si ❌, ouvre les logs.
- Cherche `535` dans les logs → c'est Gmail qui refuse le mot de passe :
  - le secret `GMAIL_APP_PASSWORD` doit être le **mot de passe d'application** (16 lettres),
    **pas** ton mot de passe Gmail habituel, et **sans espaces** ;
  - la **validation en 2 étapes** doit être activée (étape 4.1) ;
  - vérifie aussi que `GMAIL_ADDRESS` est complet et correct.
- Vérifie que les **4 secrets** existent et que leurs **noms sont exacts** (étape 5).

**L'exécution est en ❌ rouge.**
- Ouvre l'exécution → le bloc en rouge → lis le message.
- `ModuleNotFoundError` : le fichier `requirements.txt` est manquant ou mal copié — re-vérifie l'étape 2.
- Erreur dans « Lancer l'agent » : lis la dernière ligne, elle indique souvent la cause (secret manquant, etc.).

**Les données d'une valeur sont « n/d » ou la valeur manque dans le digest.**
- Yahoo a peut-être renvoyé un **403** ou n'a pas de données pour ce ticker à cet instant. L'agent
  **réessaie** et **bascule de serveur** automatiquement ; en général ça revient au passage suivant.
- Vérifie que le **ticker** est correct dans `config.py` (le bon suffixe : `.PA` pour Paris,
  `.ST` pour Stockholm…).

**Le digest n'est pas arrivé à 8h pile / les alertes ont un peu de retard.**
- Normal : le **cron gratuit de GitHub est souvent retardé**. Le digest part au premier passage
  entre 8h et midi. Les alertes rouges partent au passage suivant le mouvement.

**L'IA n'a rien commenté.**
- En cas de saturation (429/503) ou si le **plafond d'appels** d'une exécution est atteint, l'agent
  envoie quand même l'email **sans** commentaire IA (il ne plante jamais pour ça). Ça se régularise ensuite.

**Je veux arrêter l'agent.**
- Onglet **Actions** → **Agent boursier** → bouton **« … »** (ou menu) → **Disable workflow**.
  Pour le réactiver : **Enable workflow**.

---

## 🔒 Sécurité & rappel

- **Aucune clé n'est dans le code** : tout passe par les **4 secrets** GitHub (chiffrés). C'est
  pourquoi le dépôt peut être public sans danger.
- Ne colle **jamais** tes clés ou mots de passe directement dans `config.py` ou `agent.py`.
- **Rappel final** : cet agent donne de l'**information**, **pas un conseil d'investissement**.
  Les marchés comportent un risque de perte. À toi de décider. 📊
