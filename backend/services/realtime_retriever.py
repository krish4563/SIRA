# services/realtime_retriever.py

import logging
import os
from datetime import datetime

import feedparser
import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------
# GENERIC SAFE GET WRAPPER
# ------------------------------------------------------


def safe_get(url, timeout=10, headers=None, params=None):
    try:
        r = requests.get(url, timeout=timeout, headers=headers, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error("[REALTIME] Fetch failed for %s: %s", url, e)
        return None


# ------------------------------------------------------
# 1. CRYPTO — BTC & ETH (USING BINANCE)
# ------------------------------------------------------


def fetch_crypto() -> list[dict]:
    out = []

    # BTC (Binance)
    btc = safe_get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"},
    )
    if btc:
        out.append(
            {
                "title": "Live Bitcoin (BTC) Price",
                "url": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                "snippet": f"BTC/USDT: {btc['price']}",
                "provider": "binance",
            }
        )

    # ETH (Binance)
    eth = safe_get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "ETHUSDT"},
    )
    if eth:
        out.append(
            {
                "title": "Live Ethereum (ETH) Price",
                "url": "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
                "snippet": f"ETH/USDT: {eth['price']}",
                "provider": "binance",
            }
        )

    return out


# ------------------------------------------------------
# 2. NIFTY 50 INDEX
# ------------------------------------------------------


def fetch_nifty50() -> list[dict]:
    data = safe_get(
        "https://priceapi.moneycontrol.com/techCharts/indianMarket/stock/history",
        params={"symbol": "NIFTY 50", "resolution": "1"},
    )

    if not data:
        return []

    try:
        last_price = data["c"][-1]
        return [
            {
                "title": "Live Nifty 50 Index",
                "url": "https://www.nseindia.com",
                "snippet": f"Nifty50 latest price: {last_price}",
                "provider": "moneycontrol",
            }
        ]
    except (KeyError, IndexError):
        return []


# ------------------------------------------------------
# 3. FOREX — USD/INR
# ------------------------------------------------------


def fetch_forex() -> list[dict]:
    fx = safe_get(
        "https://api.exchangerate.host/latest",
        params={"base": "USD", "symbols": "INR"},
    )

    if not fx:
        return []

    try:
        rate = fx["rates"]["INR"]
        return [
            {
                "title": "USD/INR Forex Rate",
                "url": "https://api.exchangerate.host/latest",
                "snippet": f"USD → INR: {rate}",
                "provider": "exchangerate.host",
            }
        ]
    except KeyError:
        return []


# ------------------------------------------------------
# 4. GOLD (XAU/USD)
# ------------------------------------------------------


def fetch_gold() -> list[dict]:
    gold = safe_get("https://api.metals.live/v1/spot")
    if not gold:
        return []

    try:
        xau = gold[0]["price"]
        return [
            {
                "title": "Live Gold Price (XAU/USD)",
                "url": "https://metals.live",
                "snippet": f"Gold Spot Price (USD): {xau}",
                "provider": "metals.live",
            }
        ]
    except (KeyError, IndexError):
        return []


# ------------------------------------------------------
# WEATHER — OpenWeather
# ------------------------------------------------------

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def fetch_weather(city: str = "Pune") -> list[dict]:
    if not OPENWEATHER_API_KEY:
        # logger.warning("[REALTIME] OPENWEATHER_API_KEY missing.")
        return []

    data = safe_get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
    )

    if not data:
        return []

    try:
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        desc = data["weather"][0]["description"].title()

        return [
            {
                "title": f"Weather in {city}",
                "url": f"https://openweathermap.org/city/{data.get('id', '')}",
                "snippet": f"{desc}. Temp: {temp}°C, Feels like: {feels_like}°C, Humidity: {humidity}%",
                "provider": "openweather",
            }
        ]
    except KeyError:
        return []


# ------------------------------------------------------
# AQI (Pune) — WAQI Demo Token
# ------------------------------------------------------


def fetch_aqi() -> list[dict]:
    aqi = safe_get("https://api.waqi.info/feed/Pune/?token=demo")
    if not aqi or aqi.get("status") != "ok":
        return []

    try:
        return [
            {
                "title": "Live AQI (Pune)",
                "url": "https://waqi.info",
                "snippet": f"AQI: {aqi['data']['aqi']}",
                "provider": "waqi",
            }
        ]
    except KeyError:
        return []


# ------------------------------------------------------
# EARTHQUAKES — Last 1 hour
# ------------------------------------------------------


def fetch_earthquakes() -> list[dict]:
    eq = safe_get(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    )

    if not eq:
        return []

    out = []
    try:
        for e in eq["features"][:5]:
            mag = e["properties"]["mag"]
            place = e["properties"]["place"]

            out.append(
                {
                    "title": f"Earthquake — M{mag}",
                    "url": e["properties"]["url"],
                    "snippet": f"Magnitude {mag} near {place}",
                    "provider": "USGS",
                }
            )
    except KeyError:
        pass

    return out


# ------------------------------------------------------
# GOOGLE NEWS RSS
# ------------------------------------------------------


def fetch_trending_news() -> list[dict]:
    try:
        feed = feedparser.parse("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en")
    except Exception:
        return []

    out = []
    for entry in feed.entries[:5]:
        out.append(
            {
                "title": entry.title,
                "url": entry.link,
                "snippet": entry.summary[:200],
                "provider": "google-news",
            }
        )
    return out


# ------------------------------------------------------
# TWITTER / X TRENDS (India)
# ------------------------------------------------------

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")


def fetch_twitter_trends() -> list[dict]:
    if not TWITTER_BEARER_TOKEN:
        # logger.warning("[REALTIME] TWITTER_BEARER_TOKEN missing.")
        return []

    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
    params = {"id": "23424848"}  # India

    data = safe_get(
        "https://api.twitter.com/1.1/trends/place.json",
        headers=headers,
        params=params,
    )

    if not data or not isinstance(data, list):
        return []

    try:
        trends = data[0].get("trends", [])[:5]
        out = []
        for t in trends:
            out.append(
                {
                    "title": f"Twitter Trend: {t.get('name')}",
                    "url": t.get("url", ""),
                    "snippet": f"Tweet Volume: {t.get('tweet_volume')}",
                    "provider": "twitter",
                }
            )
        return out
    except IndexError:
        return []


# ------------------------------------------------------
# MASTER DISPATCHER
# ------------------------------------------------------


def fetch_realtime(topic: str) -> list[dict]:
    """
    Decides which real-time API to call based on keywords.
    Returns [] if no keyword matches (Fix for Bitcoin-everywhere bug).
    """
    t = topic.lower()

    if any(x in t for x in ["btc", "eth", "crypto", "bitcoin", "ethereum"]):
        return fetch_crypto()

    if any(x in t for x in ["nifty", "sensex", "index", "stocks"]):
        return fetch_nifty50()

    if any(x in t for x in ["forex", "usd", "inr", "currency"]):
        return fetch_forex()

    if any(x in t for x in ["gold", "xau"]):
        return fetch_gold()

    if any(x in t for x in ["weather", "temperature", "rain", "climate"]):
        return fetch_weather("Pune")

    if "aqi" in t:
        return fetch_aqi()

    if any(x in t for x in ["earthquake", "seismic"]):
        return fetch_earthquakes()

    if any(x in t for x in ["news", "headlines", "trending"]):
        return fetch_trending_news()

    if any(x in t for x in ["twitter", "trend", "x.com", "hashtags"]):
        return fetch_twitter_trends()

    # ---------------------------------------------------
    # 🚨 CRITICAL FIX: RETURN EMPTY LIST INSTEAD OF CRYPTO
    # ---------------------------------------------------
    return []