"""
Configuration module for TikTok Analyzer Bot.
Loads settings from environment variables and .env file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ─── Telegram Bot ─────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ─── TikTok API ───────────────────────────────────────────────
TIKWM_API_URL = "https://www.tikwm.com/api/"
TIKWM_API_TIMEOUT = 30  # seconds

# ─── FFprobe ──────────────────────────────────────────────────
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")

# ─── Temp Directory ───────────────────────────────────────────
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# ─── Region Flags ─────────────────────────────────────────────
REGION_FLAGS = {
    "ID": "🇮🇩", "JP": "🇯🇵", "US": "🇺🇸", "GB": "🇬🇧", "KR": "🇰🇷",
    "MY": "🇲🇾", "SG": "🇸🇬", "TH": "🇹🇭", "VN": "🇻🇳", "PH": "🇵🇭",
    "IN": "🇮🇳", "BR": "🇧🇷", "DE": "🇩🇪", "FR": "🇫🇷", "IT": "🇮🇹",
    "ES": "🇪🇸", "RU": "🇷🇺", "AU": "🇦🇺", "CA": "🇨🇦", "MX": "🇲🇽",
    "TW": "🇹🇼", "HK": "🇭🇰", "TR": "🇹🇷", "SA": "🇸🇦", "AE": "🇦🇪",
    "EG": "🇪🇬", "NG": "🇳🇬", "ZA": "🇿🇦", "AR": "🇦🇷", "CL": "🇨🇱",
    "CO": "🇨🇴", "PK": "🇵🇰", "BD": "🇧🇩", "NL": "🇳🇱", "PL": "🇵🇱",
    "SE": "🇸🇪", "NO": "🇳🇴", "FI": "🇫🇮", "DK": "🇩🇰", "NZ": "🇳🇿",
}

# ─── Region Names ─────────────────────────────────────────────
REGION_NAMES = {
    "ID": "Indonesia", "JP": "Japan", "US": "United States", "GB": "United Kingdom",
    "KR": "South Korea", "MY": "Malaysia", "SG": "Singapore", "TH": "Thailand",
    "VN": "Vietnam", "PH": "Philippines", "IN": "India", "BR": "Brazil",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain",
    "RU": "Russia", "AU": "Australia", "CA": "Canada", "MX": "Mexico",
    "TW": "Taiwan", "HK": "Hong Kong", "TR": "Turkey", "SA": "Saudi Arabia",
    "AE": "UAE", "EG": "Egypt", "NG": "Nigeria", "ZA": "South Africa",
    "AR": "Argentina", "CL": "Chile", "CO": "Colombia", "PK": "Pakistan",
    "BD": "Bangladesh", "NL": "Netherlands", "PL": "Poland", "SE": "Sweden",
    "NO": "Norway", "FI": "Finland", "DK": "Denmark", "NZ": "New Zealand",
}

# ─── Category Mapping (hashtag-based inference) ───────────────
CATEGORY_KEYWORDS = {
    "Gaming": ["game", "gaming", "gamer", "esport", "gameplay", "xbox", "playstation", "nintendo", "pc"],
    "Video Games": ["genshin", "valorant", "minecraft", "roblox", "fortnite", "codm", "mobilelegends", 
                    "pubg", "freefire", "honkaistarrail", "zenless", "wuwa", "hoyoverse", "hoyocreators"],
    "Music": ["music", "song", "singing", "vocal", "guitar", "piano", "beat", "melody", "cover", "remix"],
    "Dance": ["dance", "dancing", "choreography", "kpop", "kpopdance"],
    "Comedy": ["comedy", "funny", "humor", "meme", "joke", "lol", "fyp"],
    "Education": ["education", "belajar", "tutorial", "tips", "howto", "diy", "lifehack"],
    "Food": ["food", "cooking", "recipe", "masak", "kuliner", "mukbang", "asmr"],
    "Fashion": ["fashion", "ootd", "style", "outfit", "clothes", "beauty", "makeup", "skincare"],
    "Sports": ["sport", "fitness", "gym", "workout", "football", "basketball", "soccer"],
    "Travel": ["travel", "wanderlust", "explore", "trip", "vacation", "tourism"],
    "Art": ["art", "drawing", "painting", "illustration", "sketch", "digital", "edit", "genshinedit"],
    "Anime": ["anime", "manga", "otaku", "cosplay", "waifu", "weeb", "tsaritsa"],
    "Entertainment": ["entertainment", "viral", "trending", "foryou", "fyp", "foryoupage"],
    "Technology": ["tech", "technology", "coding", "programming", "developer", "ai", "gadget"],
    "Pets": ["pet", "cat", "dog", "kitten", "puppy", "animal", "kucing", "anjing"],
}
