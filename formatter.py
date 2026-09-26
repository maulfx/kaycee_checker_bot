"""
Message Formatter module.
Formats video analysis data into clean, modern Telegram messages
matching the user's reference design with exact icons, positions, expandable quality blockquote,
and blue highlighted stats/links.
"""

import html
import re
from datetime import datetime
from config import REGION_FLAGS, REGION_NAMES, CATEGORY_KEYWORDS
from emoji_icons import ce


def _infer_categories(hashtags: list[str]) -> list[str]:
    """
    Infer video categories from hashtags.
    Returns a list of matched category names.
    """
    categories = []
    hashtags_lower = [h.lower() for h in hashtags]
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            for hashtag in hashtags_lower:
                if keyword in hashtag:
                    if category not in categories:
                        categories.append(category)
                    break
    
    if not categories:
        categories.append("Entertainment")
    
    return categories


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to MM:SS format."""
    if seconds <= 0:
        return "0:00"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _format_number(n: int) -> str:
    """Format numbers with thousand separators (e.g. 198,591)."""
    return f"{n:,}"


def _detect_shadow_ban(data: dict) -> str:
    """
    Simple shadow ban detection heuristic.
    Checks indicators like low views relative to time posted.
    """
    views = data.get("views", 0)
    likes = data.get("likes", 0)
    comments = data.get("comments", 0)
    shares = data.get("shares", 0)
    create_time = data.get("create_time", 0)
    
    if create_time == 0:
        return "No"
    
    age_hours = (datetime.now().timestamp() - create_time) / 3600
    
    if age_hours > 48 and views == 0:
        return "Possible"
    
    if age_hours > 72 and views > 0:
        engagement_rate = (likes + comments + shares) / views
        if engagement_rate < 0.001 and views < 100:
            return "Possible"
    
    return "No"


def _format_bitrate_str(bps: int) -> str:
    """Format bitrate into human-readable string (e.g. 2.0 MBps or 451.0 KBps)."""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} MBps"
    kbps = round(bps / 1000)
    return f"{kbps} KBps"


def _format_file_size_str(bytes_val: float) -> str:
    """Format file size into human-readable string (e.g. 4.5 MB or 600.4 KB)."""
    if bytes_val <= 0:
        return "Unknown"
    if bytes_val >= 1048576:
        return f"{bytes_val / 1048576:.1f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{int(bytes_val)} B"


def _get_stream_resolution_label(w: int, h: int, fps: int, gear: str = "") -> str:
    """Format stream resolution label like 1080p60, 720p60, 576p30."""
    base_dim = min(w, h) if (w > 0 and h > 0) else max(w, h)
    if "1080" in gear or base_dim >= 1080:
        res = "1080p"
    elif "720" in gear or base_dim >= 720:
        res = "720p"
    elif "540" in gear or base_dim >= 540:
        res = f"{base_dim}p" if base_dim > 0 else "576p"
    elif "480" in gear or base_dim >= 480:
        res = "480p"
    elif "360" in gear or base_dim >= 360:
        res = "360p"
    else:
        res = f"{base_dim}p" if base_dim > 0 else "720p"
    
    stream_fps = fps if fps > 0 else 30
    return f"{res}{stream_fps}"


def _get_gear_device_icon(gear: str) -> str:
    """Determine device icon (Phone / Browser / Both) for stream gear."""
    g = gear.lower()
    if "normal" in g:
        return ce("globe", "🌐")
    elif "lower" in g or "lowest" in g or "bytevc1" in g:
        return ce("phone", "📱")
    elif "adapt" in g:
        return f"{ce('globe', '🌐')} {ce('phone', '📱')}"
    elif "play_addr" in g:
        return f"{ce('globe', '🌐')} {ce('phone', '📱')}"
    return ce("phone", "📱")


def format_analysis_message(
    tiktok_data: dict,
    video_quality: dict,
    vq_score: float,
) -> str:
    """
    Format all analysis data into the exact Telegram HTML message layout matching the user's screenshot.
    """
    
    # ─── Extract data ─────────────────────────────────────────
    raw_username = tiktok_data.get("author_username", "Unknown")
    raw_nickname = tiktok_data.get("author_nickname", raw_username)
    raw_title = tiktok_data.get("title", "")
    raw_formatted_date = tiktok_data.get("formatted_date", "Unknown")
    duration = tiktok_data.get("duration", 0)
    raw_video_id = tiktok_data.get("id", "Unknown")
    region_code = tiktok_data.get("region", "")
    raw_source = tiktok_data.get("source", "Browser")
    hashtags = tiktok_data.get("hashtags", [])
    video_url = tiktok_data.get("original_url") or f"https://www.tiktok.com/@{raw_username}/video/{raw_video_id}"
    
    # Escape HTML special characters
    author_name = html.escape(str(raw_nickname or raw_username))
    title = html.escape(str(raw_title))
    formatted_date = html.escape(str(raw_formatted_date))
    video_id = html.escape(str(raw_video_id))
    source = html.escape(str(raw_source))
    
    # Music info
    music_title = html.escape(str(tiktok_data.get("music_title", f"original sound - {raw_username}")))
    
    # Stats
    views = tiktok_data.get("views", 0)
    likes = tiktok_data.get("likes", 0)
    comments = tiktok_data.get("comments", 0)
    favorites = tiktok_data.get("favorites", 0)
    shares = tiktok_data.get("shares", 0)
    downloads = tiktok_data.get("downloads", 0)
    
    # Quality
    orig_width = tiktok_data.get("width", 0) or video_quality.get("width", 0)
    orig_height = tiktok_data.get("height", 0) or video_quality.get("height", 0)
    codec = video_quality.get("codec") or tiktok_data.get("codec", "h264")
    bitrate_kbps = video_quality.get("bitrate_kbps") or tiktok_data.get("bitrate_kbps", 0)
    fps = video_quality.get("fps", 30)
    file_size = video_quality.get("file_size_bytes") or tiktok_data.get("size", 0)
    browser_q = tiktok_data.get("browser_quality") or video_quality.get("browser_quality", "1080p60")
    phone_q = tiktok_data.get("phone_quality") or video_quality.get("phone_quality", "1080p60")
    
    bitrate_info = tiktok_data.get("bitrate_info", [])
    
    # Region
    region_flag = REGION_FLAGS.get(region_code, "🌐")
    region_name = REGION_NAMES.get(region_code, region_code or "Unknown")
    
    # Shadow ban check
    shadow_ban = _detect_shadow_ban(tiktok_data)
    
    # Categories from hashtags
    categories = _infer_categories(hashtags)

    # VQ Score: Use exact score from TikTok if available
    raw_vq = float(tiktok_data.get("vq_score") or vq_score or 0.0)
    if raw_vq > 0:
        vq_display = f"{raw_vq:.2f}"
    else:
        calc_q = float(video_quality.get("vq_score") or 70.0)
        vq_display = f"{calc_q:.2f}"

    # ─── Build message ────────────────────────────────────────
    lines = []
    
    # Header: 🎵 skyrul  🗓️ 31 August 2026, 05:10:55
    lines.append(f"{ce('music_note', '🎵')} <b>{author_name}</b>  {ce('calendar', '🗓️')} {formatted_date}")
    
    # Title in Blockquote (Italic)
    if title:
        lines.append(f"<blockquote><i>{title}</i></blockquote>")
    
    # Audio Track
    dur_str = f" • {_format_duration(duration)}" if duration > 0 else ""
    lines.append(f"{ce('music_notes', '🎶')} {music_title}{dur_str}")
    lines.append("")
    
    # 📈 Statistics
    lines.append(f"{ce('chart_up', '📈')} <b>Statistics</b>")
    lines.append(f"• {ce('eye', '👀')} <code>{_format_number(views)}</code> Views")
    lines.append(f"• {ce('heart', '❤️')} <code>{_format_number(likes)}</code> Likes")
    lines.append(f"• {ce('comment', '💬')} <code>{_format_number(comments)}</code> Comments")
    lines.append(f"• {ce('star', '⭐')} <code>{_format_number(favorites)}</code> Favorites")
    lines.append(f"• {ce('forward', '🚀')} <code>{_format_number(shares)}</code> Shares")
    lines.append(f"• {ce('download', '📥')} <code>{_format_number(downloads)}</code> Downloads")
    lines.append("")
    
    # ℹ️ Information
    lines.append(f"{ce('info', 'ℹ️')} <b>Information</b>")
    lines.append(f"• {ce('tag', '🆔')} ID | <code>{video_id}</code>")
    lines.append(f"• {ce('tv', '💻')} Source | <code>{source}</code>")
    lines.append(f"• {ce('location', '📍')} Region | {region_flag} <b>{region_name}</b>")
    lines.append(f"• {ce('shield', '🛡️')} Shadow ban | <code>{shadow_ban}</code>")
    lines.append("")
    
    # 🎬 Quality
    lines.append(f"{ce('video', '🎬')} <b>Quality</b>")
    lines.append(f"• {ce('globe', '🌐')} Browser | <code>{browser_q}</code>")
    lines.append(f"• {ce('phone', '📱')} Phone | <code>{phone_q}</code>")
    
    # Expandable Stream Profiles blockquote (padded with invisible space for 100% full-width bubble match)
    FULL_WIDTH_PAD = "\u2800" * 28
    quote_lines = []
    if bitrate_info:
        for idx, b in enumerate(bitrate_info):
            gear = b.get("gear", "play_addr")
            b_codec = b.get("codec", "hevc")
            b_bitrate = b.get("bitrate", 0)
            b_w = b.get("width", 0)
            b_h = b.get("height", 0)
            b_fps = b.get("fps", 60)
            b_data_size = float(b.get("data_size", 0) or 0)
            
            if b_data_size <= 0 and duration > 0 and b_bitrate > 0:
                b_size_bytes = (b_bitrate / 8.0) * duration
            else:
                b_size_bytes = b_data_size

            size_str = _format_file_size_str(b_size_bytes)
            bitrate_str = _format_bitrate_str(b_bitrate)
            res_str = _get_stream_resolution_label(b_w, b_h, b_fps, gear)

            dev_icon = _get_gear_device_icon(gear)
            pad_str = FULL_WIDTH_PAD if idx == 0 else ""
            quote_lines.append(f"{dev_icon} <b>{gear}</b>{pad_str}")
            quote_lines.append(f"<code>{res_str}</code> • <code>{bitrate_str}</code> • <code>{b_codec}</code> • <code>{size_str}</code>")
    else:
        max_d = max(orig_width, orig_height)
        res_str = f"{max_d}p60" if max_d > 0 else "1080p60"
        bitrate_str = _format_bitrate_str(bitrate_kbps * 1000) if bitrate_kbps > 0 else "2.0 MBps"
        size_bytes = (bitrate_kbps * 1000 / 8.0) * duration if (duration > 0 and bitrate_kbps > 0) else file_size
        size_str = _format_file_size_str(size_bytes) if size_bytes > 0 else "4.5 MB"
        
        quote_lines.append(f"{ce('phone', '📱')} <b>play_addr</b>{FULL_WIDTH_PAD}")
        quote_lines.append(f"<code>{res_str}</code> • <code>{bitrate_str}</code> • <code>{codec}</code> • <code>{size_str}</code>")

    lines.append(f"<blockquote expandable>\n" + "\n".join(quote_lines) + "\n</blockquote>")
    
    orig_str = f"{orig_width}x{orig_height}" if (orig_width > 0 and orig_height > 0) else "1174x1080"
    lines.append(f"| Original | <code>{orig_str}</code>")
    lines.append(f"| VQ Score | <code>{vq_display}</code>")
    lines.append("")
    
    # 🏷️ Categories
    if categories:
        lines.append(f"{ce('tag', '🏷️')} <b>Categories</b>")
        for cat in categories:
            lines.append(f"| {html.escape(cat)}")
    
    return "\n".join(lines).strip()
