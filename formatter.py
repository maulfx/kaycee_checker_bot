"""
Message Formatter module.
Formats video analysis data into clean, modern Telegram messages
matching the user's reference design with TgAndroidIcons style, blockquotes, and clear typography.
"""

import html
from datetime import datetime
from config import REGION_FLAGS, REGION_NAMES, CATEGORY_KEYWORDS
from video_analyzer import format_bitrate, format_file_size
from vq_score import get_vq_grade, get_vq_bar


def _infer_categories(hashtags: list[str]) -> list[str]:
    """
    Infer video categories from hashtags.
    Returns a list of matched category names.
    """
    categories = set()
    hashtags_lower = [h.lower() for h in hashtags]
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            for hashtag in hashtags_lower:
                if keyword in hashtag:
                    categories.add(category)
                    break
    
    if not categories:
        categories.add("Entertainment")
    
    return sorted(categories)


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to MM:SS format."""
    if seconds <= 0:
        return "0:00"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _format_number(n: int) -> str:
    """Format numbers with thousand separators (e.g. 1,000, 25,000)."""
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
        return "⚠️ Possible"
    
    if age_hours > 72 and views > 0:
        engagement_rate = (likes + comments + shares) / views
        if engagement_rate < 0.001 and views < 100:
            return "⚠️ Possible"
    
    return "No"


def _format_bitrate_str(bps: int) -> str:
    """Format bitrate into human-readable string (e.g. 4.3 MBps or 700 KBps)."""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} MBps"
    kbps = round(bps / 1000)
    return f"{kbps} KBps"


def _format_file_size_str(bytes_val: float) -> str:
    """Format file size into human-readable string (e.g. 5.4 MB or 829.1 KB)."""
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


def format_analysis_message(
    tiktok_data: dict,
    video_quality: dict,
    vq_score: float
) -> str:
    """
    Format all analysis data into a clean Telegram HTML message matching the user's design and TgAndroidIcons pack.
    """
    
    # ─── Extract data ─────────────────────────────────────────
    raw_username = tiktok_data.get("author_username", "Unknown")
    raw_nickname = tiktok_data.get("author_nickname", raw_username)
    raw_title = tiktok_data.get("title", "")
    raw_formatted_date = tiktok_data.get("formatted_date", "Unknown")
    duration = tiktok_data.get("duration", 0)
    raw_video_id = tiktok_data.get("id", "Unknown")
    region_code = tiktok_data.get("region", "")
    raw_source = tiktok_data.get("source", "Unknown")
    hashtags = tiktok_data.get("hashtags", [])
    
    # Escape HTML special characters
    username = html.escape(str(raw_username))
    nickname = html.escape(str(raw_nickname))
    title = html.escape(str(raw_title))
    formatted_date = html.escape(str(raw_formatted_date))
    video_id = html.escape(str(raw_video_id))
    source = html.escape(str(raw_source))
    
    # Music info
    music_title = html.escape(str(tiktok_data.get("music_title", "")))
    music_author = html.escape(str(tiktok_data.get("music_author", "")))
    
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
    browser_q = tiktok_data.get("browser_quality") or video_quality.get("browser_quality", "720p60")
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
    final_vq = tiktok_data.get("vq_score") or vq_score
    
    # ─── Build message ────────────────────────────────────────
    lines = []
    
    # ═══ HEADER (Author & Date) ═══
    lines.append(f"🎵 {nickname}  🗓 {formatted_date}")
    
    # Title wrapped in blockquote
    if title:
        display_title = title if len(title) <= 250 else title[:247] + "..."
        lines.append(f"<blockquote>{display_title}</blockquote>")
    
    # Music info
    if music_title:
        music_display = f"🎧 {music_title}"
        if duration:
            music_display += f" • {_format_duration(duration)}"
        lines.append(music_display)
    
    lines.append("")
    
    # ═══ STATISTICS ═══
    lines.append("📊 <b>Statistics</b>")
    lines.append(f"  • 👁 <b>{_format_number(views)}</b> Views")
    lines.append(f"  • ♡ <b>{_format_number(likes)}</b> Likes")
    lines.append(f"  • 💬 <b>{_format_number(comments)}</b> Comments")
    lines.append(f"  • 🔖 <b>{_format_number(favorites)}</b> Favorites")
    lines.append(f"  • ➦ <b>{_format_number(shares)}</b> Shares")
    lines.append(f"  • ⤓ <b>{_format_number(downloads)}</b> Downloads")
    lines.append("")
    
    # ═══ INFORMATION ═══
    lines.append("ℹ <b>Information</b>")
    lines.append(f"  • 🔗 ID ┃ <code>{video_id}</code>")
    lines.append(f"  • ⤓ Source ┃ {source}")
    lines.append(f"  • 📍 Region ┃ {region_flag} {region_name}")
    lines.append(f"  • 👻 Shadow ban ┃ {shadow_ban}")
    if tiktok_data.get("is_ad"):
        lines.append(f"  • 📢 Ad ┃ Yes")
    lines.append("")
    
    # ═══ QUALITY ═══
    lines.append("⭐ <b>Quality</b>")
    lines.append(f"• 🌐 Browser | {browser_q}")
    lines.append(f"• 📱 Phone | {phone_q}")
    
    # Dynamic Stream Quality Blockquote
    quote_lines = []
    if bitrate_info:
        for b in bitrate_info:
            gear = b.get("gear", "")
            b_codec = b.get("codec", "h264")
            b_bitrate = b.get("bitrate", 0)
            b_w = b.get("width", 0)
            b_h = b.get("height", 0)
            b_fps = b.get("fps", 30)
            b_data_size = float(b.get("data_size", 0) or 0)
            
            if b_data_size <= 0 and duration > 0 and b_bitrate > 0:
                b_size_bytes = (b_bitrate / 8.0) * duration
            else:
                b_size_bytes = b_data_size

            size_str = _format_file_size_str(b_size_bytes)
            bitrate_str = _format_bitrate_str(b_bitrate)
            res_str = _get_stream_resolution_label(b_w, b_h, b_fps, gear)

            if "adapt_lowest_1080" in gear:
                header = f"🌐 📱 {gear}"
            elif "normal" in gear or gear == "play_addr":
                header = "🌐 📱 play_addr 🌐 normal_720_0 📱 play_addr_h264"
            elif "adapt_lower_720" in gear:
                header = f"🌐 📱 {gear}"
            elif "adapt_540" in gear:
                header = f"🌐 📱 {gear} 📱 play_addr_bytevc1"
            elif "lower_540" in gear:
                header = f"📱 {gear}"
            elif "lowest_540" in gear:
                header = f"📱 {gear}"
            elif "lowest_480" in gear:
                header = f"📱 {gear}"
            else:
                is_web = "normal" in gear or "720" in gear or "adapt" in gear
                is_phone = "adapt" in gear or "lower" in gear or "lowest" in gear or "540" in gear or "1080" in gear or "play_addr" in gear
                icon_str = "🌐 📱" if (is_web and is_phone) else ("🌐" if is_web else "📱")
                header = f"{icon_str} {gear}"

            quote_lines.append(header)
            quote_lines.append(f"{res_str} • {bitrate_str} • {b_codec} • {size_str}")
            quote_lines.append("")
    else:
        max_d = max(orig_width, orig_height)
        res_str = f"{max_d}p30" if max_d > 0 else "720p30"
        bitrate_str = _format_bitrate_str(bitrate_kbps * 1000)
        size_bytes = (bitrate_kbps * 1000 / 8.0) * duration if duration > 0 else file_size
        size_str = _format_file_size_str(size_bytes)
        
        quote_lines.append(f"📱 play_addr 📱 play_addr_{codec}")
        quote_lines.append(f"{res_str} • {bitrate_str} • {codec} • {size_str}")
        quote_lines.append("")

    if quote_lines and quote_lines[-1] == "":
        quote_lines.pop()

    lines.append("<blockquote>" + "\n".join(quote_lines) + "</blockquote>")
    
    if orig_width > 0 and orig_height > 0:
        lines.append(f"| Original | {orig_width}x{orig_height}")
    lines.append(f"| VQ Score | {final_vq}")
    lines.append("")
    
    # ═══ CATEGORIES ═══
    if categories:
        lines.append("🏷 <b>Categories</b>")
        for cat in categories:
            lines.append(f"  | {cat}")
    
    return "\n".join(lines)
