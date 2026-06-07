# -*- coding: utf-8 -*-
"""
config.py — TOUS les réglages de l'agent boursier.

C'est le SEUL fichier que tu as besoin de modifier pour personnaliser l'agent :
- ajouter / retirer une valeur surveillée
- changer un seuil d'alerte
- changer les horaires d'envoi
- activer / désactiver l'IA

Aucune connaissance en code n'est nécessaire : tu remplaces juste les valeurs.
"""

# =========================================================================
# 1) WATCHLIST — les valeurs surveillées
# =========================================================================
# Pour AJOUTER une valeur  : copie-colle une ligne et adapte-la.
# Pour RETIRER une valeur   : supprime la ligne (ou mets un # devant).
#
#   "nom"       : le nom affiché dans les emails
#   "ticker"    : le code Yahoo Finance (vérifiable sur finance.yahoo.com)
#   "secteur"   : courte description (sert au contexte de l'IA)
#   "seuil"     : variation du jour en % qui déclenche une alerte ROUGE
#   "mots_cles" : la recherche utilisée pour les actualités Google Actualités
#
WATCHLIST = [
    {"nom": "Kalray",                "ticker": "ALKAL.PA", "secteur": "Processeurs DPU / infrastructure IA", "seuil": 8, "mots_cles": "Kalray action"},
    {"nom": "2CRSI",                 "ticker": "AL2SI.PA", "secteur": "Serveurs HPC / infrastructure IA",    "seuil": 8, "mots_cles": "2CRSI action"},
    {"nom": "Riber",                 "ticker": "ALRIB.PA", "secteur": "Équipements d'épitaxie / semi",        "seuil": 6, "mots_cles": "Riber action épitaxie"},
    {"nom": "Haffner Energy",        "ticker": "ALHAF.PA", "secteur": "Hydrogène / décarbonation",            "seuil": 6, "mots_cles": "Haffner Energy hydrogène"},
    {"nom": "Median Technologies",   "ticker": "ALMDT.PA", "secteur": "MedTech / imagerie IA",                "seuil": 6, "mots_cles": "Median Technologies action"},
    {"nom": "Vusion Group",          "ticker": "VU.PA",    "secteur": "Étiquettes électroniques / retail",    "seuil": 5, "mots_cles": "Vusion Group SES-imagotag"},
    {"nom": "STIF",                  "ticker": "ALSTI.PA", "secteur": "Sécurité industrielle anti-explosion", "seuil": 6, "mots_cles": "STIF Securistuff action"},
    {"nom": "Sivers Semiconductors", "ticker": "SIVE.ST",  "secteur": "Semi RF / photonique 5G",              "seuil": 6, "mots_cles": "Sivers Semiconductors"},
    {"nom": "LQQ (Nasdaq-100 x2)",   "ticker": "LQQ.PA",   "secteur": "ETF à effet de levier x2",             "seuil": 3, "mots_cles": "Nasdaq 100 LQQ ETF"},
]

# =========================================================================
# 2) CONTEXTE MACRO — indices de marché suivis (la "météo" des marchés)
# =========================================================================
MACRO = [
    {"nom": "Taux 10 ans US", "ticker": "^TNX"},
    {"nom": "EUR/USD",        "ticker": "EURUSD=X"},
    {"nom": "Nasdaq-100",     "ticker": "^NDX"},
    {"nom": "VIX (peur)",     "ticker": "^VIX"},
]

# =========================================================================
# 3) SEUILS & ANTI-SPAM
# =========================================================================
SEUIL_VOLUME        = 3.0    # volume du jour >= 3x la moyenne 1 mois -> alerte rouge
COOLDOWN_MINUTES    = 60     # délai minimum entre 2 alertes rouges pour une MÊME valeur
COOLDOWN_BYPASS_PCT = 4.0    # ... sauf si la variation a bougé de +/- 4% depuis la dernière alerte
GARDE_FOU_VARIATION = 50.0   # au-delà de +/- 50%, la donnée est jugée fausse (bug) et IGNORÉE

# =========================================================================
# 4) HORAIRES (toujours en heure de Paris)
# =========================================================================
HEURE_DIGEST        = 8      # digest du MATIN, avant l'ouverture (Euronext ouvre à 9h)
HEURE_LIMITE_DIGEST = 12     # filet de sécurité : si le cron est en retard, le digest part avant cette heure
HEURES_ORANGE       = [13, 18]   # créneaux d'envoi des points "orange" regroupés
FENETRE_ORANGE_H    = 4      # tolérance (heures) pour rattraper un créneau orange manqué (retard du cron)

# =========================================================================
# 5) INTELLIGENCE ARTIFICIELLE (Google Gemini, gratuit)
# =========================================================================
IA_ACTIVE      = True                    # mettre False pour couper totalement l'IA
AI_MODEL       = "gemini-2.5-flash-lite" # modèle stable avec un quota gratuit confortable
MAX_APPELS_IA  = 4                       # plafond d'appels IA PAR EXÉCUTION (protège le quota)

# =========================================================================
# 6) DIVERS
# =========================================================================
TIMEZONE                = "Europe/Paris"
HISTORIQUE              = "1y"   # profondeur d'historique récupérée chez Yahoo (1 an)
ENVOYER_EMAIL_DEMARRAGE = True   # email de confirmation lors du tout premier lancement
SEUIL_SILENCE_VOLATILITE = 0.012 # volatilité quotidienne sous ce seuil = "calme inhabituel" (1,2 %)
