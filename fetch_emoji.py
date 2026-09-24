import requests
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = "8906993504:AAHgiU2puxaOwY5h6Bn-IjnWW3piEb1EgsE"
r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getStickerSet?name=TgAndroidIcons")
data = r.json()
stickers = data.get("result", {}).get("stickers", [])
for i, s in enumerate(stickers[120:282]):
    emoji = s.get("emoji", "?")
    eid = s.get("custom_emoji_id", "?")
    print(f"[{i+120}] {emoji} -> {eid}")
