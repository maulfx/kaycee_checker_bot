"""
TikTok API module - Direct Raw Data & Stream Extractor.
Extracts official uncompressed master streams directly from TikTok ByteDance servers:
1. Primary: Direct Web Rehydration Scraper via curl_cffi Safari impersonation
2. Secondary: Direct yt-dlp metadata & stream protocol extractor
"""

import re
import json
import logging
import asyncio
from datetime import datetime
from curl_cffi import requests as curl_requests
import yt_dlp

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
    """Calculate quality string tier like 1080p60, 720p60, 720p30 based on short side resolution."""
    base_dim = min(width, height) if (width > 0 and height > 0) else max(width, height)
    if base_dim >= 2160:
        res = "2160p"
    elif base_dim >= 1440:
        res = "1440p"
    elif base_dim >= 1080:
        res = "1080p"
    elif base_dim >= 720:
        res = "720p"
    elif base_dim >= 540:
        res = f"{base_dim}p" if base_dim in (540, 576) else "576p"
    elif base_dim >= 480:
        res = "480p"
    elif base_dim >= 360:
        res = "360p"
    else:
        res = f"{base_dim}p" if base_dim > 0 else "720p"

    display_fps = int(round(fps)) if (fps and fps > 0) else 30
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
        seen_gears = set()

        # Parse real streams directly from raw_bitrate_info
        for b in raw_bitrate_info:
            w = int(b.get("PlayAddr", {}).get("Width", 0) or 0)
            h = int(b.get("PlayAddr", {}).get("Height", 0) or 0)
            br = int(b.get("Bitrate", 0) or 0)
            cd = b.get("CodecType", "")
            gear = b.get("GearName", "")
            
            # Detect FPS from gear name (e.g. normal_720_60, 720p60, gear_60, 60fps)
            # Must NOT match the '20' inside '720' or numbers inside resolutions
            gear_lower = gear.lower()
            detected_fps = 0
            fps_match = re.search(r'(?<!\d)(120|60|50|48|30|25|24|20)(?:fps)?(?!\d)', gear_lower)
            if fps_match:
                detected_fps = int(fps_match.group(1))

            raw_fps = b.get("BitrateFPS") or b.get("fps") or detected_fps or 0
            b_fps = int(round(raw_fps)) if raw_fps else 0
            b_data_size = int(b.get("PlayAddr", {}).get("DataSize", 0) or 0)
            url_list = b.get("PlayAddr", {}).get("UrlList", [])
            b_url = url_list[0] if url_list else ""

            seen_gears.add(gear)
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

        # ONLY add play_addr fallback IF raw_bitrate_info was completely empty!
        # Do not inject fake duplicate play_addr when raw_bitrate_info already has real streams.
        if play_url and not parsed_bitrate_info:
            parsed_bitrate_info.append({
                "gear": "play_addr",
                "codec": _clean_codec(codec or "h264"),
                "bitrate": bitrate,
                "width": width,
                "height": height,
                "fps": 0,
                "data_size": int((bitrate / 8.0) * duration) if (bitrate > 0 and duration > 0) else 0,
                "url": play_url
            })
            seen_gears.add("play_addr")

        # Sort streams descending by resolution (width * height), then fps, then bitrate
        sorted_streams = sorted(
            parsed_bitrate_info,
            key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("fps", 0), x.get("bitrate", 0)),
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

        # ─── VQ Score ───
        raw_vq = video.get("VQScore") or item.get("VQScore")
        vq_score = float(raw_vq) if raw_vq else 0.0

        # ─── Quality Tiers ───
        # Check all parsed streams for any detected FPS
        detected_stream_fps = 0
        for s in sorted_streams:
            s_fps = int(round(s.get("fps") or 0))
            if s_fps > detected_stream_fps:
                detected_stream_fps = s_fps

        # If 60fps (or higher) is detected on any stream, propagate to streams with 0 fps
        if detected_stream_fps > 0:
            for s in sorted_streams:
                if not s.get("fps") or s.get("fps") <= 0:
                    s["fps"] = detected_stream_fps

        # Separate streams into Browser vs Phone
        browser_streams = [s for s in sorted_streams if "normal" in s.get("gear", "").lower()]
        phone_streams = [s for s in sorted_streams if any(k in s.get("gear", "").lower() for k in ("lower", "lowest", "bytevc1"))]
        dual_streams = [s for s in sorted_streams if "adapt" in s.get("gear", "").lower() or "play_addr" in s.get("gear", "").lower()]

        for ds in dual_streams:
            browser_streams.append(ds)
            phone_streams.append(ds)

        if not browser_streams:
            browser_streams = sorted_streams
        if not phone_streams:
            phone_streams = sorted_streams

        # Browser Quality: from highest browser stream
        browser_streams.sort(
            key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("fps", 0), x.get("bitrate", 0)),
            reverse=True
        )
        best_b = browser_streams[0] if browser_streams else {}
        b_w = best_b.get("width") or max_width or width
        b_h = best_b.get("height") or max_height or height
        b_fps = int(round(best_b.get("fps") or 0)) or detected_stream_fps or 30
        browser_q = _calculate_quality_tier_string(b_w, b_h, b_fps, "browser")

        # Phone Quality: from highest phone stream (e.g. 720p60 if only up to 720p)
        phone_streams.sort(
            key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("fps", 0), x.get("bitrate", 0)),
            reverse=True
        )
        best_p = phone_streams[0] if phone_streams else {}
        p_w = best_p.get("width") or max_width or width
        p_h = best_p.get("height") or max_height or height
        p_fps = int(round(best_p.get("fps") or 0)) or detected_stream_fps or 30
        phone_q = _calculate_quality_tier_string(p_w, p_h, p_fps, "phone")

        overall_fps = max(detected_stream_fps, b_fps, p_fps)
        if overall_fps <= 0:
            overall_fps = 30

        # ─── Suggested Words / Search Tips ───
        raw_sw = item.get("suggestedWords", []) or item.get("suggested_words", []) or item.get("contents", []) or []
        suggested_words = []
        if isinstance(raw_sw, list):
            for sw in raw_sw:
                if isinstance(sw, str) and sw.strip():
                    suggested_words.append(sw.strip())
                elif isinstance(sw, dict):
                    w = sw.get("word") or sw.get("text") or sw.get("title") or ""
                    if w.strip():
                        suggested_words.append(w.strip())

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
            "download_addr": video.get("downloadAddr", ""),
            "wmplay_url": "",
            "cover_url": video.get("cover", ""),
            "origin_cover_url": video.get("originCover", ""),
            "width": max_width or width,
            "height": max_height or height,
            "fps": overall_fps,
            "size": 0,
            "hd_size": 0,
            "wm_size": 0,
            "bitrate_kbps": bitrate_kbps,
            "codec": _clean_codec(best_codec),
            "bitrate_info": sorted_streams,
            "browser_quality": browser_q,
            "phone_quality": phone_q,
            "vq_score": vq_score,
            "music_title": music_title,
            "music_author": music_author,
            "music_url": music_url,
            "music_is_original": True,
            "music_duration": 0,
            "suggested_words": suggested_words,
            "region": str(location).upper() if location else "ID",
            "source": _detect_source(max_width or width, max_height or height),
            "is_ad": bool(item.get("isAd", False)),
            "original_url": url,
        }
    except Exception as e:
        logger.warning(f"Engine 1 web scraper exception: {e}")
        return None


def _extract_tiktok_ytdlp_sync(url: str) -> dict | None:
    """
    Extract comprehensive TikTok video data and all adaptive quality tiers using yt-dlp.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'socket_timeout': 15,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            video_id = str(info.get("id", ""))
            title = info.get("title", "") or info.get("description", "")
            duration = int(info.get("duration", 0) or 0)
            create_time = int(info.get("timestamp", 0) or 0)
            formatted_date = (
                datetime.fromtimestamp(create_time).strftime("%d %B %Y, %H:%M:%S")
                if create_time else "Unknown"
            )
            author_username = info.get("uploader_id") or info.get("uploader", "Unknown")
            author_nickname = info.get("uploader", author_username)
            author_avatar = info.get("avatar", "")
            
            views = int(info.get("view_count", 0) or 0)
            likes = int(info.get("like_count", 0) or 0)
            comments = int(info.get("comment_count", 0) or 0)
            reposts = int(info.get("repost_count", 0) or 0)
            
            formats = info.get("formats", [])
            parsed_streams = []
            
            for f in formats:
                vcodec = f.get("vcodec")
                if vcodec == "none" or not vcodec:
                    continue
                w = int(f.get("width") or 0)
                h = int(f.get("height") or 0)
                fps = int(round(f.get("fps") or 30))
                tbr = f.get("tbr") or f.get("vbr") or 0
                br_kbps = int(tbr) if tbr > 0 else 0
                br_bps = br_kbps * 1000
                data_size = int(f.get("filesize") or f.get("filesize_approx") or 0)
                s_url = f.get("url", "")
                f_id = f.get("format_id", "")
                cleaned_codec = _clean_codec(vcodec)
                
                parsed_streams.append({
                    "gear": f_id or f"{max(w,h)}p",
                    "codec": cleaned_codec,
                    "bitrate": br_bps,
                    "width": w,
                    "height": h,
                    "fps": fps,
                    "data_size": data_size,
                    "url": s_url,
                })
            
            parsed_streams.sort(
                key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("fps", 0), x.get("bitrate", 0)),
                reverse=True
            )
            
            best_stream = parsed_streams[0] if parsed_streams else {}
            width = best_stream.get("width") or int(info.get("width", 0) or 0)
            height = best_stream.get("height") or int(info.get("height", 0) or 0)
            fps = best_stream.get("fps") or int(round(info.get("fps") or 30))
            bitrate_kbps = (best_stream.get("bitrate", 0) // 1000) if best_stream.get("bitrate") else int(info.get("tbr") or 0)
            codec = best_stream.get("codec") or _clean_codec(info.get("vcodec", "h264"))
            play_url = best_stream.get("url") or info.get("url", "")
            hdplay_url = play_url
            
            browser_q = _calculate_quality_tier_string(width, height, fps, "browser")
            phone_q = _calculate_quality_tier_string(width, height, fps, "phone")
            
            logger.info("Fetched TikTok video data via yt-dlp Engine")
            return {
                "id": video_id,
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
                "favorites": 0,
                "shares": reposts,
                "downloads": 0,
                "play_url": play_url,
                "hdplay_url": hdplay_url,
                "wmplay_url": "",
                "cover_url": info.get("thumbnail", ""),
                "origin_cover_url": info.get("thumbnail", ""),
                "width": width,
                "height": height,
                "fps": fps,
                "size": int(info.get("filesize") or info.get("filesize_approx") or 0),
                "hd_size": 0,
                "wm_size": 0,
                "bitrate_kbps": bitrate_kbps,
                "codec": codec,
                "bitrate_info": parsed_streams,
                "browser_quality": browser_q,
                "phone_quality": phone_q,
                "music_title": info.get("track") or f"original sound - {author_nickname}",
                "music_author": info.get("artist") or author_nickname,
                "music_url": "",
                "music_is_original": True,
                "music_duration": duration,
                "region": "ID",
                "source": _detect_source(width, height),
                "is_ad": False,
                "original_url": url,
            }
    except Exception as e:
        logger.warning(f"yt-dlp engine extraction failed: {e}")

async def fetch_tiktok_data(url: str) -> dict | None:
    """
    Fetch comprehensive TikTok video data directly without third-party proxy fallback engines.
    1. Primary: Direct Web Rehydration Scraper via curl_cffi Safari impersonation
    2. Secondary: Direct yt-dlp metadata extractor
    """
    # ─── Engine 1: Direct Web Rehydration Scraper ───────────────
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _scrape_tiktok_web_sync, url)
        if data and data.get("id"):
            return data
    except Exception as e:
        logger.warning(f"Direct web rehydration scraper exception: {e}")

    # ─── Engine 2: Direct yt-dlp Protocol Extractor ─────────────
    try:
        loop = asyncio.get_running_loop()
        ytdlp_data = await loop.run_in_executor(None, _extract_tiktok_ytdlp_sync, url)
        if ytdlp_data and ytdlp_data.get("id"):
            return ytdlp_data
    except Exception as e:
        logger.warning(f"Direct yt-dlp engine failed: {e}")

    logger.error("Could not fetch TikTok data using direct engines.")
    return None

