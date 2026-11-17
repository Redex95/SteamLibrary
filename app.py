"""
Steam Library Explorer - versione per Vercel.

Il server non ha stato e non salva nulla: chiavi, token, specifiche del PC e libreria
vivono nel browser (localStorage / IndexedDB). Il server serve la pagina e fa da proxy
verso Steam, perché le API di Steam non si possono chiamare direttamente dal browser (CORS).

Locale:  pip install flask requests && python app.py   ->  http://127.0.0.1:5057
Vercel:  vercel   (rileva da solo Flask da app.py + requirements.txt)
"""
import html as htmllib
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
BASE = "https://api.steampowered.com"


class SteamError(Exception):
    pass


@app.after_request
def no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(SteamError)
def on_steam_error(e):
    return jsonify(error=str(e)), 502


@app.errorhandler(requests.RequestException)
def on_network_error(e):
    # niente dettagli: il messaggio di requests può contenere l'URL con la chiave
    return jsonify(error="Impossibile contattare Steam."), 502


@app.errorhandler(Exception)
def on_error(e):
    if isinstance(e, HTTPException):
        return e
    return jsonify(error="Errore interno del server."), 500


def clean(v):
    """Toglie spazi e virgolette attorno al valore: "1234" diventa 1234, e "" o '' contano come vuoto."""
    return str(v or "").strip().strip("\"'`\u201c\u201d\u2018\u2019").strip()


def body():
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------------------
# Tabella GPU: punteggio relativo (RX 7800 XT = 100). Valori approssimativi
# di prestazioni raster, servono solo a ordinare/confrontare.
# ---------------------------------------------------------------------------
NV = {
    "5090": 250, "5080": 165, "5070ti": 145, "5070": 118, "5060ti": 95, "5060": 80,
    "4090": 190, "4080super": 150, "4080": 145, "4070tisuper": 125, "4070ti": 118, "4070super": 110,
    "4070": 98, "4060ti": 82, "4060": 68,
    "3090ti": 128, "3090": 118, "3080ti": 117, "3080": 106, "3070ti": 90, "3070": 84, "3060ti": 76,
    "3060": 58, "3050": 42,
    "2080ti": 88, "2080super": 78, "2080": 72, "2070super": 68, "2070": 60, "2060super": 56, "2060": 48,
    "1660ti": 40, "1660super": 40, "1660": 36, "1650super": 30, "1650": 22,
    "1080ti": 62, "1080": 52, "1070ti": 47, "1070": 43, "1060": 29, "1050ti": 20, "1050": 16,
    "980ti": 32, "980": 26, "970": 22, "960": 14, "950": 11, "780ti": 16, "780": 13, "770": 10,
    "760": 8, "750ti": 8, "750": 7, "680": 8, "670": 7, "660ti": 7, "660": 6, "650": 4,
}
AMD = {
    "9070xt": 135, "9070": 120, "7900xtx": 135, "7900xt": 120, "7900gre": 105, "7800xt": 100,
    "7700xt": 88, "7600xt": 62, "7600": 58,
    "6950xt": 110, "6900xt": 104, "6800xt": 98, "6800": 90, "6750xt": 78, "6700xt": 72, "6650xt": 60,
    "6600xt": 56, "6600": 52, "6500xt": 28, "6400": 20,
    "5700xt": 58, "5700": 50, "5600xt": 46, "5500xt": 30,
    "590": 32, "580": 30, "570": 26, "560": 15, "550": 10, "480": 28, "470": 24, "460": 14,
}
OLD_AMD = {"390": 24, "380": 16, "290": 18, "280": 12, "270": 10, "7970": 12, "7870": 9}
VEGA = {"64": 46, "56": 42}
ARC = {"770": 62, "750": 56, "580": 48, "380": 20}


def combine(found):
    """found = [(vendor, etichetta, punteggio)]. Un requisito elenca di solito un componente per marca
    (es. "i7-12700 o Ryzen 7 7800X3D") e ne basta uno: per ogni marca tengo il più potente
    e come punteggio uso il più basso tra le marche."""
    best = {}
    for vendor, label, score in found:
        if vendor not in best or score > best[vendor][1]:
            best[vendor] = (label, score)
    if not best:
        return None, None
    return " / ".join(l for l, _ in best.values()), min(sc for _, sc in best.values())


def best_gpu(text):
    """Cerca nomi di GPU nel testo e restituisce (etichetta, punteggio)."""
    found = []
    for m in re.finditer(r"(?:GTX|RTX)\s*(\d{3,4})((?:\s*(?:Ti|SUPER))*)", text, re.I):
        key = m.group(1) + re.sub(r"\s+", "", m.group(2)).lower()
        if key in NV:
            found.append(("nvidia", re.sub(r"\s+", " ", m.group(0)).strip(), NV[key]))
    for m in re.finditer(r"RX\s*(\d{3,4})\s*(XTX|XT|GRE)?", text, re.I):
        key = m.group(1) + (m.group(2) or "").lower()
        if key in AMD:
            found.append(("amd", re.sub(r"\s+", " ", m.group(0)).strip(), AMD[key]))
    for m in re.finditer(r"\bR9\s*(\d{3})", text, re.I):
        if m.group(1) in OLD_AMD:
            found.append(("amd", m.group(0), OLD_AMD[m.group(1)]))
    for m in re.finditer(r"Vega\s*(\d{2})", text, re.I):
        if m.group(1) in VEGA:
            found.append(("amd", m.group(0), VEGA[m.group(1)]))
    for m in re.finditer(r"Arc\s*A(\d{3})", text, re.I):
        if m.group(1) in ARC:
            found.append(("intel", m.group(0), ARC[m.group(1)]))
    return combine(found)


# ---------------------------------------------------------------------------
# Tabella CPU: punteggio relativo (Ryzen 7 7700 = 100), stima gaming. Chiavi = numero del modello.
INTEL = {
    "14900": 128, "14700": 122, "14600": 108, "13900": 126, "13700": 116, "13600": 106, "13500": 96,
    "13400": 90, "13100": 66, "12900": 110, "12700": 100, "12600": 94, "12500": 84, "12400": 80, "12100": 58,
    "11900": 88, "11700": 82, "11600": 78, "11500": 74, "11400": 70, "10900": 80, "10700": 72, "10600": 66,
    "10500": 62, "10400": 58, "10100": 40, "9900": 74, "9700": 64, "9600": 56, "9400": 50, "9100": 38,
    "8700": 66, "8600": 56, "8500": 52, "8400": 50, "8350": 42, "8100": 40, "7700": 52, "7600": 46,
    "7500": 44, "7400": 42, "7350": 38, "7100": 28, "6700": 48, "6600": 42, "6500": 38, "6400": 36, "6100": 26,
    "4790": 44, "4770": 42, "4690": 38, "4670": 36, "4590": 34, "4570": 33, "4460": 33, "4440": 31, "4430": 32,
    "4160": 24, "4130": 24, "3770": 36, "3570": 32, "3550": 31, "3470": 30, "3450": 29, "3350": 28, "3330": 26,
    "3240": 19, "3220": 18, "2700": 32, "2600": 30, "2500": 26, "2400": 24, "2300": 20, "2100": 17,
    "950": 15, "920": 14, "860": 14, "750": 14,
}
ULTRA = {"285": 125, "265": 118, "245": 104, "235": 95}
RYZEN = {
    "9950": 135, "9900": 130, "9800x3d": 140, "9700": 112, "9600": 106, "7950x3d": 128, "7950": 122, "7900": 114,
    "7800x3d": 125, "7700": 100, "7600": 94, "7500": 88, "5950": 105, "5900": 100, "5800x3d": 108, "5800": 92,
    "5700": 88, "5600": 80, "5500": 70, "3950": 90, "3900": 87, "3800": 75, "3700": 72, "3600": 67, "3500": 60,
    "3300": 55, "3100": 45, "2700": 56, "2600": 51, "2400": 36, "2200": 30, "1800": 50, "1700": 45, "1600": 42,
    "1500": 36, "1400": 32, "1300": 30, "1200": 26,
}
FX = {"9590": 34, "9370": 33, "8350": 30, "8320": 28, "8150": 26, "6350": 24, "6300": 22, "4300": 18}


def best_cpu(text):
    """Cerca nomi di CPU nel testo e restituisce (etichetta, punteggio)."""
    found = []
    for m in re.finditer(r"\bi([3579])\s*-?\s*(\d{3,5})", text, re.I):
        if m.group(2) in INTEL:
            found.append(("intel", f"i{m.group(1)}-{m.group(2)}", INTEL[m.group(2)]))
    for m in re.finditer(r"Ultra\s*[579]\s*(\d{3})", text, re.I):
        if m.group(1) in ULTRA:
            found.append(("intel", re.sub(r"\s+", " ", m.group(0)), ULTRA[m.group(1)]))
    for m in re.finditer(r"Ryzen\s*[3579]\s*(\d{4})\s*(X3D)?", text, re.I):
        key = m.group(1) + ("x3d" if m.group(2) else "")
        if key in RYZEN or m.group(1) in RYZEN:
            found.append(("amd", re.sub(r"\s+", " ", m.group(0)).strip(), RYZEN.get(key, RYZEN.get(m.group(1)))))
    for m in re.finditer(r"\bFX[- ]?(\d{4})", text, re.I):
        if m.group(1) in FX:
            found.append(("amd", f"FX-{m.group(1)}", FX[m.group(1)]))
    return combine(found)


# ---------------------------------------------------------------------------
# Requisiti di sistema (Steam Store API)
# ---------------------------------------------------------------------------
def clean_html(s):
    s = re.sub(r"<br\s*/?>|</li>|</ul>|</p>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return htmllib.unescape(s).strip()


def to_gb(num, unit):
    v = float(num)
    return v / 1024 if unit.upper() == "MB" else v


def parse_ram(t):
    m = re.search(r"(?:Memory|RAM)\D{0,20}?(\d+(?:\.\d+)?)\s*(GB|MB)", t, re.I) or \
        re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)\s*(?:of\s*)?RAM", t, re.I)
    return round(to_gb(*m.groups()), 1) if m else None


def parse_storage(t):
    m = re.search(r"(?:Storage|Hard Drive|Hard Disk|Disk Space)\D{0,40}?(\d+(?:\.\d+)?)\s*(GB|MB)", t, re.I)
    return round(to_gb(*m.groups()), 1) if m else None


def analyse(data):
    reqs = data.get("pc_requirements")
    out = {"v": 2, "type": data.get("type"), "gpu": None, "gpu_score": None, "cpu": None, "cpu_score": None,
           "ram": None, "storage": None, "req_min": "", "req_rec": ""}
    if not isinstance(reqs, dict):
        return out
    mn, rec = clean_html(reqs.get("minimum")), clean_html(reqs.get("recommended"))
    out["req_min"], out["req_rec"] = mn[:700], rec[:700]
    for text in (rec, mn):  # priorità ai requisiti consigliati
        if out["gpu_score"] is None:
            out["gpu"], out["gpu_score"] = best_gpu(text)
        if out["cpu_score"] is None:
            out["cpu"], out["cpu_score"] = best_cpu(text)
        if out["ram"] is None:
            out["ram"] = parse_ram(text)
        if out["storage"] is None:
            out["storage"] = parse_storage(text)
    return out


# ---------------------------------------------------------------------------
# API (stateless: le credenziali arrivano nel corpo della richiesta e non vengono salvate)
# ---------------------------------------------------------------------------
def steam_get(path, params, timeout=25):
    r = requests.get(f"{BASE}/{path}", params=params, timeout=timeout)
    if r.status_code in (401, 403):
        raise SteamError("Steam ha rifiutato le credenziali (API key o token non validi, oppure profilo privato).")
    if r.status_code == 429:
        raise SteamError("Steam sta limitando le richieste, riprova tra poco.")
    if not r.ok:
        raise SteamError(f"Steam ha risposto con errore {r.status_code}.")
    return r.json()


@app.post("/api/owned")
def api_owned():
    b = body()
    key, sid = clean(b.get("api_key")), clean(b.get("steam_id"))
    if not key or not sid:
        return jsonify(error="Servono API key e SteamID64."), 400
    d = steam_get("IPlayerService/GetOwnedGames/v1/", {
        "key": key, "steamid": sid, "include_appinfo": 1, "include_played_free_games": 1})
    games = [{"appid": g["appid"], "name": g.get("name", ""), "hours": round(g.get("playtime_forever", 0) / 60, 1)}
             for g in d.get("response", {}).get("games", [])]
    return jsonify(games=games)


@app.post("/api/family")
def api_family():
    b = body()
    token, sid = clean(b.get("token")), clean(b.get("steam_id"))
    if not token or not sid:
        return jsonify(error="Servono token e SteamID64."), 400
    g = steam_get("IFamilyGroupsService/GetFamilyGroupForUser/v1/", {"access_token": token, "steamid": sid})
    gid = g.get("response", {}).get("family_groupid")
    if not gid:
        raise SteamError("Non risulti in nessun gruppo famiglia (o il token è scaduto).")
    s = steam_get("IFamilyGroupsService/GetSharedLibraryApps/v1/", {
        "access_token": token, "family_groupid": gid, "steamid": sid, "include_own": 1, "include_free": 0}, timeout=50)
    apps = [{"appid": a["appid"], "name": a.get("name", ""), "owners": [str(x) for x in a.get("owner_steamids", [])]}
            for a in s.get("response", {}).get("apps", [])]
    return jsonify(apps=apps)


@app.post("/api/players")
def api_players():
    b = body()
    key = clean(b.get("api_key"))
    ids = [clean(i) for i in (b.get("ids") or [])][:100]
    if not key or not ids:
        return jsonify(error="Servono API key e SteamID."), 400
    p = steam_get("ISteamUser/GetPlayerSummaries/v2/", {"key": key, "steamids": ",".join(ids)})
    names = {pl["steamid"]: pl.get("personaname", pl["steamid"]) for pl in p.get("response", {}).get("players", [])}
    return jsonify(names=names)


@app.post("/api/details")
def api_details():
    """Requisiti di sistema per un piccolo gruppo di giochi (max 10), scaricati in parallelo."""
    ids = []
    for x in (body().get("appids") or [])[:10]:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass

    def one(appid):
        try:
            r = requests.get("https://store.steampowered.com/api/appdetails", params={
                "appids": appid, "cc": "it", "l": "english", "filters": "basic,pc_requirements"}, timeout=8)
            if r.status_code == 429:
                return str(appid), {"rate": True}
            if not r.ok:
                return str(appid), {"fail": True}
            entry = r.json().get(str(appid), {})
            return str(appid), (analyse(entry["data"]) if entry.get("success") else {"v": 2, "error": True})
        except Exception:
            return str(appid), {"fail": True}

    if not ids:
        return jsonify(results={})
    with ThreadPoolExecutor(max_workers=len(ids)) as ex:
        return jsonify(results=dict(ex.map(one, ids)))


@app.post("/api/pc")
def api_pc():
    b = body()
    gl, gs = best_gpu(str(b.get("gpu") or ""))
    cl, cs = best_cpu(str(b.get("cpu") or ""))
    return jsonify(gpu_label=gl, gpu_score=gs, cpu_label=cl, cpu_score=cs)


@app.get("/")
def index():
    return render_template("index.html")



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057, debug=False)