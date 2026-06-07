# -*- coding: utf-8 -*-
"""
agent.py — Agent boursier automatique (surveillance + alertes email).

Fonctionnement (résumé) :
  - Tourne toutes les 5 minutes via GitHub Actions.
  - Récupère les cours (Yahoo Finance) + le contexte macro.
  - Calcule des indicateurs techniques EN PYTHON PUR (sans pandas/numpy).
  - Calcule un "score de conviction" transparent (-10 à +10).
  - Récupère les actualités (Google Actualités RSS).
  - Envoie des alertes email en 3 niveaux : ROUGE (immédiat), ORANGE (regroupé), DIGEST (matin 8h).
  - Mémorise son état dans state.json pour ne pas se répéter (anti-spam).

⚠️ Cet agent fournit de l'INFORMATION D'AIDE À LA DÉCISION, jamais de conseil d'achat/vente.
"""

import os
import json
import time
import smtplib
import re
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import feedparser

try:
    from zoneinfo import ZoneInfo
except Exception:                      # filet de sécurité très improbable
    ZoneInfo = None

import config as cfg

# -------------------------------------------------------------------------
# SECRETS (jamais en clair dans le code : lus depuis les variables d'env.)
# -------------------------------------------------------------------------
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL    = os.environ.get("RECIPIENT_EMAIL", "")

STATE_FILE = "state.json"

# User-Agent d'un vrai navigateur (sinon Yahoo renvoie souvent un 403 aux serveurs)
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def log(msg):
    """Affiche un message horodaté dans les logs GitHub Actions."""
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def maintenant_paris():
    """Renvoie l'heure actuelle en fuseau de Paris (gère l'heure d'été)."""
    if ZoneInfo:
        return datetime.now(ZoneInfo(cfg.TIMEZONE))
    # repli grossier (UTC+1) si zoneinfo indisponible
    return datetime.now(timezone.utc) + timedelta(hours=1)


# =========================================================================
#  ÉTAT PERSISTANT (state.json)
# =========================================================================
def etat_par_defaut():
    return {
        "initialized": False,        # False = tout premier lancement
        "last_digest_date": None,    # date du dernier digest envoyé (anti-doublon)
        "orange_slots_sent": {},     # { "2025-06-07": ["13", "18"] }
        "seen_news": {},             # { ticker: [liens déjà vus] }
        "red_cooldowns": {},         # { ticker: {"ts": ..., "variation": ...} }
        "tech_state": {},            # { ticker: état technique précédent } -> détection des transitions
        "orange_queue": [],          # file d'attente des signaux orange en attente d'envoi
    }


def charger_etat():
    """Charge state.json en fusionnant avec les valeurs par défaut (robuste)."""
    base = etat_par_defaut()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            base.update({k: data.get(k, v) for k, v in base.items()})
    except FileNotFoundError:
        log("state.json absent : initialisation d'un état vierge.")
    except Exception as ex:
        log(f"state.json illisible ({ex}) : réinitialisation.")
    return base


def sauver_etat(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


# =========================================================================
#  RÉCUPÉRATION DES DONNÉES YAHOO FINANCE
# =========================================================================
def creer_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    return s


def rechauffer_session(s):
    """Visite Yahoo pour récupérer les cookies (réduit les blocages 403)."""
    for url in ("https://fc.yahoo.com", "https://finance.yahoo.com"):
        try:
            s.get(url, timeout=10)
        except Exception:
            pass


def parser_chart(data):
    """Transforme la réponse JSON Yahoo en un dictionnaire propre."""
    res = data["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp", []) or []
    quote = (res.get("indicators", {}).get("quote", [{}]) or [{}])[0]
    return {
        "ts":            ts,
        "closes":        quote.get("close", []) or [],
        "highs":         quote.get("high", []) or [],
        "lows":          quote.get("low", []) or [],
        "volumes":       quote.get("volume", []) or [],
        "market_price":  meta.get("regularMarketPrice"),
        "market_time":   meta.get("regularMarketTime"),
        "market_volume": meta.get("regularMarketVolume"),
        "gmtoffset":     meta.get("gmtoffset", 0) or 0,
        "currency":      meta.get("currency", ""),
    }


def yahoo_chart(ticker, s):
    """
    Récupère l'historique 1 an d'une valeur, avec :
      - réessais en cas de 401/403/429 (rafraîchissement de session),
      - bascule entre query1 et query2 (deux hôtes Yahoo),
      - aucune exception qui fait planter le programme.
    """
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    path = f"/v8/finance/chart/{ticker}?interval=1d&range={cfg.HISTORIQUE}"
    for tentative in range(4):
        host = hosts[tentative % 2]
        url = f"https://{host}{path}"
        try:
            r = s.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data.get("chart", {}).get("result"):
                    return parser_chart(data)
                log(f"[YAHOO] {ticker} : réponse sans données.")
                return None
            if r.status_code in (401, 403, 429):
                log(f"[YAHOO] {ticker} HTTP {r.status_code} (essai {tentative + 1}/4) — on rafraîchit la session.")
                rechauffer_session(s)
                time.sleep(1.5 * (tentative + 1))
                continue
            log(f"[YAHOO] {ticker} HTTP {r.status_code} : on ignore cette valeur.")
            return None
        except Exception as ex:
            log(f"[YAHOO] {ticker} exception : {ex}")
            time.sleep(1.5)
    log(f"[YAHOO] {ticker} : échec après 4 tentatives, on continue.")
    return None


# =========================================================================
#  INDICATEURS TECHNIQUES (Python pur, sans pandas/numpy)
# =========================================================================
def _propre(valeurs):
    """Retire les None d'une liste."""
    return [v for v in valeurs if v is not None]


def rsi(closes, periode=14):
    """RSI selon la méthode de Wilder (lissage exponentiel)."""
    if len(closes) < periode + 1:
        return None
    gains, pertes = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        pertes.append(max(-delta, 0.0))
    avg_gain = sum(gains[:periode]) / periode
    avg_perte = sum(pertes[:periode]) / periode
    for i in range(periode, len(gains)):
        avg_gain = (avg_gain * (periode - 1) + gains[i]) / periode
        avg_perte = (avg_perte * (periode - 1) + pertes[i]) / periode
    if avg_perte == 0:
        return 100.0
    rs = avg_gain / avg_perte
    return 100.0 - (100.0 / (1.0 + rs))


def ema_serie(valeurs, periode):
    """Série complète d'EMA (amorcée par une moyenne simple)."""
    if len(valeurs) < periode:
        return []
    k = 2.0 / (periode + 1)
    val = sum(valeurs[:periode]) / periode
    out = [val]
    for v in valeurs[periode:]:
        val = v * k + val * (1 - k)
        out.append(val)
    return out


def macd(closes, rapide=12, lent=26, signal=9):
    """MACD = EMA12 - EMA26 ; signal = EMA9 du MACD ; histogramme = MACD - signal."""
    if len(closes) < lent + signal:
        return None
    ema_rapide = ema_serie(closes, rapide)
    ema_lent = ema_serie(closes, lent)
    n = min(len(ema_rapide), len(ema_lent))   # alignement par la fin (dates récentes)
    ligne_macd = [f - l for f, l in zip(ema_rapide[-n:], ema_lent[-n:])]
    ligne_signal = ema_serie(ligne_macd, signal)
    if not ligne_signal:
        return None
    m = ligne_macd[-1]
    sig = ligne_signal[-1]
    return {"macd": m, "signal": sig, "hist": m - sig}


def sma(closes, periode):
    """Moyenne mobile simple."""
    if len(closes) < periode:
        return None
    return sum(closes[-periode:]) / periode


def volatilite(closes, fenetre=20):
    """Écart-type des rendements quotidiens sur 'fenetre' séances."""
    if len(closes) < fenetre + 1:
        return None
    rendements = [(closes[i] - closes[i - 1]) / closes[i - 1]
                  for i in range(1, len(closes)) if closes[i - 1]]
    rendements = rendements[-fenetre:]
    if len(rendements) < 2:
        return None
    moy = sum(rendements) / len(rendements)
    var = sum((r - moy) ** 2 for r in rendements) / len(rendements)
    return var ** 0.5


def variation_n(closes, n):
    """Variation en % par rapport à n séances en arrière."""
    if len(closes) <= n:
        return None
    ancien = closes[-1 - n]
    recent = closes[-1]
    if not ancien:
        return None
    return (recent - ancien) / ancien * 100.0


def variation_du_jour(ts, closes, gmtoffset, market_price):
    """
    Calcule la variation du jour de façon ROBUSTE.

    Important (bug critique d'une version précédente) :
    on NE se sert PAS de 'chartPreviousClose' du méta Yahoo, qui peut être très
    ancien pour les small caps illiquides (d'où des +2000% absurdes).
    On reconstruit la variation à partir de la série historique.
    """
    paires = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if len(paires) < 2:
        return None
    def date_locale(epoch):
        return (datetime.fromtimestamp(epoch, timezone.utc) + timedelta(seconds=gmtoffset)).date()

    aujourd_hui = (datetime.now(timezone.utc) + timedelta(seconds=gmtoffset)).date()
    date_derniere_barre = date_locale(paires[-1][0])
    dernier_close = paires[-1][1]

    if date_derniere_barre >= aujourd_hui:
        # La dernière barre est celle d'aujourd'hui (marché ouvert ou clôturé du jour).
        prix = market_price if market_price is not None else dernier_close
        precedent = paires[-2][1]
    else:
        # Pas de barre datée d'aujourd'hui (pré-ouverture, week-end, jour férié).
        if (market_price is not None and dernier_close
                and abs(market_price - dernier_close) / dernier_close > 0.0005):
            # Cotation en cours aujourd'hui mais barre du jour pas encore créée.
            prix, precedent = market_price, dernier_close
        else:
            # Marché fermé : on reporte la variation de la dernière séance complète.
            prix, precedent = dernier_close, paires[-2][1]

    if not precedent:
        return None
    return (prix - precedent) / precedent * 100.0


# =========================================================================
#  SCORE DE CONVICTION (transparent et expliqué)
# =========================================================================
def conviction(prix, s20, s50, s200, macd_data, rsi_val, var_semaine):
    """
    Score heuristique de -10 à +10. Chaque composante est expliquée.
    On utilise la LIGNE MACD vs 0 (et non l'histogramme, qui frôle 0 en tendance régulière).
    """
    score = 0
    raisons = []

    if s200:
        if prix > s200:
            score += 2; raisons.append("cours au-dessus de la MM200 (tendance de fond haussière) : +2")
        else:
            score -= 2; raisons.append("cours sous la MM200 (tendance de fond baissière) : −2")
    if s50:
        if prix > s50:
            score += 1; raisons.append("cours au-dessus de la MM50 : +1")
        else:
            score -= 1; raisons.append("cours sous la MM50 : −1")
    if s50 and s200:
        if s50 > s200:
            score += 2; raisons.append("MM50 > MM200 (configuration haussière) : +2")
        else:
            score -= 2; raisons.append("MM50 < MM200 (configuration baissière) : −2")
    if s20 and s50:
        if s20 > s50:
            score += 1; raisons.append("MM20 > MM50 (court terme haussier) : +1")
        else:
            score -= 1; raisons.append("MM20 < MM50 (court terme baissier) : −1")
    if macd_data:
        if macd_data["macd"] > 0:
            score += 2; raisons.append("MACD au-dessus de 0 (momentum positif) : +2")
        else:
            score -= 2; raisons.append("MACD sous 0 (momentum négatif) : −2")
    if rsi_val is not None:
        if rsi_val > 70:
            score -= 1; raisons.append(f"RSI {rsi_val:.0f} (surachat, essoufflement possible) : −1")
        elif rsi_val < 30:
            score += 1; raisons.append(f"RSI {rsi_val:.0f} (survente, rebond possible) : +1")
        elif rsi_val > 55:
            score += 1; raisons.append(f"RSI {rsi_val:.0f} (dynamique positive) : +1")
        elif rsi_val < 45:
            score -= 1; raisons.append(f"RSI {rsi_val:.0f} (dynamique négative) : −1")
    if var_semaine is not None:
        if var_semaine > 3:
            score += 1; raisons.append(f"momentum hebdo {var_semaine:+.1f}% : +1")
        elif var_semaine < -3:
            score -= 1; raisons.append(f"momentum hebdo {var_semaine:+.1f}% : −1")

    score = max(-10, min(10, score))
    return score, raisons


def libelle_conviction(score):
    if score >= 6:  return "fortement haussier"
    if score >= 2:  return "haussier"
    if score > -2:  return "neutre"
    if score > -6:  return "baissier"
    return "fortement baissier"


# =========================================================================
#  ANALYSE COMPLÈTE D'UNE VALEUR
# =========================================================================
def analyser(item, parsed):
    """Calcule tous les indicateurs et le score pour une valeur. Renvoie un dict ou None."""
    closes = _propre(parsed["closes"])
    if len(closes) < 30:
        log(f"[ANALYSE] {item['ticker']} : historique insuffisant ({len(closes)} points).")
        return None
    highs = _propre(parsed["highs"]) or closes
    lows = _propre(parsed["lows"]) or closes
    volumes = _propre(parsed["volumes"])

    prix = parsed["market_price"] if parsed["market_price"] is not None else closes[-1]

    var_jour = variation_du_jour(parsed["ts"], parsed["closes"],
                                 parsed["gmtoffset"], parsed["market_price"])
    var_suspecte = False
    if var_jour is not None and abs(var_jour) > cfg.GARDE_FOU_VARIATION:
        # Garde-fou : Euronext a des coupe-circuits à ~±20%, donc >50% = bug de données.
        log(f"[GARDE-FOU] {item['ticker']} variation aberrante {var_jour:.0f}% IGNORÉE.")
        var_jour, var_suspecte = None, True

    var_semaine = variation_n(closes, 5)
    var_mois = variation_n(closes, 21)

    rsi_val = rsi(closes, 14)
    macd_data = macd(closes)
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)

    # Support / résistance affichés (fenêtre incluant la séance en cours)
    support = min(lows[-20:]) if len(lows) >= 5 else None
    resistance = max(highs[-20:]) if len(highs) >= 5 else None
    # Bornes pour DÉTECTER une cassure (on exclut la barre en cours)
    plus_haut_anterieur = max(highs[-21:-1]) if len(highs) >= 21 else None
    plus_bas_anterieur = min(lows[-21:-1]) if len(lows) >= 21 else None

    vol = volatilite(closes, 20)
    vol_silence = volatilite(closes[-11:-1] if len(closes) >= 12 else closes, 9)

    vols_recent = volumes[-21:] if len(volumes) >= 5 else []
    vol_moyen = (sum(vols_recent) / len(vols_recent)) if vols_recent else None
    vol_actuel = parsed["market_volume"] if parsed["market_volume"] else (volumes[-1] if volumes else None)

    score, raisons = conviction(prix, s20, s50, s200, macd_data, rsi_val, var_semaine)

    return {
        "nom": item["nom"], "ticker": item["ticker"], "secteur": item["secteur"],
        "seuil": item["seuil"], "mots_cles": item["mots_cles"], "currency": parsed["currency"],
        "price": prix, "var_day": var_jour, "var_suspecte": var_suspecte,
        "var_week": var_semaine, "var_month": var_mois,
        "rsi": rsi_val, "macd": macd_data,
        "sma20": s20, "sma50": s50, "sma200": s200,
        "support": support, "resistance": resistance,
        "plus_haut_anterieur": plus_haut_anterieur, "plus_bas_anterieur": plus_bas_anterieur,
        "volatilite": vol, "vol_silence": vol_silence,
        "cur_vol": vol_actuel, "avg_vol": vol_moyen,
        "score": score, "label": libelle_conviction(score), "raisons": raisons,
    }


# =========================================================================
#  DÉTECTION DES SIGNAUX (rouge immédiat / orange sur transition)
# =========================================================================
def declencheurs_rouge(a):
    """Renvoie la liste des raisons d'une alerte ROUGE (vide si aucune)."""
    raisons = []
    if a["var_day"] is not None and abs(a["var_day"]) >= a["seuil"]:
        sens = "hausse" if a["var_day"] > 0 else "baisse"
        raisons.append(f"variation {a['var_day']:+.1f}% en {sens} (seuil {a['seuil']}%)")
    if (a["cur_vol"] and a["avg_vol"] and a["avg_vol"] > 0
            and a["cur_vol"] >= cfg.SEUIL_VOLUME * a["avg_vol"]):
        ratio = a["cur_vol"] / a["avg_vol"]
        raisons.append(f"volume {ratio:.1f}× la moyenne 1 mois")
    return raisons


def en_cooldown(state, a):
    """True si la valeur est encore en période de silence anti-spam."""
    last = state["red_cooldowns"].get(a["ticker"])
    if not last:
        return False
    if time.time() - last["ts"] >= cfg.COOLDOWN_MINUTES * 60:
        return False
    courant = a["var_day"] if a["var_day"] is not None else 0
    # On laisse repasser une alerte si le mouvement a nettement changé.
    if abs(courant - last.get("variation", 0)) >= cfg.COOLDOWN_BYPASS_PCT:
        return False
    return True


def etat_technique(a):
    """Photographie l'état technique d'une valeur (pour comparer d'une exécution à l'autre)."""
    zone_rsi = "neutre"
    if a["rsi"] is not None:
        if a["rsi"] >= 70:
            zone_rsi = "surachat"
        elif a["rsi"] <= 30:
            zone_rsi = "survente"
    signe_macd = None
    if a["macd"]:
        signe_macd = "pos" if a["macd"]["macd"] >= 0 else "neg"
    croix_mm = None
    if a["sma50"] and a["sma200"]:
        croix_mm = "golden" if a["sma50"] >= a["sma200"] else "death"
    au_dessus_res = bool(a["plus_haut_anterieur"] and a["price"] > a["plus_haut_anterieur"])
    sous_support = bool(a["plus_bas_anterieur"] and a["price"] < a["plus_bas_anterieur"])
    silence = bool(a["vol_silence"] is not None and a["vol_silence"] < cfg.SEUIL_SILENCE_VOLATILITE)
    return {
        "zone_rsi": zone_rsi, "signe_macd": signe_macd, "croix_mm": croix_mm,
        "au_dessus_res": au_dessus_res, "sous_support": sous_support, "silence": silence,
    }


def detecter_transitions(prec, nouv):
    """
    Renvoie la liste des signaux orange UNIQUEMENT sur CHANGEMENT d'état
    (sinon le même signal repartirait toutes les 5 minutes).
    """
    out = []
    if not prec:                       # 1re fois : on enregistre sans signaler
        return out

    if prec.get("croix_mm") and nouv.get("croix_mm") and prec["croix_mm"] != nouv["croix_mm"]:
        if nouv["croix_mm"] == "golden":
            out.append("🟢 Golden cross : la MM50 repasse au-dessus de la MM200 (signal de fond haussier).")
        else:
            out.append("🔴 Death cross : la MM50 repasse sous la MM200 (signal de fond baissier).")

    if prec.get("zone_rsi") != nouv.get("zone_rsi"):
        if nouv["zone_rsi"] == "surachat":
            out.append("RSI entré en zone de SURACHAT (> 70).")
        elif nouv["zone_rsi"] == "survente":
            out.append("RSI entré en zone de SURVENTE (< 30).")
        elif prec.get("zone_rsi") == "surachat":
            out.append("RSI sorti de la zone de surachat.")
        elif prec.get("zone_rsi") == "survente":
            out.append("RSI sorti de la zone de survente.")

    if prec.get("signe_macd") and nouv.get("signe_macd") and prec["signe_macd"] != nouv["signe_macd"]:
        if nouv["signe_macd"] == "pos":
            out.append("MACD repasse au-dessus de 0 (le momentum devient positif).")
        else:
            out.append("MACD repasse sous 0 (le momentum devient négatif).")

    if (not prec.get("au_dessus_res")) and nouv.get("au_dessus_res"):
        out.append("📈 Cassure d'un plus-haut récent (sortie par le haut).")
    if (not prec.get("sous_support")) and nouv.get("sous_support"):
        out.append("📉 Cassure d'un plus-bas récent (sortie par le bas).")

    if (not prec.get("silence")) and nouv.get("silence"):
        out.append("😴 Calme inhabituel (volatilité très faible) — la valeur s'endort.")
    return out


# =========================================================================
#  ACTUALITÉS (Google Actualités RSS)
# =========================================================================
def recuperer_actus(mots_cles, s):
    """Récupère les dernières actualités d'une valeur. Ne plante jamais."""
    from urllib.parse import quote
    url = ("https://news.google.com/rss/search?q=" + quote(mots_cles) +
           "&hl=fr&gl=FR&ceid=FR:fr")
    try:
        r = s.get(url, timeout=15)
        if r.status_code != 200:
            return []
        feed = feedparser.parse(r.content)
        items = []
        for e in feed.entries[:8]:
            items.append({
                "titre": e.get("title", ""),
                "lien": e.get("link", ""),
                "date": e.get("published", ""),
            })
        return items
    except Exception as ex:
        log(f"[ACTU] échec pour « {mots_cles} » : {ex}")
        return []


# =========================================================================
#  INTELLIGENCE ARTIFICIELLE (Google Gemini)
# =========================================================================
def _appel_ia_brut(prompt):
    """
    >>> SEUL POINT DE CONTACT AVEC LE FOURNISSEUR D'IA <<<

    Pour basculer vers une AUTRE API plus tard (ex. Claude / Anthropic),
    il suffit de réécrire CETTE SEULE fonction, en gardant la même signature :
    elle reçoit un 'prompt' (texte) et renvoie une réponse (texte) ou None.

    Gère proprement les erreurs 429 (quota) et 503 (surcharge) sans planter.
    """
    if not cfg.IA_ACTIVE or not GEMINI_API_KEY:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg.AI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    corps = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 700},
    }
    for tentative in range(3):
        try:
            r = requests.post(url, json=corps, timeout=30)
            if r.status_code == 200:
                data = r.json()
                cands = data.get("candidates") or []
                if not cands:
                    return None
                parts = cands[0].get("content", {}).get("parts", [])
                texte = "".join(p.get("text", "") for p in parts).strip()
                return texte or None
            if r.status_code in (429, 503):
                log(f"[IA] HTTP {r.status_code} (essai {tentative + 1}/3) — on patiente.")
                time.sleep(2 * (tentative + 1))
                continue
            log(f"[IA] HTTP {r.status_code} : {r.text[:160]}")
            return None
        except Exception as ex:
            log(f"[IA] exception : {ex}")
            time.sleep(2)
    return None


def _extraire_json(texte):
    """Extrait un objet JSON même si l'IA ajoute du texte ou des balises ```json autour."""
    if not texte:
        return None
    t = texte.strip()
    if "```" in t:
        t = t.replace("```json", "```")
        for bloc in t.split("```"):
            if "{" in bloc and "}" in bloc:
                t = bloc
                break
    debut, fin = t.find("{"), t.rfind("}")
    if debut == -1 or fin == -1 or fin <= debut:
        return None
    extrait = t[debut:fin + 1]
    try:
        return json.loads(extrait)
    except Exception:
        nettoye = re.sub(r",\s*([}\]])", r"\1", extrait)   # virgules traînantes
        try:
            return json.loads(nettoye)
        except Exception:
            return None


def _texte_position(a):
    parts = []
    if a["sma50"]:
        parts.append("au-dessus de la MM50" if a["price"] > a["sma50"] else "sous la MM50")
    if a["sma200"]:
        parts.append("au-dessus de la MM200" if a["price"] > a["sma200"] else "sous la MM200")
    return ", ".join(parts) or "n/d"


def interpreter(a, macro_txt, actus):
    """Demande à l'IA d'expliquer le « pourquoi ». Renvoie un dict ou None."""
    titres = " ; ".join(n["titre"] for n in actus[:4]) or "aucune actualité récente"
    macd_l = f"{a['macd']['macd']:.3f}" if a["macd"] else "n/d"
    prompt = f"""Tu es analyste financier. Tu fournis une INFORMATION d'aide à la décision, jamais un conseil d'achat ou de vente.
Réponds UNIQUEMENT par un objet JSON valide, sans aucun texte autour.

Valeur : {a['nom']} ({a['ticker']}) — {a['secteur']}
Cours : {a['price']:.4g} {a['currency']}
Variation jour : {_pct(a['var_day'])}, semaine : {_pct(a['var_week'])}, mois : {_pct(a['var_month'])}
RSI(14) : {_nb(a['rsi'])} | MACD (ligne) : {macd_l} | Position : {_texte_position(a)}
Score interne : {a['score']} ({a['label']})
Contexte macro : {macro_txt}
Actualités récentes : {titres}

Renvoie EXACTEMENT ce JSON :
{{"cause_probable": "1 à 2 phrases sur la cause probable du mouvement",
"lien_actualite": "le titre de l'actualité liée, ou chaîne vide",
"score_ajuste": un entier de -10 à 10,
"a_surveiller": "1 phrase : quoi surveiller ensuite",
"resume": "1 phrase de synthèse"}}"""
    return _extraire_json(_appel_ia_brut(prompt))


def commentaire_ia_digest(analyses, macro_txt):
    """Un court commentaire de marché pour le digest (1 seul appel IA)."""
    lignes = "\n".join(f"- {a['nom']} : {_pct(a['var_day'])} (score {a['score']})" for a in analyses)
    prompt = f"""Tu es analyste de marché. INFORMATION d'aide à la décision, jamais de conseil d'achat/vente.
Réponds en 2-3 phrases en français, sans liste.

Météo macro : {macro_txt}
Valeurs suivies ce matin :
{lignes}

Donne une synthèse générale de l'ambiance de marché et des points d'attention du jour."""
    rep = _appel_ia_brut(prompt)
    return rep.strip() if rep else None


# =========================================================================
#  ENVOI D'EMAILS (Gmail via SMTP_SSL port 465)
# =========================================================================
def envoyer_email(sujet, html):
    """Envoie un email HTML. Ne plante jamais ; logue les erreurs courantes."""
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and RECIPIENT_EMAIL):
        log("[EMAIL] secrets manquants (GMAIL_ADDRESS / GMAIL_APP_PASSWORD / RECIPIENT_EMAIL).")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = sujet
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = RECIPIENT_EMAIL
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as serveur:
            serveur.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            serveur.sendmail(GMAIL_ADDRESS, [RECIPIENT_EMAIL], msg.as_string())
        log(f"[EMAIL] envoyé : {sujet}")
        return True
    except smtplib.SMTPAuthenticationError:
        log("[EMAIL] ERREUR 535 : mot de passe d'application Gmail invalide ou 2FA non activée.")
        return False
    except Exception as ex:
        log(f"[EMAIL] échec : {ex}")
        return False


# =========================================================================
#  MISE EN FORME HTML DES EMAILS
# =========================================================================
def _pct(x):
    if x is None:
        return "n/d"
    return f"{x:+.1f}%"


def _nb(x, n=1):
    return f"{x:.{n}f}" if isinstance(x, (int, float)) else "n/d"


def _couleur(x):
    if x is None:
        return "#666"
    return "#137333" if x >= 0 else "#c5221f"


def _entete(titre, sous_titre):
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#202124;max-width:640px;margin:auto;">
      <div style="border-bottom:3px solid #1a73e8;padding-bottom:8px;margin-bottom:16px;">
        <div style="font-size:20px;font-weight:bold;">{titre}</div>
        <div style="font-size:13px;color:#5f6368;">{sous_titre}</div>
      </div>
    """


def _pied():
    return """
      <div style="margin-top:24px;padding-top:12px;border-top:1px solid #e0e0e0;
                  font-size:11px;color:#9aa0a6;">
        Agent boursier automatique — information d'aide à la décision, <b>pas un conseil
        d'investissement</b>. Données : Yahoo Finance &amp; Google Actualités.
      </div>
    </div>
    """


def _bloc_valeur(a, raisons=None, ia=None):
    """Carte HTML détaillée d'une valeur (utilisée dans rouge/orange)."""
    macd_txt = "n/d"
    if a["macd"]:
        signe = "au-dessus de 0" if a["macd"]["macd"] >= 0 else "sous 0"
        macd_txt = f"{a['macd']['macd']:.3f} ({signe})"
    lignes_raisons = ""
    if raisons:
        lignes_raisons = "<div style='margin-top:6px;'>" + "".join(
            f"<div style='font-size:13px;'>• {r}</div>" for r in raisons) + "</div>"
    bloc_ia = ""
    if ia:
        lien = ia.get("lien_actualite") or ""
        lien_html = f"<div style='font-size:12px;color:#5f6368;'>Actu liée : {lien}</div>" if lien else ""
        bloc_ia = f"""
        <div style="background:#f1f8ff;border-left:4px solid #1a73e8;padding:10px;margin-top:10px;border-radius:4px;">
          <div style="font-weight:bold;font-size:13px;">🤖 Lecture IA</div>
          <div style="font-size:13px;margin-top:4px;"><b>Cause probable :</b> {ia.get('cause_probable','—')}</div>
          {lien_html}
          <div style="font-size:13px;margin-top:4px;"><b>Score ajusté :</b> {ia.get('score_ajuste','—')}</div>
          <div style="font-size:13px;margin-top:4px;"><b>À surveiller :</b> {ia.get('a_surveiller','—')}</div>
        </div>"""
    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;padding:14px;margin-bottom:14px;">
      <div style="font-size:16px;font-weight:bold;">{a['nom']}
        <span style="font-size:12px;color:#5f6368;font-weight:normal;">({a['ticker']} · {a['secteur']})</span>
      </div>
      <div style="font-size:22px;font-weight:bold;margin:4px 0;">
        {a['price']:.4g} {a['currency']}
        <span style="font-size:16px;color:{_couleur(a['var_day'])};">{_pct(a['var_day'])}</span>
      </div>
      <div style="font-size:13px;color:#3c4043;">
        Semaine {_pct(a['var_week'])} · Mois {_pct(a['var_month'])} ·
        RSI {_nb(a['rsi'],0)} · MACD {macd_txt}
      </div>
      <div style="font-size:13px;margin-top:4px;">
        Score de conviction : <b>{a['score']:+d}/10</b> — {a['label']}
      </div>
      {lignes_raisons}
      {bloc_ia}
    </div>"""


def rendu_rouge(enrichis, macro_txt, now):
    n = len(enrichis)
    titre = ("🔴 ALERTE — mouvement important" if n == 1
             else f"🔴 ALERTE — {n} mouvements importants")
    html = _entete(titre, f"{now:%d/%m/%Y %H:%M} · {macro_txt}")
    for a, raisons, ia in enrichis:
        html += _bloc_valeur(a, raisons=raisons, ia=ia)
    return html + _pied()


def sujet_rouge(enrichis):
    if len(enrichis) == 1:
        a = enrichis[0][0]
        return f"🔴 {a['nom']} {_pct(a['var_day'])}"
    noms = ", ".join(e[0]["nom"] for e in enrichis[:3])
    suite = "…" if len(enrichis) > 3 else ""
    return f"🔴 {len(enrichis)} alertes : {noms}{suite}"


def rendu_orange(queue, macro_txt, now):
    html = _entete("🟠 Point de surveillance", f"{now:%d/%m/%Y %H:%M} · {macro_txt}")
    techniques = [q for q in queue if q.get("type") == "technique"]
    actus = [q for q in queue if q.get("type") == "actu"]
    if techniques:
        html += "<div style='font-size:15px;font-weight:bold;margin:8px 0;'>📊 Signaux techniques</div>"
        for q in techniques:
            html += (f"<div style='border:1px solid #eee;border-radius:6px;padding:10px;margin-bottom:8px;'>"
                     f"<b>{q['nom']}</b> "
                     f"<span style='font-size:12px;color:#5f6368;'>(score {q.get('score','?'):+d}, {q.get('label','')})</span>"
                     f"<div style='font-size:13px;margin-top:4px;'>{q['message']}</div></div>")
    if actus:
        html += "<div style='font-size:15px;font-weight:bold;margin:14px 0 8px;'>📰 Actualités nouvelles</div>"
        for q in actus:
            html += (f"<div style='font-size:13px;margin-bottom:8px;'>"
                     f"<b>{q['nom']}</b> — <a href='{q['lien']}' style='color:#1a73e8;'>{q['titre']}</a></div>")
    return html + _pied()


def sujet_orange(queue):
    nb_t = sum(1 for q in queue if q.get("type") == "technique")
    nb_a = sum(1 for q in queue if q.get("type") == "actu")
    return f"🟠 Point surveillance : {nb_t} signal(aux), {nb_a} actu(s)"


def ligne_digest(a):
    return f"""
    <tr>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;font-weight:bold;">{a['nom']}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{a['price']:.4g}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;color:{_couleur(a['var_day'])};">{_pct(a['var_day'])}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;color:{_couleur(a['var_week'])};">{_pct(a['var_week'])}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;color:{_couleur(a['var_month'])};">{_pct(a['var_month'])}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{_nb(a['rsi'],0)}</td>
      <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;font-weight:bold;">{a['score']:+d}</td>
    </tr>"""


def rendu_digest(analyses, macro, macro_txt, now, commentaire_ia):
    html = _entete("☕ Digest matinal", f"{now:%A %d/%m/%Y} · avant l'ouverture")
    # Météo macro
    html += "<div style='font-size:15px;font-weight:bold;margin:8px 0;'>🌍 Météo des marchés</div>"
    html += "<div style='font-size:13px;margin-bottom:12px;'>"
    for m in macro:
        html += (f"<span style='display:inline-block;margin-right:14px;'>"
                 f"<b>{m['nom']}</b> : {m['price']:.4g} "
                 f"<span style='color:{_couleur(m['var_day'])};'>{_pct(m['var_day'])}</span></span>")
    html += "</div>"
    if commentaire_ia:
        html += (f"<div style='background:#f1f8ff;border-left:4px solid #1a73e8;padding:10px;"
                 f"border-radius:4px;font-size:13px;margin-bottom:14px;'>🤖 {commentaire_ia}</div>")
    # Tableau des valeurs
    html += """
    <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;">
      <tr style="background:#f5f5f5;">
        <th style="padding:6px 8px;text-align:left;">Valeur</th>
        <th style="padding:6px 8px;text-align:right;">Cours</th>
        <th style="padding:6px 8px;text-align:right;">Jour</th>
        <th style="padding:6px 8px;text-align:right;">Sem.</th>
        <th style="padding:6px 8px;text-align:right;">Mois</th>
        <th style="padding:6px 8px;text-align:right;">RSI</th>
        <th style="padding:6px 8px;text-align:right;">Score</th>
      </tr>"""
    for a in sorted(analyses, key=lambda x: (x["var_day"] is None, -(x["var_day"] or 0))):
        html += ligne_digest(a)
    html += "</table>"
    # Mouvements marquants
    avec_var = [a for a in analyses if a["var_day"] is not None]
    if avec_var:
        haut = max(avec_var, key=lambda x: x["var_day"])
        bas = min(avec_var, key=lambda x: x["var_day"])
        html += (f"<div style='font-size:13px;margin-top:14px;'>"
                 f"📈 Plus forte hausse : <b>{haut['nom']}</b> {_pct(haut['var_day'])} · "
                 f"📉 Plus forte baisse : <b>{bas['nom']}</b> {_pct(bas['var_day'])}</div>")
    return html + _pied()


def rendu_demarrage(analyses, macro_txt):
    html = _entete("✅ Agent boursier démarré", "Premier lancement réussi")
    html += ("<div style='font-size:14px;'>L'agent est opérationnel. Tu recevras désormais :</div>"
             "<ul style='font-size:13px;'>"
             "<li>🔴 des alertes <b>immédiates</b> sur les mouvements importants ;</li>"
             "<li>🟠 un <b>point regroupé</b> 1 à 2 fois par jour (signaux techniques + actus) ;</li>"
             "<li>☕ un <b>digest chaque matin à 8h</b>, avant l'ouverture.</li></ul>"
             f"<div style='font-size:13px;color:#5f6368;'>{macro_txt}</div>"
             f"<div style='font-size:13px;margin-top:8px;'>{len(analyses)} valeur(s) correctement chargée(s).</div>")
    return html + _pied()


# =========================================================================
#  CONTEXTE MACRO
# =========================================================================
def recuperer_macro(s):
    """Récupère les indices macro. Renvoie une liste (valeurs indisponibles ignorées)."""
    res = []
    for m in cfg.MACRO:
        parsed = yahoo_chart(m["ticker"], s)
        if not parsed:
            continue
        closes = _propre(parsed["closes"])
        if len(closes) < 2:
            continue
        prix = parsed["market_price"] if parsed["market_price"] is not None else closes[-1]
        var = variation_du_jour(parsed["ts"], parsed["closes"],
                                parsed["gmtoffset"], parsed["market_price"])
        if var is not None and abs(var) > cfg.GARDE_FOU_VARIATION:
            var = None
        res.append({"nom": m["nom"], "ticker": m["ticker"], "price": prix, "var_day": var})
    return res


def texte_macro(macro):
    """Petite phrase résumant la météo macro (avec lecture du VIX)."""
    if not macro:
        return "Contexte macro indisponible."
    morceaux = []
    for m in macro:
        txt = f"{m['nom']} {_pct(m['var_day'])}"
        if m["ticker"] == "^VIX":
            v = m["price"]
            if v is not None:
                if v < 15:
                    humeur = "marché calme"
                elif v < 20:
                    humeur = "marché normal"
                elif v < 30:
                    humeur = "marché nerveux"
                else:
                    humeur = "marché sous stress"
                txt = f"VIX {v:.1f} ({humeur})"
        morceaux.append(txt)
    return " · ".join(morceaux)


# =========================================================================
#  NETTOYAGE & UTILITAIRES D'ÉTAT
# =========================================================================
def purger_anciens_creneaux(state, now):
    """Garde uniquement les créneaux orange des 3 derniers jours (évite de gonfler state.json)."""
    limite = (now.date() - timedelta(days=3)).isoformat()
    state["orange_slots_sent"] = {
        d: v for d, v in state["orange_slots_sent"].items() if d >= limite
    }


# =========================================================================
#  PROGRAMME PRINCIPAL
# =========================================================================
def main():
    log("================ Démarrage de l'exécution ================")
    state = charger_etat()
    now = maintenant_paris()
    aujourd_hui = now.date().isoformat()

    s = creer_session()
    rechauffer_session(s)

    # 1) Analyser chaque valeur de la watchlist
    analyses = []
    for item in cfg.WATCHLIST:
        parsed = yahoo_chart(item["ticker"], s)
        if not parsed:
            continue
        a = analyser(item, parsed)
        if a:
            analyses.append(a)
    log(f"{len(analyses)}/{len(cfg.WATCHLIST)} valeur(s) analysée(s).")

    # 2) Contexte macro
    macro = recuperer_macro(s)
    macro_txt = texte_macro(macro)

    # 3) PREMIER LANCEMENT : on initialise sans envoyer d'alertes en masse
    if not state.get("initialized"):
        for a in analyses:
            actus = recuperer_actus(a["mots_cles"], s)
            state["seen_news"][a["ticker"]] = sorted(n["lien"] for n in actus if n["lien"])
            state["tech_state"][a["ticker"]] = etat_technique(a)
        state["initialized"] = True
        purger_anciens_creneaux(state, now)
        sauver_etat(state)
        if cfg.ENVOYER_EMAIL_DEMARRAGE:
            envoyer_email("✅ Agent boursier démarré", rendu_demarrage(analyses, macro_txt))
        log("Premier lancement : état initialisé, aucune alerte envoyée.")
        log("================ Fin de l'exécution ================")
        return

    budget_ia = [cfg.MAX_APPELS_IA]   # liste = mutable, pour décrémenter dans les fonctions

    # 4) Détection ROUGE + transitions ORANGE + nouvelles actus
    rouges = []
    for a in analyses:
        tk = a["ticker"]

        # --- ROUGE (immédiat) ---
        decl = declencheurs_rouge(a)
        if decl and not en_cooldown(state, a):
            rouges.append((a, decl))

        # --- ORANGE : signaux techniques sur TRANSITION uniquement ---
        prec = state["tech_state"].get(tk, {})
        nouv = etat_technique(a)
        for tr in detecter_transitions(prec, nouv):
            state["orange_queue"].append({
                "type": "technique", "ticker": tk, "nom": a["nom"],
                "message": tr, "score": a["score"], "label": a["label"],
            })
        state["tech_state"][tk] = nouv

        # --- ORANGE : actualités nouvelles (jamais vues) ---
        actus = recuperer_actus(a["mots_cles"], s)
        vues = set(state["seen_news"].get(tk, []))
        for n in actus:
            if n["lien"] and n["lien"] not in vues:
                state["orange_queue"].append({
                    "type": "actu", "ticker": tk, "nom": a["nom"],
                    "titre": n["titre"], "lien": n["lien"],
                })
                vues.add(n["lien"])
        state["seen_news"][tk] = sorted(vues)[-50:]   # on borne la mémoire

    # 5) Envoi ROUGE — REGROUPÉ en un seul email, IA plafonnée
    if rouges:
        # On pose le cooldown AVANT d'envoyer (évite tout doublon).
        for a, _ in rouges:
            state["red_cooldowns"][a["ticker"]] = {
                "ts": time.time(),
                "variation": a["var_day"] if a["var_day"] is not None else 0,
            }
        enrichis = []
        for a, decl in rouges:
            ia = None
            if budget_ia[0] > 0:
                actus = recuperer_actus(a["mots_cles"], s)
                ia = interpreter(a, macro_txt, actus)
                budget_ia[0] -= 1
            enrichis.append((a, decl, ia))
        envoyer_email(sujet_rouge(enrichis), rendu_rouge(enrichis, macro_txt, now))
        log(f"{len(enrichis)} alerte(s) rouge(s) -> 1 email groupé.")

    # 6) Envoi ORANGE — aux créneaux configurés (ex. 13h, 18h)
    creneaux_envoyes = state["orange_slots_sent"].get(aujourd_hui, [])
    dus = [c for c in cfg.HEURES_ORANGE
           if now.hour >= c and now.hour < c + cfg.FENETRE_ORANGE_H and str(c) not in creneaux_envoyes]
    if dus and state["orange_queue"]:
        envoyer_email(sujet_orange(state["orange_queue"]),
                      rendu_orange(state["orange_queue"], macro_txt, now))
        for c in dus:
            creneaux_envoyes.append(str(c))
        state["orange_slots_sent"][aujourd_hui] = sorted(set(creneaux_envoyes))
        state["orange_queue"] = []
        log("Point orange regroupé envoyé.")

    # 7) DIGEST — le matin (filet jusqu'à HEURE_LIMITE_DIGEST si le cron est en retard)
    if (cfg.HEURE_DIGEST <= now.hour < cfg.HEURE_LIMITE_DIGEST
            and state.get("last_digest_date") != aujourd_hui and analyses):
        commentaire = None
        if budget_ia[0] > 0:
            commentaire = commentaire_ia_digest(analyses, macro_txt)
            budget_ia[0] -= 1
        envoyer_email(f"☕ Digest matinal — {now:%d/%m/%Y}",
                      rendu_digest(analyses, macro, macro_txt, now, commentaire))
        state["last_digest_date"] = aujourd_hui
        log("Digest matinal envoyé.")

    # 8) Sauvegarde de l'état
    purger_anciens_creneaux(state, now)
    sauver_etat(state)
    log("================ Fin de l'exécution ================")


if __name__ == "__main__":
    main()
