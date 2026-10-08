#!/usr/bin/env python3
"""
Alerte Gazole TotalEnergies - Sarthe (72)
Surveille la DISPONIBILITE du Gazole (pas le prix).
Alerte en cas de retour en stock ou de rupture.
"""

import requests
import json
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw

# ============================================================
# CONFIGURATION
# ============================================================

NTFY_TOPIC = "total72-gazole-stock"
DISTANCE_MAX_METRES = 150
FICHIER_STOCKS = "etats_gazole.json"
FICHIER_CACHE = "stations_total_cache.json"
FICHIER_RECAP = "recap_dernier.json"
DOSSIER_PUBLIC = "public"
HEURE_RECAP = 8

# ============================================================


def charger_json(fichier, defaut):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return defaut
    return defaut


def sauvegarder_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def creer_icones_png():
    """Genere les icones PNG 192x192 et 512x512 - orange diesel."""
    os.makedirs(DOSSIER_PUBLIC, exist_ok=True)

    for taille in (192, 512):
        img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        marge = taille // 16
        draw.rounded_rectangle(
            [marge, marge, taille - marge, taille - marge],
            radius=taille // 8,
            fill=(230, 126, 34, 255),
        )

        # Goutte de carburant stylisee (goutte)
        draw.polygon([
            (int(taille * 0.50), int(taille * 0.15)),
            (int(taille * 0.28), int(taille * 0.55)),
            (int(taille * 0.32), int(taille * 0.75)),
            (int(taille * 0.50), int(taille * 0.85)),
            (int(taille * 0.68), int(taille * 0.75)),
            (int(taille * 0.72), int(taille * 0.55)),
        ], fill=(255, 255, 255, 255))

        # Interieur de la goutte (orange clair pour effet 3D)
        draw.ellipse(
            [int(taille * 0.38), int(taille * 0.60),
             int(taille * 0.62), int(taille * 0.78)],
            fill=(230, 126, 34, 255),
        )

        img.save(os.path.join(DOSSIER_PUBLIC, f"icon-{taille}.png"))
        print(f"   Icone {taille}x{taille} generee")


def creer_manifest():
    manifest = {
        "name": "Alerte Gazole Sarthe",
        "short_name": "Alerte Gazole",
        "description": "Disponibilite du Gazole chez TotalEnergies en Sarthe",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#e67e22",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    with open(os.path.join(DOSSIER_PUBLIC, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"   Manifest cree")


def envoyer_notification(titre, message, priorite="max"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": titre.encode("utf-8"),
                "Priority": "max",
                "Tags": "fuel,rotating_light,warning",
                "X-Priority": "1",
            },
            timeout=10,
        )
        print(f"[{datetime.now():%H:%M:%S}] Notification envoyee : {titre}")
    except Exception as e:
        print(f"[ERREUR] Envoi notification : {e}")


def distance_metres(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111000
    dlon = (lon1 - lon2) * 111000 * math.cos(math.radians(lat1))
    return math.sqrt(dlat**2 + dlon**2)


def recuperer_positions_total_sarthe():
    cache = charger_json(FICHIER_CACHE, None)
    if cache and isinstance(cache, dict):
        positions = cache.get("positions", [])
        if positions:
            print(f"   Cache trouve ({len(positions)} stations)")
            return positions

    print("   Interrogation d'Overpass...")
    serveurs = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    query = """
    [out:json][timeout:60];
    (
      node["amenity"="fuel"]["brand"~"Total",i](47.70,-0.70,48.50,1.00);
      way["amenity"="fuel"]["brand"~"Total",i](47.70,-0.70,48.50,1.00);
    );
    out center;
    """
    for serveur in serveurs:
        try:
            r = requests.get(
                serveur,
                params={"data": query},
                headers={"User-Agent": "AlerteGazoleSarthe/1.0"},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            positions = []
            for el in data.get("elements", []):
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None or lon is None:
                    continue
                tags = el.get("tags", {})
                nom = tags.get("name") or tags.get("brand") or tags.get("operator") or "Total"
                positions.append({"lat": float(lat), "lon": float(lon), "nom": nom})
            if positions:
                print(f"      {len(positions)} stations recues")
                sauvegarder_json(FICHIER_CACHE, {
                    "date": datetime.now().isoformat(),
                    "positions": positions,
                })
                return positions
        except Exception as e:
            print(f"      Echec : {type(e).__name__}")
            continue

    print("[ERREUR] Aucun serveur Overpass et pas de cache.")
    return []


def recuperer_stations_sarthe():
    url = (
        "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
        "prix-des-carburants-en-france-flux-instantane-v2/records"
        "?where=startswith(cp,%2272%22)&limit=100"
    )
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"[ERREUR] API gouvernementale : {e}")
        return []


def etat_gazole(station):
    """Retourne 'dispo', 'temp', 'def' ou None pour le Gazole."""
    rupture = station.get("gazole_rupture_type")
    prix = station.get("gazole_prix")
    if rupture == "temporaire":
        return "temp"
    if rupture == "definitive":
        return "def"
    if prix is not None:
        return "dispo"
    return None


def generer_page_html(stations_data, chemin="public/index.html"):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)

    paris = datetime.now(ZoneInfo("Europe/Paris"))
    date_heure = paris.strftime("%d/%m/%Y a %Hh%M")

    # Separe les stations dispo et indispo
    dispo = [s for s in stations_data if s["etat"] == "dispo"]
    temp = [s for s in stations_data if s["etat"] == "temp"]
    definitive = [s for s in stations_data if s["etat"] == "def"]

    dispo.sort(key=lambda s: s.get("ville", "ZZZ"))
    temp.sort(key=lambda s: s.get("ville", "ZZZ"))
    definitive.sort(key=lambda s: s.get("ville", "ZZZ"))

    def card(s, couleur, badge):
        prix_html = ""
        if s.get("prix") is not None:
            prix_html = f'<div class="prix">{s["prix"]:.3f} EUR/L</div>'
        return f'''
        <div class="station" style="border-left-color: {couleur};">
            <div class="badge" style="background: {couleur};">{badge}</div>
            <div class="ville">{s.get("ville", "?")} <span class="cp">({s.get("cp", "?")})</span></div>
            <div class="adresse">{s.get("adresse", "?")}</div>
            {prix_html}
        </div>'''

    dispo_html = "".join([card(s, "#090", "DISPO") for s in dispo])
    temp_html = "".join([card(s, "#e80", "RUPTURE TEMP.") for s in temp])
    def_html = "".join([card(s, "#c00", "RUPTURE DEF.") for s in definitive])

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alerte Gazole Sarthe</title>
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#e67e22">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         margin: 0; padding: 16px; background: #f0f2f5; color: #222;
         display: flex; flex-direction: column; align-items: center; }}
  header, h2, .stations, .date {{ width: 100%; max-width: 700px; }}
  header {{ background: linear-gradient(135deg, #e67e22, #b35c14);
            color: white; padding: 20px; border-radius: 12px;
            margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h1 {{ margin: 0; font-size: 1.3em; }}
  .compteur {{ margin-top: 8px; font-size: 1em; opacity: 0.95; }}
  h2 {{ font-size: 1.1em; color: #333; margin: 20px 0 10px 0;
        border-bottom: 2px solid #ccc; padding-bottom: 4px; }}
  h2.dispo {{ color: #090; border-bottom-color: #090; }}
  h2.temp {{ color: #e80; border-bottom-color: #e80; }}
  h2.def {{ color: #c00; border-bottom-color: #c00; }}
  .stations {{ display: grid; gap: 10px; grid-template-columns: 1fr; }}
  @media (min-width: 600px) {{
    .stations {{ grid-template-columns: 1fr 1fr; }}
  }}
  .station {{ background: white; padding: 14px; border-radius: 10px;
              box-shadow: 0 1px 4px rgba(0,0,0,0.08);
              border-left: 4px solid #ccc; position: relative; }}
  .badge {{ position: absolute; top: 8px; right: 8px;
            font-size: 0.65em; color: white; padding: 2px 6px;
            border-radius: 4px; font-weight: bold; }}
  .ville {{ font-weight: bold; font-size: 1.05em; padding-right: 100px; }}
  .cp {{ font-weight: normal; color: #888; font-size: 0.85em; }}
  .adresse {{ color: #555; font-size: 0.9em; margin-top: 4px; }}
  .prix {{ color: #090; font-weight: bold; margin-top: 6px; font-size: 0.95em; }}
  .date {{ text-align: center; color: #888; font-size: 0.85em;
           margin: 20px 0; }}
  .vide {{ background: white; padding: 20px; text-align: center;
           border-radius: 10px; color: #666; font-size: 0.9em; }}
</style>
</head>
<body>
<header>
  <h1>Gazole TotalEnergies - Sarthe</h1>
  <div class="compteur">{len(dispo)} station(s) avec Gazole dispo</div>
</header>

<h2 class="dispo">✅ Gazole disponible ({len(dispo)})</h2>
<div class="stations">
{dispo_html if dispo_html else '<div class="vide">Aucune station avec Gazole disponible actuellement.</div>'}
</div>

{"<h2 class='temp'>⚠️ Rupture temporaire (" + str(len(temp)) + ")</h2><div class='stations'>" + temp_html + "</div>" if temp else ""}

{"<h2 class='def'>❌ Rupture definitive (" + str(len(definitive)) + ")</h2><div class='stations'>" + def_html + "</div>" if definitive else ""}

<div class="date">Derniere mise a jour : {date_heure}</div>
</body>
</html>'''

    with open(chemin, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Page HTML generee ({len(dispo)} dispo, {len(temp)} temp, {len(definitive)} def)")


def envoyer_recap(dispo, temp, definitive):
    total_dispo = len(dispo)
    lignes = [f"Stations avec Gazole disponible : {total_dispo}", ""]

    if dispo:
        lignes.append("TOP 10 stations (par ville) :")
        for s in dispo[:10]:
            lignes.append(f"  {s.get('ville', '?')} ({s.get('cp', '?')})")
        if len(dispo) > 10:
            lignes.append(f"  ... et {len(dispo) - 10} autres")

    if temp:
        lignes.append(f"\nEn rupture temporaire : {len(temp)}")

    message = "\n".join(lignes)
    titre = f"Recap Gazole : {total_dispo} stations disponibles"
    envoyer_notification(titre, message)


def main():
    print("=== Alerte Gazole (disponibilite) - Sarthe ===")
    paris = datetime.now(ZoneInfo("Europe/Paris"))
    print(f"Execution : {paris.strftime('%d/%m/%Y %H:%M')}\n")

    date_aujourdhui = paris.strftime("%Y-%m-%d")
    stocks_precedents = charger_json(FICHIER_STOCKS, {})
    recap_dernier = charger_json(FICHIER_RECAP, {})

    positions_total = recuperer_positions_total_sarthe()
    print(f"   {len(positions_total)} stations TotalEnergies")
    if not positions_total:
        return

    stations = recuperer_stations_sarthe()
    print(f"   {len(stations)} stations dans la Sarthe\n")

    stations_total = {}
    for station in stations:
        geom = station.get("geom") or {}
        lat = geom.get("lat")
        lon = geom.get("lon")
        if lat is None or lon is None:
            continue

        match = None
        for p in positions_total:
            if distance_metres(lat, lon, p["lat"], p["lon"]) < DISTANCE_MAX_METRES:
                match = p
                break
        if not match:
            continue

        sid = str(station.get("id", f"{lat}_{lon}"))
        etat = etat_gazole(station)
        prix = station.get("gazole_prix")

        stations_total[sid] = {
            "ville": station.get("ville", "?"),
            "adresse": station.get("adresse", "?"),
            "cp": station.get("cp", "?"),
            "etat": etat,
            "prix": float(prix) if prix is not None else None,
        }

    print(f"{len(stations_total)} stations Total en Sarthe\n")

    # Separation pour la page web
    dispo = [{"id": sid, **info} for sid, info in stations_total.items() if info["etat"] == "dispo"]
    temp = [{"id": sid, **info} for sid, info in stations_total.items() if info["etat"] == "temp"]
    definitive = [{"id": sid, **info} for sid, info in stations_total.items() if info["etat"] == "def"]

    print("-> Generation de la page web...")
    generer_page_html(dispo + temp + definitive)

    print("-> Generation des icones...")
    creer_icones_png()
    creer_manifest()

    # --- Detection des changements ---
    retours = []  # stations qui ont retrouve du gazole
    nouvelles_ruptures = []  # stations qui ont perdu le gazole

    for sid, info in stations_total.items():
        etat_avant = stocks_precedents.get(sid, {}).get("etat")
        etat_maintenant = info["etat"]

        # Retour en stock (etait temp ou def, maintenant dispo)
        if etat_avant in ("temp", "def") and etat_maintenant == "dispo":
            retours.append({
                "ville": info["ville"],
                "adresse": info["adresse"],
                "cp": info["cp"],
            })

        # Nouvelle rupture (etait dispo, maintenant temp ou def)
        if etat_avant == "dispo" and etat_maintenant in ("temp", "def"):
            nouvelles_ruptures.append({
                "ville": info["ville"],
                "adresse": info["adresse"],
                "cp": info["cp"],
                "type": etat_maintenant,
            })

    # --- Envoi des notifications ---
    if retours:
        lignes = []
        for r in retours[:20]:
            lignes.append(f"{r['ville']} ({r['cp']})\n   {r['adresse']}")
        titre = f"{len(retours)} station(s) ont du Gazole !"
        message = "\n\n".join(lignes)
        if len(retours) > 20:
            message += f"\n\n... et {len(retours) - 20} autres"
        print(f"\n{titre}\n{message}\n")
        envoyer_notification(titre, message)

    if nouvelles_ruptures:
        lignes = []
        for r in nouvelles_ruptures[:20]:
            type_txt = "temporaire" if r["type"] == "temp" else "definitive"
            lignes.append(f"{r['ville']} ({r['cp']}) - rupture {type_txt}")
        titre = f"{len(nouvelles_ruptures)} nouvelle(s) rupture(s)"
        message = "\n\n".join(lignes)
        if len(nouvelles_ruptures) > 20:
            message += f"\n\n... et {len(nouvelles_ruptures) - 20} autres"
        print(f"\n{titre}\n{message}\n")
        envoyer_notification(titre, message)

    # --- Recap quotidien ---
    derniere_date_recap = recap_dernier.get("date", "")
    if (paris.hour >= HEURE_RECAP and date_aujourdhui != derniere_date_recap):
        print(f"\n-> Envoi du recap quotidien (date : {date_aujourdhui})")
        envoyer_recap(dispo, temp, definitive)
        recap_dernier["date"] = date_aujourdhui
        recap_dernier["heure_envoi"] = paris.isoformat()
        sauvegarder_json(FICHIER_RECAP, recap_dernier)

    if not retours and not nouvelles_ruptures:
        print("\nAucun changement detecte.")

    # Sauvegarde de l'etat
    sauvegarder_json(FICHIER_STOCKS, stations_total)
    print(f"\nEtat sauvegarde : {len(stations_total)} stations")


if __name__ == "__main__":
    main()