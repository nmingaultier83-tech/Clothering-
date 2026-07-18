"""
Outfit Finder - Trouve des références pas chères à partir d'une photo d'outfit
et génère un moodboard.

Lancer avec : streamlit run app.py
"""

import base64
import io
import json
import os

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Outfit Finder", page_icon="👗", layout="wide")

MOODBOARD_WIDTH = 1200
THUMB_SIZE = (260, 260)
BG_COLOR = (245, 245, 245)


# ---------------------------------------------------------------------------
# ETAPE 1 : Identification des vêtements dans la photo (via Claude vision)
# ---------------------------------------------------------------------------
def identify_garments(image_bytes: bytes, anthropic_api_key: str) -> list[dict]:
    """
    Envoie la photo à l'API Claude (vision) et récupère une liste de
    vêtements identifiés avec une description utile pour la recherche.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Regarde cette photo d'un outfit. Identifie chaque pièce vestimentaire "
        "visible (haut, bas, chaussures, sac, accessoires, etc). "
        "Réponds UNIQUEMENT avec un JSON valide, sans texte autour, sous la forme :\n"
        '[{"item": "nom court", "search_query": "description précise pour '
        'un moteur de recherche shopping (couleur, matière, coupe, style)"}]'
    )

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# ETAPE 2 : Recherche de produits pas chers (via SerpAPI - Google Shopping)
# ---------------------------------------------------------------------------
def search_cheap_products(query: str, serpapi_key: str, max_results: int = 3) -> list[dict]:
    """
    Cherche des produits correspondant à la requête, triés par prix croissant.
    Retourne une liste de dicts : title, price, thumbnail, link
    """
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google_shopping",
            "q": query,
            "api_key": serpapi_key,
            "hl": "fr",
            "gl": "fr",
        },
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("shopping_results", [])

    def price_value(item):
        raw = item.get("extracted_price")
        return raw if raw is not None else float("inf")

    results_sorted = sorted(results, key=price_value)
    products = []
    for item in results_sorted[:max_results]:
        products.append(
            {
                "title": item.get("title", "Sans titre"),
                "price": item.get("price", "Prix inconnu"),
                "thumbnail": item.get("thumbnail"),
                "link": item.get("link") or item.get("product_link", "#"),
                "source": item.get("source", ""),
            }
        )
    return products


# ---------------------------------------------------------------------------
# ETAPE 3 : Génération du moodboard (Pillow)
# ---------------------------------------------------------------------------
def build_moodboard(original_image: Image.Image, items_with_products: list[dict]) -> Image.Image:
    """
    Compose une planche : photo originale à gauche, grille de produits trouvés
    à droite avec titre + prix.
    """
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
        font_bold = font

    all_products = [p for it in items_with_products for p in it["products"]]
    n_products = max(len(all_products), 1)
    cols = 3
    rows = (n_products + cols - 1) // cols

    orig_w = 420
    orig_h = int(original_image.height * (orig_w / original_image.width))
    original_resized = original_image.resize((orig_w, orig_h))

    grid_w = cols * (THUMB_SIZE[0] + 20) + 20
    grid_h = rows * (THUMB_SIZE[1] + 60) + 20

    canvas_w = orig_w + grid_w + 60
    canvas_h = max(orig_h + 60, grid_h) + 80
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.text((20, 15), "Ton outfit", font=font_bold, fill=(20, 20, 20))
    canvas.paste(original_resized, (20, 50))

    grid_x0 = orig_w + 40
    draw.text((grid_x0, 15), "Références pas chères", font=font_bold, fill=(20, 20, 20))

    x, y = grid_x0, 50
    for i, product in enumerate(all_products):
        col = i % cols
        if col == 0 and i != 0:
            y += THUMB_SIZE[1] + 60
        x = grid_x0 + col * (THUMB_SIZE[0] + 20)

        try:
            thumb_resp = requests.get(product["thumbnail"], timeout=15)
            thumb = Image.open(io.BytesIO(thumb_resp.content)).convert("RGB")
            thumb.thumbnail(THUMB_SIZE)
        except Exception
