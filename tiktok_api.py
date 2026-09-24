"""
TikTok API module - Multi-Engine Data Extractor.
Attempts data fetching using multiple provider engines:
1. Engine 1: Direct Web Rehydration Scraper via curl_cffi (Full stats, region, resolution, bitrate, audio)
2. Engine 2: TikWM API via HTTP / fallback
3. Engine 3: TikTok oEmbed + SaveTik / SSSTik fallback scraper
"""

import re
import json
import httpx
import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from config import TIKWM_API_URL, TIKWM_API_TIMEOUT

logger = logging.getLogger(__name__)

# Supported TikTok URL patterns
TIKTOK_URL_PATTERNS = [
    re.compile(r'https?://(?:www\.)?tiktok\.com/@[\w.]+/video/(\d+)'),
    re.compile(r'https?://(?:vm|vt)\.tiktok\.com/([\w]+)'),
    re.compile(r'https?://(?:www\.)?tiktok\.com/t/([\w]+)'),
    re.compile(r'https?://(?:www\.)?tiktok\.com/@[\w.]+/photo/(\d+)'),
]


def extract_tiktok_url(text: str) -> str | None:
    """Extract the first TikTok URL from text."""
    pattern = re.compile(
        r'https?://(?:(?:www|vm|vt)\.)?tiktok\.com/[^\s<>\"\']+'
    )
    match = pattern.search(text)
    return match.group(0) if match else None


def _parse_hashtags(title: str) -> list[str]:
    """Extract hashtags from video title/description."""
    return re.findall(r'#(\w+)', title or '')


def _detect_source(width: int, height: int) -> str:
    """Detect upload source (Desktop/Phone/Browser)."""
    if width == 0 or height == 0:
        return "Desktop"
    if width == 1174 and height == 1080:
        return "Desktop"
    if width > height:
        return "Browser"
    return "Desktop"


def _clean_codec(codec: str) -> str:
    c = codec.lower()
    if "h265" in c or "hevc" in c or "hvc1" in c or "bytevc1" in c:
        return "hevc"
    if "h264" in c or "avc" in c:
        return "h264"
    if "av1" in c or "av01" in c:
        return "av1"
    return codec if codec else "h264"


def _calculate_quality_tier_string(width: int, height: int, fps: int = 30, device: str = "phone") -> str:
    """Calculate quality string tier like 1080p30, 720p30."""
    max_dim = max(width, height)
    if max_dim >= 2160:
        res = "2160p" if device == "phone" else "1080p"
    elif max_dim >= 1440:
        res = "1440p" if device == "phone" else "1080p"
    elif max_dim >= 1080:
        res = "1080p" if device == "phone" else "720p"
    elif max_dim >= 720:
        res = "720p"
    elif max_dim >= 480:
        res = "480p"
    elif max_dim >= 360:
        res = "360p"
    else:
        res = f"{max_dim}p" if max_dim > 0 else "720p"

    display_fps = 60 if (device == "phone" and max_dim >= 1080) else 30
    return f"{res}{display_fps}"


def _scrape_tiktok_web_sync(url: str) -> dict | None:
    """
    Synchronous scraper using curl_cffi Safari impersonation to extract 
    __UNIVERSAL_DATA_FOR_REHYDRATION__ from TikTok web page.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        r = curl_requests.get(url, impersonate="safari17_0", headers=headers, timeout=15)
        if r.status_code != 200 or len(r.text) < 1000:
            logger.warning(f"Engine 1 web scrape returned status {r.status_code}, len {len(r.text)}")
            return None
        
        m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m:
            logger.warning("Engine 1 could not find __UNIVERSAL_DATA_FOR_REHYDRATION__ script tag")
            return None

        jdata = json.loads(m.group(1))
        scope = jdata.get("__DEFAULT_SCOPE__", {})
        app_ctx = scope.get("webapp.app-context", {})
        biz_ctx = scope.get("webapp.biz-context", {})
        video_detail = scope.get("webapp.video-detail", {})
        item = video_detail.get("itemInfo", {}).get("itemStruct", {})

        if not item:
            logger.warning("Engine 1: itemStruct was empty in rehydration scope")
            return None

        # ─── Statistics ───
        stats = item.get("statsV2") or item.get("stats") or {}
        views = int(stats.get("playCount", 0) or 0)
        likes = int(stats.get("diggCount", 0) or 0)
        comments = int(stats.get("commentCount", 0) or 0)
        favorites = int(stats.get("collectCount", 0) or 0)
        shares = int(stats.get("shareCount", 0) or 0)
        downloads = int(stats.get("downloadCount", 0) or stats.get("download_count", 0) or stats.get("saveCount", 0) or item.get("downloadCount", 0) or 0)

        # ─── Author ───
        author = item.get("author", {})
        author_username = author.get("uniqueId", "")
        author_nickname = author.get("nickname", author_username)
        author_avatar = author.get("avatarThumb", "")

        # ─── Video & Bitrate Tiers ───
        video = item.get("video", {})
        width = int(video.get("width", 0) or 0)
        height = int(video.get("height", 0) or 0)
        duration = int(video.get("duration", 0) or 0)
        bitrate = int(video.get("bitrate", 0) or 0)
        codec = video.get("codecType", "h264")

        raw_bitrate_info = video.get("bitrateInfo", [])
        parsed_bitrate_info = []

        max_width, max_height = width, height
        max_bitrate = bitrate
        best_codec = codec
        play_url = video.get("playAddr", "")
        hdplay_url = ""

        # First add default play_addr if available
        if play_url and bitrate > 0:
            parsed_bitrate_info.append({
                "gear": "play_addr",
                "codec": _clean_codec(codec),
                "bitrate": bitrate,
                "width": width,
                "height": height,
                "fps": 30,
                "data_size": 0,
                "url": play_url
            })

        for b in raw_bitrate_info:
            w = int(b.get("PlayAddr", {}).get("Width", 0) or 0)
            h = int(b.get("PlayAddr", {}).get("Height", 0) or 0)
            br = int(b.get("Bitrate", 0) or 0)
            cd = b.get("CodecType", "")
            gear = b.get("GearName", "")
            b_fps = int(b.get("BitrateFPS", 30) or 30)
            b_data_size = int(b.get("PlayAddr", {}).get("DataSize", 0) or 0)
            url_list = b.get("PlayAddr", {}).get("UrlList", [])
            b_url = url_list[0] if url_list else ""

            parsed_bitrate_info.append({
                "gear": gear,
                "codec": _clean_codec(cd),
                "bitrate": br,
                "width": w,
                "height": h,
                "fps": b_fps,
                "data_size": b_data_size,
                "url": b_url
            })

            if w * h > max_width * max_height:
                max_width, max_height = w, h
            if br > max_bitrate:
                max_bitrate = br
            if "h265" in cd or "hevc" in cd or "hvc1" in cd:
                best_codec = cd
            if "1080" in gear or w >= 1080 or h >= 1080:
                if b_url:
                    hdplay_url = b_url

        # Sort streams descending by resolution (width * height) and bitrate so highest quality is at the top
        sorted_streams = sorted(
            parsed_bitrate_info,
            key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("bitrate", 0)),
            reverse=True
        )

        if not play_url and sorted_streams:
            play_url = sorted_streams[0].get("url", "")
        if not hdplay_url:
            hdplay_url = play_url

        # ─── Region ───
        location = (
            item.get("locationCreated") or 
            item.get("region") or 
            biz_ctx.get("vregion") or 
            app_ctx.get("region") or 
            "ID"
        )

        # ─── Creation Time ───
        create_time = int(item.get("createTime", 0) or 0)
        formatted_date = (
            datetime.fromtimestamp(create_time).strftime("%d %B %Y, %H:%M:%S")
            if create_time else "Unknown"
        )

        # ─── Music ───
        music = item.get("music", {})
        music_title = music.get("title", f"original sound - {author_nickname}")
        music_author = music.get("authorName", author_nickname)
        music_url = music.get("playUrl", "")

        title = item.get("desc", "")
        bitrate_kbps = max_bitrate // 1000 if max_bitrate > 0 else (bitrate // 1000 if bitrate > 0 else 0)

        # ─── Quality Tiers ───
        browser_q = _calculate_quality_tier_string(max_width or width, max_height or height, 30, "browser")
        phone_q = _calculate_quality_tier_string(max_width or width, max_height or height, 60 if max_height >= 1080 or max_width >= 1080 else 30, "phone")

        logger.info("Successfully fetched video data via Engine 1 (Direct Web Rehydration Scraper)")
        return {
            "id": str(item.get("id", "")),
            "title": title,
            "hashtags": _parse_hashtags(title),
            "duration": duration,
            "create_time": create_time,
            "formatted_date": formatted_date,
            "author_username": author_username,
            "author_nickname": author_nickname,
            "author_avatar": author_avatar,
            "views": views,
            "likes": likes,
            "comments": comments,
            "favorites": favorites,
            "shares": shares,
            "downloads": downloads,
            "play_url": play_url,
            "hdplay_url": hdplay_url,
            "wmplay_url": "",
            "cover_url": video.get("cover", ""),
            "origin_cover_url": video.get("originCover", ""),
            "width": max_width or width,
            "height": max_height or height,
            "size": 0,
            "hd_size": 0,
            "wm_size": 0,
            "bitrate_kbps": bitrate_kbps,
            "codec": _clean_codec(best_codec),
            "bitrate_info": sorted_streams,
            "browser_quality": browser_q,
            "phone_quality": phone_q,
            "music_title": music_title,
            "music_author": music_author,
            "music_url": music_url,
            "music_is_original": True,
            "music_duration": 0,
            "region": str(location).upper() if location else "ID",
            "source": _detect_source(max_width or width, max_height or height),
            "is_ad": bool(item.get("isAd", False)),
            "original_url": url,
        }

    except Exception as e:
        logger.warning(f"Engine 1 web scraper exception: {e}")
        return None


async def fetch_tiktok_data(url: str) -> dict | None:
    """
    Fetch comprehensive TikTok video data using multi-engine fallback strategy.
    """
    # ─── Engine 1: Direct Web Rehydration Scraper ───────────────
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _scrape_tiktok_web_sync, url)
        if data and data.get("id"):
            return data
    except Exception as e:
        logger.warning(f"Engine 1 execution failed: {e}")

    # ─── Engine 2: TikWM API ─────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=TIKWM_API_TIMEOUT, follow_redirects=True) as client:
            params = {"url": url, "count": 12, "cursor": 0, "web": 1, "hd": 1}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            response = await client.post(TIKWM_API_URL, data=params, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0 and result.get("data"):
                    data = result.get("data", {})
                    author = data.get("author", {})
                    music_info = data.get("music_info", {})
                    create_time = data.get("create_time", 0)
                    formatted_date = (
                        datetime.fromtimestamp(create_time).strftime("%d %B %Y, %H:%M:%S")
                        if create_time else "Unknown"
                    )
                    w = data.get("width", 0)
                    h = data.get("height", 0)
                    logger.info("Fetched video data via Engine 2 (TikWM)")
                    return {
                        "id": str(data.get("id", "")),
                        "title": data.get("title", ""),
                        "hashtags": _parse_hashtags(data.get("title", "")),
                        "duration": data.get("duration", 0),
                        "create_time": create_time,
                        "formatted_date": formatted_date,
                        "author_username": author.get("unique_id", ""),
                        "author_nickname": author.get("nickname", ""),
                        "author_avatar": author.get("avatar", ""),
                        "views": data.get("play_count", 0),
                        "likes": data.get("digg_count", 0),
                        "comments": data.get("comment_count", 0),
                        "favorites": data.get("collect_count", 0),
                        "shares": data.get("share_count", 0),
                        "downloads": data.get("download_count", 0),
                        "play_url": data.get("play", ""),
                        "hdplay_url": data.get("hdplay", ""),
                        "wmplay_url": data.get("wmplay", ""),
                        "cover_url": data.get("cover", ""),
                        "origin_cover_url": data.get("origin_cover", ""),
                        "width": w,
                        "height": h,
                        "size": data.get("size", 0),
                        "hd_size": data.get("hd_size", 0),
                        "wm_size": data.get("wm_size", 0),
                        "bitrate_kbps": 0,
                        "codec": "h264",
                        "bitrate_info": [],
                        "browser_quality": _calculate_quality_tier_string(w, h, 30, "browser"),
                        "phone_quality": _calculate_quality_tier_string(w, h, 60 if h >= 1080 or w >= 1080 else 30, "phone"),
                        "music_title": music_info.get("title", ""),
                        "music_author": music_info.get("author", ""),
                        "music_url": music_info.get("play", ""),
                        "music_is_original": music_info.get("original", False),
                        "music_duration": music_info.get("duration", 0),
                        "region": str(data.get("region", "ID")).upper(),
                        "source": _detect_source(w, h),
                        "is_ad": data.get("is_ad", False),
                        "original_url": url,
                    }
    except Exception as e:
        logger.warning(f"Engine 2 (TikWM) failed: {e}")

    # ─── Engine 3: Fallback (TikTok oEmbed + SaveTik Scraper) ─────
    logger.info("Attempting Engine 3 (TikTok oEmbed + SaveTik Scraper)...")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            id_match = re.search(r'/video/(\d+)', url) or re.search(r'/photo/(\d+)', url)
            video_id = id_match.group(1) if id_match else ""
            
            oembed_data = {}
            try:
                import urllib.parse
                enc_url = urllib.parse.quote(url, safe="")
                r_oembed = await client.get(f"https://www.tiktok.com/oembed?url={enc_url}", headers=headers)
                if r_oembed.status_code == 200:
                    oembed_data = r_oembed.json()
            except Exception as e:
                logger.warning(f"TikTok oEmbed failed: {e}")
            
            play_url = ""
            hdplay_url = ""
            music_url = ""
            avatar_url = ""
            
            try:
                r_savetik = await client.post("https://savetik.co/api/ajaxSearch", data={"q": url}, headers=headers)
                if r_savetik.status_code == 200:
                    res_json = r_savetik.json()
                    html_content = res_json.get("data", "")
                    soup = BeautifulSoup(html_content, "html.parser")
                    for a in soup.find_all("a", href=True):
                        txt = a.get_text(strip=True).lower()
                        href = a["href"]
                        if "mp4 hd" in txt:
                            hdplay_url = href
                        elif "mp4" in txt and not play_url:
                            play_url = href
                        elif "mp3" in txt:
                            music_url = href
            except Exception as e:
                logger.warning(f"SaveTik failed: {e}")

            if not play_url and not hdplay_url and not oembed_data:
                logger.error("All TikTok API engines failed to retrieve video data")
                return None
            
            title = oembed_data.get("title", "")
            author_username = oembed_data.get("author_unique_id") or (url.split("@")[1].split("/")[0] if "@" in url else "Unknown")
            author_nickname = oembed_data.get("author_name") or author_username
            cover_url = oembed_data.get("thumbnail_url", "")
            w = int(oembed_data.get("thumbnail_width", 0) or 0)
            h = int(oembed_data.get("thumbnail_height", 0) or 0)
            music_title = f"original sound - {author_nickname}"
            
            logger.info("Fetched TikTok video data via Engine 3 (Fallback)")
            return {
                "id": video_id or str(oembed_data.get("embed_product_id", "Unknown")),
                "title": title,
                "hashtags": _parse_hashtags(title),
                "duration": 0,
                "create_time": 0,
                "formatted_date": datetime.now().strftime("%d %B %Y, %H:%M:%S"),
                "author_username": author_username,
                "author_nickname": author_nickname,
                "author_avatar": avatar_url,
                "views": 0,
                "likes": 0,
                "comments": 0,
                "favorites": 0,
                "shares": 0,
                "downloads": 0,
                "play_url": play_url or hdplay_url,
                "hdplay_url": hdplay_url or play_url,
                "wmplay_url": "",
                "cover_url": cover_url,
                "origin_cover_url": cover_url,
                "width": w,
                "height": h,
                "size": 0,
                "hd_size": 0,
                "wm_size": 0,
                "bitrate_kbps": 0,
                "codec": "h264",
                "bitrate_info": [],
                "browser_quality": _calculate_quality_tier_string(w, h, 30, "browser"),
                "phone_quality": _calculate_quality_tier_string(w, h, 30, "phone"),
                "music_title": music_title,
                "music_author": author_nickname,
                "music_url": music_url,
                "music_is_original": True,
                "music_duration": 0,
                "region": "ID",
                "source": _detect_source(w, h),
                "is_ad": False,
                "original_url": url,
            }
            
    except Exception as e:
        logger.error(f"Engine 3 failed: {e}", exc_info=True)
        return None
