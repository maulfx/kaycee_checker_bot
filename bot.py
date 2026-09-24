"""
TikTok Video Analyzer - Telegram Bot
=====================================
Main entry point. Handles Telegram commands and messages,
orchestrates video analysis pipeline, and sends formatted results.

Features:
    - Send TikTok link → get thumbnail + action buttons
    - Download buttons: 576p, 720p, 1080p, Original, MP3
    - Shazam & Preview buttons
    - Check button → full video quality analysis (no limit)

Usage:
    1. Set TELEGRAM_BOT_TOKEN in .env file
    2. Run: python bot.py
    3. Send a TikTok link to the bot on Telegram
"""

import re
import html as html_module
import logging
import json
import httpx
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import BOT_TOKEN, REGION_FLAGS, REGION_NAMES
from tiktok_api import fetch_tiktok_data, extract_tiktok_url
from video_analyzer import analyze_video
from vq_score import calculate_vq_score
from formatter import format_analysis_message

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TikTokBot")

# Reduce noise from httpx/httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# TikTok URL detection pattern
TIKTOK_URL_RE = re.compile(
    r'https?://(?:(?:www|vm|vt)\.)?tiktok\.com/[^\s<>\"\']+',
    re.IGNORECASE,
)


def _format_number(n: int) -> str:
    """Format numbers with thousand separators (e.g. 1,000, 25,000)."""
    return f"{n:,}"


def _format_file_size(bytes_val: float) -> str:
    """Format file size into human-readable string."""
    if bytes_val <= 0:
        return ""
    if bytes_val >= 1048576:
        return f"{bytes_val / 1048576:.1f}MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f}KB"
    return f"{int(bytes_val)}B"


def _build_info_caption(data: dict) -> str:
    """
    Build the caption message that appears above the action buttons.
    Matches the reference design: username, date, region, caption/hashtags.
    """
    username = html_module.escape(data.get("author_username", "Unknown"))
    formatted_date = html_module.escape(data.get("formatted_date", "Unknown"))
    region_code = data.get("region", "")
    region_name = REGION_NAMES.get(region_code, region_code or "Unknown")
    title = html_module.escape(data.get("title", ""))

    lines = []
    # Header line: TikTok icon + username + date + region
    lines.append(f"🎵 <b>{username}</b>  📅 {formatted_date}  📍 {region_name}")

    # Caption/title with hashtags in blockquote
    if title:
        display_title = title if len(title) <= 300 else title[:297] + "..."
        lines.append(f"<blockquote>{display_title}</blockquote>")

    # Music info
    music_title = data.get("music_title", "")
    if music_title:
        music_display = f"♫ {html_module.escape(music_title)}"
        duration = data.get("duration", 0)
        if duration > 0:
            mins = duration // 60
            secs = duration % 60
            music_display += f" • {mins}:{secs:02d}"
        lines.append(music_display)

    lines.append("")
    lines.append("↓ <b>Choose an action</b>")

    return "\n".join(lines)


def _build_action_keyboard(data: dict, video_id: str) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard with download options, matching the reference UI.
    Layout:
      Row 1: [576p • SIZE] [720p • SIZE] [1080p • SIZE]
      Row 2: [⚡ Original] [🎵 MP3]
      Row 3: [◎ Shazam] [📺 Preview]
      Row 4: [🔍 Check]
      Row 5: [🎵 username]
    """
    bitrate_info = data.get("bitrate_info", [])
    duration = data.get("duration", 0)

    # Prepare download URLs and sizes for different resolutions
    # Try to find streams matching ~540p, ~720p, ~1080p
    stream_540 = None
    stream_720 = None
    stream_1080 = None

    for stream in bitrate_info:
        max_dim = max(stream.get("width", 0), stream.get("height", 0))
        gear = stream.get("gear", "")
        if max_dim >= 1080 or "1080" in gear:
            if stream_1080 is None:
                stream_1080 = stream
        elif max_dim >= 720 or "720" in gear:
            if stream_720 is None:
                stream_720 = stream
        elif max_dim >= 480 or "540" in gear or "lower" in gear:
            if stream_540 is None:
                stream_540 = stream

    # If we don't have distinct streams, create labels from available data
    def _stream_label(prefix: str, stream: dict | None) -> str:
        if not stream:
            return f"🎬 {prefix}"
        size_bytes = float(stream.get("data_size", 0) or 0)
        if size_bytes <= 0 and duration > 0 and stream.get("bitrate", 0) > 0:
            size_bytes = (stream["bitrate"] / 8.0) * duration
        size_str = _format_file_size(size_bytes)
        if size_str:
            return f"🎬 {prefix} • {size_str}"
        return f"🎬 {prefix}"

    # Build keyboard rows
    row1 = []
    row1.append(InlineKeyboardButton(
        _stream_label("576p", stream_540),
        callback_data=f"dl_540_{video_id}"
    ))
    row1.append(InlineKeyboardButton(
        _stream_label("720p", stream_720),
        callback_data=f"dl_720_{video_id}"
    ))
    row1.append(InlineKeyboardButton(
        _stream_label("1080p", stream_1080),
        callback_data=f"dl_1080_{video_id}"
    ))

    row2 = [
        InlineKeyboardButton("⚡ Original", callback_data=f"dl_orig_{video_id}"),
        InlineKeyboardButton("🎵 MP3", callback_data=f"dl_mp3_{video_id}"),
    ]

    row3 = [
        InlineKeyboardButton("◎ Shazam", callback_data=f"shazam_{video_id}"),
        InlineKeyboardButton("📺 Preview", callback_data=f"preview_{video_id}"),
    ]

    row4 = [
        InlineKeyboardButton("🔍 Check", callback_data=f"check_{video_id}"),
    ]

    username = data.get("author_username", "unknown")
    row5 = [
        InlineKeyboardButton(f"🎵 {username}", url=f"https://www.tiktok.com/@{username}"),
    ]

    keyboard = [row1, row2, row3, row4, row5]
    return InlineKeyboardMarkup(keyboard)


# ─── /start Command ──────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - send welcome message."""
    welcome = (
        "┌─────────────────────────────┐\n"
        "  🎬  <b>TikTok Video Analyzer</b>\n"
        "└─────────────────────────────┘\n"
        "\n"
        "Selamat datang! 👋\n"
        "\n"
        "Bot ini menganalisis kualitas video TikTok secara otomatis.\n"
        "Cukup kirim <b>link video TikTok</b> dan saya akan memberikan:\n"
        "\n"
        "  📥  Download video (576p, 720p, 1080p)\n"
        "  ⚡  Original quality download\n"
        "  🎵  Extract audio MP3\n"
        "  ◎  Shazam music detection\n"
        "  📺  Preview video\n"
        "  🔍  Full quality check & analysis\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Format link yang didukung:</b>\n"
        "  • <code>https://www.tiktok.com/@user/video/...</code>\n"
        "  • <code>https://vm.tiktok.com/...</code>\n"
        "  • <code>https://vt.tiktok.com/...</code>\n"
        "\n"
        "Kirim linknya sekarang! 🚀"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)


# ─── /help Command ────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "🔍 <b>Cara Penggunaan:</b>\n"
        "\n"
        "1️⃣  Buka video TikTok yang ingin dianalisis\n"
        "2️⃣  Salin link video (tombol Share → Copy Link)\n"
        "3️⃣  Kirim link ke chat ini\n"
        "4️⃣  Pilih action dari tombol yang muncul!\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 <b>Actions:</b>\n"
        "  • 576p/720p/1080p - Download video\n"
        "  • Original - Download kualitas asli\n"
        "  • MP3 - Extract audio saja\n"
        "  • Shazam - Deteksi musik\n"
        "  • Preview - Preview video\n"
        "  • Check - Full quality analysis\n"
        "\n"
        "⚙️ <b>Commands:</b>\n"
        "  /start - Mulai bot\n"
        "  /help  - Bantuan penggunaan\n"
        "  /about - Tentang bot ini\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# ─── /about Command ───────────────────────────────────────────
async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /about command."""
    about_text = (
        "🤖 <b>TikTok Video Analyzer Bot</b>\n"
        "\n"
        "Bot ini membantu kreator TikTok untuk:\n"
        "  • Download video berbagai resolusi\n"
        "  • Extract audio MP3\n"
        "  • Mengecek kualitas upload video\n"
        "  • Memantau statistik engagement\n"
        "  • Mendeteksi potensi shadow ban\n"
        "  • Mendapatkan skor kualitas video (VQ Score)\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>VQ Score Guide:</b>\n"
        "  🟢  90-100  Excellent (A+)\n"
        "  🟢  80-89   Very Good (A)\n"
        "  🟡  70-79   Good (B)\n"
        "  🟡  60-69   Fair (C)\n"
        "  🟠  50-59   Below Average (D)\n"
        "  🔴  40-49   Poor (E)\n"
        "  🔴  0-39    Very Poor (F)\n"
        "\n"
        "💡 <b>Tips untuk VQ Score tinggi:</b>\n"
        "  • Upload dengan resolusi 1080p atau lebih\n"
        "  • Gunakan codec H.265/HEVC jika bisa\n"
        "  • Record di 60fps untuk konten cepat\n"
        "  • Hindari kompresi berlebihan sebelum upload\n"
    )
    await update.message.reply_text(about_text, parse_mode=ParseMode.HTML)


# ─── Handle TikTok Link (Initial) ────────────────────────────
async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    When user sends a TikTok link:
    1. Fetch video data
    2. Send thumbnail image with caption + inline keyboard buttons
    3. Store data in context for callback handlers
    """
    text = update.message.text or ""
    url = extract_tiktok_url(text)

    if not url:
        return

    logger.info(f"Processing TikTok URL: {url}")

    try:
        # Fetch TikTok data directly without intermediate status message
        tiktok_data = await fetch_tiktok_data(url)

        if not tiktok_data:
            await update.message.reply_text(
                "❌ <b>Failed to retrieve video data</b>\n\n"
                "Possible reasons:\n"
                "  • Invalid or expired link\n"
                "  • Video was deleted or private\n"
                "  • API rate limit reached",
                parse_mode=ParseMode.HTML,
            )
            return

        video_id = tiktok_data.get("id", "unknown")

        # Store video data in bot_data for callback access
        if "video_cache" not in context.bot_data:
            context.bot_data["video_cache"] = {}
        context.bot_data["video_cache"][video_id] = tiktok_data

        # Build caption and keyboard
        caption = _build_info_caption(tiktok_data)
        keyboard = _build_action_keyboard(tiktok_data, video_id)

        # Get thumbnail URL
        cover_url = (
            tiktok_data.get("origin_cover_url")
            or tiktok_data.get("cover_url")
            or ""
        )

        if cover_url:
            # Send thumbnail with caption and buttons
            try:
                await update.message.reply_photo(
                    photo=cover_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            except Exception as photo_err:
                logger.warning(f"Failed to send photo: {photo_err}, falling back to text")
                await update.message.reply_text(
                    caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
        else:
            # No thumbnail available, send text only
            await update.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )

        logger.info(f"Sent action menu for video {video_id} (@{tiktok_data.get('author_username')})")

    except Exception as e:
        logger.error(f"Error processing TikTok link: {e}", exc_info=True)
        error_msg = html_module.escape(str(e))
        if len(error_msg) > 200:
            error_msg = error_msg[:197] + "..."
        await status_msg.edit_text(
            f"❌ <b>Terjadi kesalahan</b>\n\n"
            f"<code>{error_msg}</code>\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback: Check (Full Analysis) ─────────────────────────
async def callback_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Check button - run video quality analysis and send video with formatted caption."""
    query = update.callback_query
    await query.answer("🔍 Checking video quality...")

    video_id = query.data.replace("check_", "", 1)
    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Video data not found. Please resend the TikTok link.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        video_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")
        video_quality = await analyze_video(video_url, fallback_data=tiktok_data)

        final_width = video_quality.get("width") or tiktok_data.get("width", 0)
        final_height = video_quality.get("height") or tiktok_data.get("height", 0)
        final_bitrate = video_quality.get("bitrate_kbps") or tiktok_data.get("bitrate_kbps", 0)
        final_codec = video_quality.get("codec") or tiktok_data.get("codec", "h264")
        final_fps = video_quality.get("fps", 30)

        vq = calculate_vq_score(
            width=final_width,
            height=final_height,
            bitrate_kbps=final_bitrate,
            codec=final_codec,
            fps=final_fps,
        )

        message = format_analysis_message(tiktok_data, video_quality, vq)

        # Download video buffer and send directly as Telegram Video
        sent_video = False
        if video_url:
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    resp = await client.get(video_url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        from io import BytesIO
                        video_bytes = BytesIO(resp.content)
                        video_bytes.name = f"{video_id}.mp4"
                        await query.message.reply_video(
                            video=video_bytes,
                            caption=message,
                            parse_mode=ParseMode.HTML,
                        )
                        sent_video = True
            except Exception as vid_err:
                logger.warning(f"Failed to send downloaded video stream: {vid_err}")

        if not sent_video:
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

        logger.info(
            f"Check complete: @{tiktok_data.get('author_username')} - "
            f"VQ:{vq} - {final_width}x{final_height}"
        )

    except Exception as e:
        logger.error(f"Error in check analysis: {e}", exc_info=True)
        error_msg = html_module.escape(str(e))
        if len(error_msg) > 200:
            error_msg = error_msg[:197] + "..."
        await query.message.reply_text(
            f"❌ <b>An error occurred during analysis</b>\n\n"
            f"<code>{error_msg}</code>",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback: Download Video ────────────────────────────────
async def callback_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle download buttons (540p, 720p, 1080p, original) - send actual video file."""
    query = update.callback_query

    # Parse callback data
    data = query.data  # e.g. "dl_540_{video_id}", "dl_orig_{video_id}"
    parts = data.split("_", 2)
    quality = parts[1]  # "540", "720", "1080", "orig"
    video_id = parts[2] if len(parts) > 2 else ""

    await query.answer(f"📥 Downloading {quality} video...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Video data not found. Please resend the TikTok link.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Find the appropriate download URL
    download_url = ""
    bitrate_info = tiktok_data.get("bitrate_info", [])

    if quality == "orig":
        download_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")
    else:
        target_res = int(quality)
        best_match = None
        for stream in bitrate_info:
            max_dim = max(stream.get("width", 0), stream.get("height", 0))
            gear = stream.get("gear", "")
            if target_res >= 1080 and (max_dim >= 1080 or "1080" in gear):
                best_match = stream
                break
            elif target_res >= 720 and (max_dim >= 720 or "720" in gear) and max_dim < 1080 and "1080" not in gear:
                best_match = stream
                break
            elif target_res >= 480 and (max_dim >= 480 or "540" in gear) and max_dim < 720 and "720" not in gear:
                best_match = stream
                break

        if best_match and best_match.get("url"):
            download_url = best_match["url"]
        else:
            if target_res >= 1080:
                download_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")
            else:
                download_url = tiktok_data.get("play_url") or tiktok_data.get("hdplay_url", "")

    label = "Original" if quality == "orig" else f"{quality}p"
    if download_url:
        sent = False
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(download_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and len(resp.content) > 1000:
                    from io import BytesIO
                    v_bytes = BytesIO(resp.content)
                    v_bytes.name = f"TikTok_{label}_{video_id}.mp4"
                    await query.message.reply_video(
                        video=v_bytes,
                        caption=f"📥 <b>TikTok Video ({label})</b>\n👤 @{html_module.escape(tiktok_data.get('author_username', ''))}",
                        parse_mode=ParseMode.HTML,
                    )
                    sent = True
        except Exception as err:
            logger.warning(f"Failed to send video bytes for download: {err}")

        if not sent:
            await query.message.reply_text(
                f"📥 <b>Download {label}</b>\n\n"
                f"<a href=\"{html_module.escape(download_url)}\">⬇️ Click here to download</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    else:
        await query.message.reply_text(
            f"❌ Download URL for {label} is unavailable.",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback: MP3 Audio ─────────────────────────────────────
async def callback_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle MP3 button - send audio download link."""
    query = update.callback_query
    video_id = query.data.replace("dl_mp3_", "", 1)
    await query.answer("🎵 Menyiapkan audio MP3...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Data video tidak ditemukan. Kirim ulang link TikTok-nya.",
            parse_mode=ParseMode.HTML,
        )
        return

    music_url = tiktok_data.get("music_url", "")
    music_title = html_module.escape(tiktok_data.get("music_title", "Audio"))

    if music_url:
        await query.message.reply_text(
            f"🎵 <b>MP3 Audio</b>\n"
            f"♫ {music_title}\n\n"
            f"<a href=\"{html_module.escape(music_url)}\">⬇️ Download MP3</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    else:
        await query.message.reply_text(
            "❌ URL audio MP3 tidak tersedia untuk video ini.",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback: Shazam ────────────────────────────────────────
async def callback_shazam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Shazam button - show music info."""
    query = update.callback_query
    video_id = query.data.replace("shazam_", "", 1)
    await query.answer("◎ Mendeteksi musik...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Data video tidak ditemukan. Kirim ulang link TikTok-nya.",
            parse_mode=ParseMode.HTML,
        )
        return

    music_title = html_module.escape(tiktok_data.get("music_title", "Unknown"))
    music_author = html_module.escape(tiktok_data.get("music_author", "Unknown"))
    music_url = tiktok_data.get("music_url", "")

    msg = (
        f"◎ <b>Shazam - Music Detection</b>\n\n"
        f"🎵 <b>Title:</b> {music_title}\n"
        f"👤 <b>Artist:</b> {music_author}\n"
    )

    if music_url:
        msg += f"\n<a href=\"{html_module.escape(music_url)}\">🎧 Dengarkan</a>"

    await query.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ─── Callback: Preview ───────────────────────────────────────
async def callback_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Preview button - send video preview URL."""
    query = update.callback_query
    video_id = query.data.replace("preview_", "", 1)
    await query.answer("📺 Menyiapkan preview...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Data video tidak ditemukan. Kirim ulang link TikTok-nya.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Use play_url for preview (lower quality / faster load)
    play_url = tiktok_data.get("play_url") or tiktok_data.get("hdplay_url", "")
    original_url = tiktok_data.get("original_url", "")

    if play_url:
        try:
            # Try to send as actual video
            await query.message.reply_video(
                video=play_url,
                caption=f"📺 Preview video\n🔗 {html_module.escape(original_url)}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Failed to send video preview: {e}")
            await query.message.reply_text(
                f"📺 <b>Preview</b>\n\n"
                f"<a href=\"{html_module.escape(play_url)}\">▶️ Tonton preview</a>\n"
                f"🔗 <a href=\"{html_module.escape(original_url)}\">Link TikTok asli</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
    else:
        await query.message.reply_text(
            f"📺 <b>Preview</b>\n\n"
            f"🔗 <a href=\"{html_module.escape(original_url)}\">Buka di TikTok</a>",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback Router ─────────────────────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to the appropriate handler."""
    query = update.callback_query
    data = query.data

    if data.startswith("check_"):
        await callback_check(update, context)
    elif data.startswith("dl_mp3_"):
        await callback_mp3(update, context)
    elif data.startswith("dl_"):
        await callback_download(update, context)
    elif data.startswith("shazam_"):
        await callback_shazam(update, context)
    elif data.startswith("preview_"):
        await callback_preview(update, context)
    else:
        await query.answer("❓ Action tidak dikenal.")


# ─── Message Handler ─────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all text messages - check if they contain TikTok URLs."""
    text = update.message.text or ""

    if TIKTOK_URL_RE.search(text):
        await handle_tiktok_link(update, context)
    else:
        await update.message.reply_text(
            "🎬 Kirim link video TikTok untuk mulai!\n\n"
            "Contoh:\n"
            "<code>https://www.tiktok.com/@username/video/1234567890</code>",
            parse_mode=ParseMode.HTML,
        )


# ─── Post Init (set bot commands) ────────────────────────────
async def post_init(application) -> None:
    """Set bot commands menu after initialization."""
    commands = [
        BotCommand("start", "Mulai bot"),
        BotCommand("help", "Bantuan penggunaan"),
        BotCommand("about", "Tentang bot & VQ Score"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set successfully")


# ─── Main ─────────────────────────────────────────────────────
def main() -> None:
    """Start the bot."""
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    if not BOT_TOKEN:
        print("━" * 50)
        print("❌ ERROR: TELEGRAM_BOT_TOKEN belum diset!")
        print("")
        print("Langkah setup:")
        print("  1. Buka @BotFather di Telegram")
        print("  2. Kirim /newbot dan ikuti instruksi")
        print("  3. Salin token bot yang diberikan")
        print("  4. Buat file .env dengan isi:")
        print("     TELEGRAM_BOT_TOKEN=token_kamu_di_sini")
        print("━" * 50)
        return

    print("━" * 50)
    print("🎬 TikTok Video Analyzer Bot")
    print("━" * 50)
    print("🔄 Memulai bot...")

    # Build application
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("✅ Bot berjalan! Tekan Ctrl+C untuk berhenti.")
    print("━" * 50)

    # Start polling
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
