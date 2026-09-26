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

import asyncio
import re
import html as html_module
import logging
import json
import httpx
from io import BytesIO
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
from emoji_icons import ce

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


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to MM:SS format."""
    if seconds <= 0:
        return "0:00"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _build_info_caption(data: dict) -> str:
    """
    Build the caption message that appears above the action buttons.
    Matches the modern reference UI layout.
    """
    raw_username = data.get("author_username", "Unknown")
    username_upper = html_module.escape(str(raw_username)).upper()
    formatted_date = html_module.escape(str(data.get("formatted_date", "Unknown")))
    title = html_module.escape(str(data.get("title", "")))
    music_title = html_module.escape(str(data.get("music_title", f"original sound - {raw_username}")))
    duration = data.get("duration", 0)
    views = data.get("views", 0)
    likes = data.get("likes", 0)
    comments = data.get("comments", 0)

    lines = []
    # Header: 🎵 SKYRUL  🗓️ 31 August 2026, 05:10:55
    lines.append(f"{ce('music_note', '🎵')} <b>{username_upper}</b>  {ce('calendar', '🗓️')} {formatted_date}")

    # Caption in blockquote (Italic)
    if title:
        display_title = title if len(title) <= 150 else title[:147] + "..."
        lines.append(f"<blockquote><i>{display_title}</i></blockquote>")

    # Audio badge
    dur_str = f" • {_format_duration(duration)}" if duration > 0 else ""
    lines.append(f"{ce('music_notes', '🎶')} {music_title}{dur_str}")
    lines.append("")
    lines.append("↓ <b>Select an option below:</b>")

    return "\n".join(lines)

    return "\n".join(lines)


def _build_action_keyboard(data: dict, video_id: str) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard with download options, matching the reference UI.
    Layout:
      Row 1: [576p • SIZE] [720p • SIZE] [1080p • SIZE]
      Row 2: [⚡ Original] [🎵 MP3]
      Row 3: [🔍 Shazam] [▶️ Preview]
      Row 4: [🔎 Check]
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
        gear = stream.get("gear", "").lower()
        if max_dim >= 1080 or "1080" in gear:
            if stream_1080 is None:
                stream_1080 = stream
        elif (720 <= max_dim < 1080) or "720" in gear:
            if stream_720 is None:
                stream_720 = stream
        elif (480 <= max_dim < 720) or "540" in gear or "576" in gear or "480" in gear or "lower" in gear or "lowest" in gear:
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

    # Build keyboard row only for available resolution tiers
    row1 = []
    if stream_540:
        row1.append(InlineKeyboardButton(
            _stream_label("576p", stream_540),
            callback_data=f"dl_540_{video_id}"
        ))
    if stream_720:
        row1.append(InlineKeyboardButton(
            _stream_label("720p", stream_720),
            callback_data=f"dl_720_{video_id}"
        ))
    if stream_1080:
        row1.append(InlineKeyboardButton(
            _stream_label("1080p", stream_1080),
            callback_data=f"dl_1080_{video_id}"
        ))

    # If no specific tier was matched in bitrate_info, use the main video resolution
    if not row1:
        w = data.get("width", 0)
        h = data.get("height", 0)
        max_dim = max(w, h)
        size_val = data.get("hd_size") or data.get("size") or 0
        dummy_stream = {"data_size": size_val}
        if max_dim >= 1080:
            row1.append(InlineKeyboardButton(
                _stream_label("1080p", dummy_stream),
                callback_data=f"dl_1080_{video_id}"
            ))
        elif max_dim >= 720:
            row1.append(InlineKeyboardButton(
                _stream_label("720p", dummy_stream),
                callback_data=f"dl_720_{video_id}"
            ))
        else:
            tag = f"{max_dim}p" if max_dim > 0 else "576p"
            row1.append(InlineKeyboardButton(
                _stream_label(tag, dummy_stream),
                callback_data=f"dl_540_{video_id}"
            ))

    row2 = [
        InlineKeyboardButton("⚡ Original", callback_data=f"dl_orig_{video_id}"),
        InlineKeyboardButton("🎵 MP3", callback_data=f"dl_mp3_{video_id}"),
    ]

    row3 = [
        InlineKeyboardButton("🔍 Shazam", callback_data=f"shazam_{video_id}"),
        InlineKeyboardButton("▶️ Preview", callback_data=f"preview_{video_id}"),
    ]

    row4 = [
        InlineKeyboardButton("🔎 Check", callback_data=f"check_{video_id}"),
    ]

    username = data.get("author_username", "unknown")
    row5 = [
        InlineKeyboardButton(f"🎵 @{username}", url=f"https://www.tiktok.com/@{username}"),
    ]

    keyboard = []
    if row1:
        keyboard.append(row1)
    keyboard.extend([row2, row3, row4, row5])
    return InlineKeyboardMarkup(keyboard)


def _build_checker_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """Build keyboard for the checker result message with a Recheck button."""
    keyboard = [
        [InlineKeyboardButton("🔄 Recheck", callback_data=f"recheck_{video_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─── /start Command ──────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - send welcome message."""
    welcome = (
        "┌─────────────────────────────┐\n"
        "  ✨  <b>TikTok Video Analyzer</b>\n"
        "└─────────────────────────────┘\n"
        "\n"
        "Welcome! 👋\n"
        "\n"
        "This bot analyzes TikTok video quality automatically.\n"
        "Simply send a <b>TikTok video link</b> and you will get:\n"
        "\n"
        "  📥  Download video (576p, 720p, 1080p)\n"
        "  ⚡  Original quality download\n"
        "  🎵  Extract MP3 audio\n"
        "  🔍  Shazam music detection\n"
        "  ▶️  Video preview\n"
        "  🔎  Full quality check & analysis\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>Supported link formats:</b>\n"
        "  • <code>https://www.tiktok.com/@user/video/...</code>\n"
        "  • <code>https://vm.tiktok.com/...</code>\n"
        "  • <code>https://vt.tiktok.com/...</code>\n"
        "\n"
        "Send your link now! 🚀"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)


# ─── /help Command ────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "🔎 <b>How to Use:</b>\n"
        "\n"
        "1️⃣  Open the TikTok video you want to analyze\n"
        "2️⃣  Copy the video link (Share → Copy Link)\n"
        "3️⃣  Send the link to this chat\n"
        "4️⃣  Choose an action from the buttons below!\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>Actions:</b>\n"
        "  • 576p/720p/1080p - Download video\n"
        "  • Original - Download original quality\n"
        "  • MP3 - Extract audio only\n"
        "  • Shazam - Detect music & artist\n"
        "  • Preview - Watch video preview\n"
        "  • Check - Full quality analysis\n"
        "\n"
        "📋 <b>Commands:</b>\n"
        "  /start - Start the bot\n"
        "  /help  - Usage guide\n"
        "  /about - About the bot & VQ Score\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# ─── /about Command ───────────────────────────────────────────
async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /about command."""
    about_text = (
        "✦ <b>TikTok Video Analyzer Bot</b>\n"
        "\n"
        "This bot helps TikTok creators to:\n"
        "  • Download videos in multiple resolutions\n"
        "  • Extract MP3 audio tracks\n"
        "  • Inspect upload quality & compression\n"
        "  • Monitor real engagement statistics\n"
        "  • Detect potential shadowbans\n"
        "  • Measure video quality rating (VQ Score)\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>VQ Score Guide (0 = No Compress / Lossless):</b>\n"
        "  🟢  0 - 15   No Compress / Pristine (Lossless)\n"
        "  🟢  16 - 30  Low Compression (Very Good)\n"
        "  🟡  31 - 45  Moderate Compression (Good)\n"
        "  🟠  46 - 60  Medium Compression (Fair)\n"
        "  🔴  > 60     Heavy Compression (Poor)\n"
        "\n"
        "💡 <b>Tips for lower VQ Score (Closer to 0):</b>\n"
        "  • Upload in 1080p resolution or higher\n"
        "  • Use higher bitrate & H.265/HEVC codec\n"
        "  • Record at 60fps for high-motion content\n"
        "  • Avoid multiple re-compressions before uploading\n"
    )
    await update.message.reply_text(about_text, parse_mode=ParseMode.HTML)


async def _fetch_cover_bytes(url: str) -> bytes | None:
    """Download cover image bytes so Telegram sends photo + caption + buttons reliably."""
    if not url:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200 and len(r.content) > 500:
                return r.content
    except Exception as e:
        logger.debug(f"Failed to fetch cover bytes: {e}")
    return None


def _build_checker_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for checker analysis message with Recheck button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Recheck", callback_data=f"recheck_{video_id}")]
    ])


# ─── Handle TikTok Link (Initial) ────────────────────────────
async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    When user sends a TikTok link:
    1. Fetch video data
    2. Send thumbnail image with caption + inline keyboard buttons merged
    3. Store data in context for callback handlers
    """
    text = update.message.text or ""
    url = extract_tiktok_url(text)

    if not url:
        return

    logger.info(f"Processing TikTok URL: {url}")

    try:
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

        # Get thumbnail URL and fetch bytes to guarantee merged photo message
        cover_url = (
            tiktok_data.get("origin_cover_url")
            or tiktok_data.get("cover_url")
            or ""
        )
        cover_bytes = await _fetch_cover_bytes(cover_url) if cover_url else None

        sent_photo = False
        if cover_bytes:
            try:
                photo_file = BytesIO(cover_bytes)
                photo_file.name = f"cover_{video_id}.jpg"
                await update.message.reply_photo(
                    photo=photo_file,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                sent_photo = True
            except Exception as e:
                logger.warning(f"Failed to send cover bytes: {e}")

        if not sent_photo and cover_url:
            try:
                await update.message.reply_photo(
                    photo=cover_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                sent_photo = True
            except Exception as e:
                logger.warning(f"Failed to send cover URL: {e}")

        if not sent_photo:
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
        await update.message.reply_text(
            f"❌ <b>An error occurred</b>\n\n"
            f"<code>{error_msg}</code>\n\n"
            f"Please try again later.",
            parse_mode=ParseMode.HTML,
        )


async def _download_tiktok_video_bytes(orig_url: str, fallback_url: str = "", quality: str = "best") -> bytes | None:
    """
    Robust video downloader using TikWM API + direct headers + yt-dlp fallback to bypass TikTok 403 CDN errors.
    """
    # 1. Try TikWM API first (fastest)
    if orig_url:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.post("https://www.tikwm.com/api/", data={"url": orig_url, "hd": 1})
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    dl_url = data.get("hdplay") or data.get("play")
                    if dl_url:
                        if dl_url.startswith("/"):
                            dl_url = "https://www.tikwm.com" + dl_url
                        r_vid = await client.get(dl_url, headers={"User-Agent": "Mozilla/5.0"})
                        if r_vid.status_code == 200 and len(r_vid.content) > 1000:
                            return r_vid.content
        except Exception as e:
            logger.debug(f"TikWM video buffer download error: {e}")

    # 2. Try direct download if fallback_url provided with proper headers
    if fallback_url:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/",
            }
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(fallback_url, headers=headers)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content
        except Exception as e:
            logger.debug(f"Direct stream download error: {e}")

    # 3. Fallback to yt-dlp
    if orig_url:
        try:
            import yt_dlp
            import tempfile
            import os
            loop = asyncio.get_running_loop()
            def _ytdlp_dl():
                with tempfile.TemporaryDirectory() as tmpdir:
                    outpath = os.path.join(tmpdir, "vid.mp4")
                    format_opt = "best"
                    if quality == "720":
                        format_opt = "best[height<=720]/best"
                    elif quality == "540":
                        format_opt = "best[height<=576]/best"

                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "outtmpl": outpath,
                        "format": format_opt,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([orig_url])
                    if os.path.exists(outpath):
                        with open(outpath, "rb") as f:
                            return f.read()
                return None
            res = await loop.run_in_executor(None, _ytdlp_dl)
            if res:
                return res
        except Exception as e:
            logger.warning(f"yt-dlp video buffer download error: {e}")

    return None


# ─── Callback: Check (Full Analysis) ─────────────────────────
async def callback_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Check button - delete previous menu, run video quality analysis, send video with analysis caption and Recheck button."""
    query = update.callback_query
    await query.answer("🔍 Checking video quality...")

    video_id = query.data.replace("check_", "", 1)
    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    chat_id = query.message.chat_id

    # Delete the previous menu message directly
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")

    try:
        if not tiktok_data:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Video data not found. Please resend the TikTok link.",
                parse_mode=ParseMode.HTML,
            )
            return

        orig_url = tiktok_data.get("original_url", "")
        # Determine the highest resolution stream URL
        bitrate_info = tiktok_data.get("bitrate_info", [])
        best_url = ""
        best_stream = None
        if bitrate_info:
            best_stream = bitrate_info[0]
            best_url = best_stream.get("url", "")
        if not best_url:
            best_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")

        video_quality = await analyze_video(best_url, fallback_data=tiktok_data)

        final_width = (best_stream.get("width") if best_stream else 0) or video_quality.get("width") or tiktok_data.get("width", 0)
        final_height = (best_stream.get("height") if best_stream else 0) or video_quality.get("height") or tiktok_data.get("height", 0)
        final_bitrate = (best_stream.get("bitrate", 0) // 1000 if best_stream else 0) or video_quality.get("bitrate_kbps") or tiktok_data.get("bitrate_kbps", 0)
        final_codec = (best_stream.get("codec") if best_stream else "") or video_quality.get("codec") or tiktok_data.get("codec", "h264")
        final_fps = (best_stream.get("fps") if best_stream else 0) or video_quality.get("fps", 30)

        vq = calculate_vq_score(
            width=final_width,
            height=final_height,
            bitrate_kbps=final_bitrate,
            codec=final_codec,
            fps=final_fps,
        )

        message = format_analysis_message(tiktok_data, video_quality, vq)
        checker_keyboard = _build_checker_keyboard(video_id)

        # Download and send the highest resolution video file with analysis caption and Recheck button
        sent_video = False
        raw_bytes = await _download_tiktok_video_bytes(orig_url, fallback_url=best_url, quality="best")
        if raw_bytes:
            try:
                video_bytes = BytesIO(raw_bytes)
                video_bytes.name = f"{video_id}_{final_width}x{final_height}.mp4"
                
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_bytes,
                    caption=message,
                    parse_mode=ParseMode.HTML,
                    width=final_width if final_width > 0 else None,
                    height=final_height if final_height > 0 else None,
                    supports_streaming=True,
                    reply_markup=checker_keyboard,
                )
                sent_video = True
            except Exception as vid_err:
                logger.warning(f"Failed to send video with analysis caption: {vid_err}")

        # Fallback to text message if video sending failed
        if not sent_video:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=checker_keyboard,
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
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>An error occurred during analysis</b>\n\n<code>{error_msg}</code>",
            parse_mode=ParseMode.HTML,
        )


# ─── Callback: Recheck (In-Place Refresh) ────────────────────
async def callback_recheck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Recheck button - re-scrape fresh TikTok data and refresh the analysis message in-place."""
    query = update.callback_query
    video_id = query.data.replace("recheck_", "", 1)
    await query.answer("🔄 Refreshing video analysis...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    orig_url = tiktok_data.get("original_url") if tiktok_data else ""
    if not orig_url:
        author = tiktok_data.get("author_username", "user") if tiktok_data else "user"
        orig_url = f"https://www.tiktok.com/@{author}/video/{video_id}"

    try:
        # Re-fetch latest TikTok data from APIs
        new_data = await fetch_tiktok_data(orig_url)
        if new_data and new_data.get("id"):
            tiktok_data = new_data
            if "video_cache" not in context.bot_data:
                context.bot_data["video_cache"] = {}
            context.bot_data["video_cache"][video_id] = tiktok_data

        if not tiktok_data:
            await query.answer("❌ Failed to refresh video data.", show_alert=True)
            return

        bitrate_info = tiktok_data.get("bitrate_info", [])
        best_url = bitrate_info[0].get("url", "") if bitrate_info else (tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", ""))
        video_quality = await analyze_video(best_url, fallback_data=tiktok_data)

        final_width = (bitrate_info[0].get("width") if bitrate_info else 0) or video_quality.get("width") or tiktok_data.get("width", 0)
        final_height = (bitrate_info[0].get("height") if bitrate_info else 0) or video_quality.get("height") or tiktok_data.get("height", 0)
        final_bitrate = (bitrate_info[0].get("bitrate", 0) // 1000 if bitrate_info else 0) or video_quality.get("bitrate_kbps") or tiktok_data.get("bitrate_kbps", 0)
        final_codec = (bitrate_info[0].get("codec") if bitrate_info else "") or video_quality.get("codec") or tiktok_data.get("codec", "h264")
        final_fps = (bitrate_info[0].get("fps") if bitrate_info else 0) or video_quality.get("fps", 30)

        vq = calculate_vq_score(
            width=final_width,
            height=final_height,
            bitrate_kbps=final_bitrate,
            codec=final_codec,
            fps=final_fps,
        )

        message = format_analysis_message(tiktok_data, video_quality, vq)
        checker_keyboard = _build_checker_keyboard(video_id)

        try:
            if query.message.caption is not None:
                await query.edit_message_caption(
                    caption=message,
                    parse_mode=ParseMode.HTML,
                    reply_markup=checker_keyboard,
                )
            else:
                await query.edit_message_text(
                    text=message,
                    parse_mode=ParseMode.HTML,
                    reply_markup=checker_keyboard,
                    disable_web_page_preview=True,
                )
            await query.answer("✅ Video analysis refreshed!")
        except Exception as edit_err:
            if "not modified" in str(edit_err).lower():
                await query.answer("✅ Video analysis is already up to date!")
            else:
                logger.warning(f"Message edit notice on recheck: {edit_err}")
                await query.answer("✅ Video analysis refreshed!")

    except Exception as e:
        logger.error(f"Error in recheck: {e}", exc_info=True)
        await query.answer("❌ Error refreshing analysis.", show_alert=True)


# ─── Callback: Download Video ────────────────────────────────
async def callback_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle download buttons (540p, 720p, 1080p, original) - delete menu, send in-app playable video with caption & hashtags."""
    query = update.callback_query
    chat_id = query.message.chat_id

    # Parse callback data
    data = query.data  # e.g. "dl_540_{video_id}", "dl_orig_{video_id}"
    parts = data.split("_", 2)
    quality = parts[1]  # "540", "720", "1080", "orig"
    video_id = parts[2] if len(parts) > 2 else ""
    label = "Original" if quality == "orig" else f"{quality}p"

    await query.answer(f"📥 Downloading {label} video...")

    # Delete the previous menu message directly
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")

    try:
        tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
        if not tiktok_data:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Video data not found. Please resend the TikTok link.",
                parse_mode=ParseMode.HTML,
            )
            return

        orig_url = tiktok_data.get("original_url", "")
        # Find the appropriate download URL
        download_url = ""
        target_stream = None
        bitrate_info = tiktok_data.get("bitrate_info", [])

        if quality == "orig":
            if bitrate_info:
                target_stream = bitrate_info[0]
                download_url = target_stream.get("url", "")
            if not download_url:
                download_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")
        else:
            target_res = int(quality)
            for stream in bitrate_info:
                max_dim = max(stream.get("width", 0), stream.get("height", 0))
                gear = stream.get("gear", "")
                if target_res >= 1080 and (max_dim >= 1080 or "1080" in gear):
                    target_stream = stream
                    break
                elif target_res >= 720 and (max_dim >= 720 or "720" in gear) and max_dim < 1080 and "1080" not in gear:
                    target_stream = stream
                    break
                elif target_res >= 480 and (max_dim >= 480 or "540" in gear) and max_dim < 720 and "720" not in gear:
                    target_stream = stream
                    break

            if target_stream and target_stream.get("url"):
                download_url = target_stream["url"]
            else:
                if target_res >= 1080:
                    download_url = tiktok_data.get("hdplay_url") or tiktok_data.get("play_url", "")
                else:
                    download_url = tiktok_data.get("play_url") or tiktok_data.get("hdplay_url", "")

        w = target_stream.get("width", 0) if target_stream else tiktok_data.get("width", 0)
        h = target_stream.get("height", 0) if target_stream else tiktok_data.get("height", 0)

        # Build download caption with author, caption, hashtags
        raw_title = tiktok_data.get("title", "")
        author_nickname = html_module.escape(tiktok_data.get("author_nickname", "Video"))
        author_username = html_module.escape(tiktok_data.get("author_username", ""))

        caption_lines = [f"🎵 <b>{author_nickname}</b>  👤 @{author_username}"]
        if raw_title:
            display_title = html_module.escape(raw_title)
            if len(display_title) > 300:
                display_title = display_title[:297] + "..."
            caption_lines.append(f"<blockquote>{display_title}</blockquote>")

        caption_lines.append(f"📥 <b>TikTok Video ({label})</b> • {w}x{h}")
        vid_caption = "\n".join(caption_lines)
        if len(vid_caption) > 1024:
            vid_caption = vid_caption[:1020] + "..."

        raw_bytes = await _download_tiktok_video_bytes(orig_url, fallback_url=download_url, quality=quality)
        if raw_bytes:
            try:
                v_bytes = BytesIO(raw_bytes)
                v_bytes.name = f"TikTok_{label}_{video_id}.mp4"
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=v_bytes,
                    caption=vid_caption,
                    parse_mode=ParseMode.HTML,
                    width=w if w > 0 else None,
                    height=h if h > 0 else None,
                    supports_streaming=True,
                )
            except Exception as err:
                logger.warning(f"Failed to send video bytes for download: {err}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Failed to send {label} video file.",
                    parse_mode=ParseMode.HTML,
                )
        elif download_url:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📥 <b>Download {label}</b>\n\n<a href=\"{html_module.escape(download_url)}\">⬇️ Click here to download</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Download URL for {label} is unavailable.",
                parse_mode=ParseMode.HTML,
            )
    except Exception as err:
        logger.error(f"Error in download callback: {err}")


# ─── Callback: MP3 Audio ─────────────────────────────────────
async def callback_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle MP3 button - delete menu and send MP3 audio file directly."""
    query = update.callback_query
    video_id = query.data.replace("dl_mp3_", "", 1)
    chat_id = query.message.chat_id
    await query.answer("🎵 Preparing MP3 audio...")

    # Delete previous menu directly
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")

    try:
        tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
        if not tiktok_data:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Video data not found. Please resend the TikTok link.",
                parse_mode=ParseMode.HTML,
            )
            return

        music_url = tiktok_data.get("music_url", "")
        music_title = html_module.escape(tiktok_data.get("music_title", "Audio"))
        music_author = html_module.escape(tiktok_data.get("music_author", "TikTok"))

        if music_url:
            sent = False
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/",
                }
                async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
                    resp = await client.get(music_url, headers=headers)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        audio_bytes = BytesIO(resp.content)
                        audio_bytes.name = f"{music_title}.mp3"
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=audio_bytes,
                            title=music_title,
                            performer=music_author,
                            caption=f"🎵 <b>{music_title}</b> - {music_author}",
                            parse_mode=ParseMode.HTML,
                        )
                        sent = True
            except Exception as err:
                logger.warning(f"Failed to send MP3 audio file: {err}")

            if not sent:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎵 <b>MP3 Audio</b>\n🎧 {music_title}\n\n<a href=\"{html_module.escape(music_url)}\">⬇️ Download MP3</a>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ MP3 audio URL is unavailable for this video.",
                parse_mode=ParseMode.HTML,
            )
    except Exception as err:
        logger.error(f"Error in MP3 callback: {err}")


# ─── Callback: Shazam ────────────────────────────────────────
async def callback_shazam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Shazam button - show music info."""
    query = update.callback_query
    video_id = query.data.replace("shazam_", "", 1)
    await query.answer("🔍 Detecting music...")

    tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
    if not tiktok_data:
        await query.message.reply_text(
            "❌ Video data not found. Please resend the TikTok link.",
            parse_mode=ParseMode.HTML,
        )
        return

    music_title = html_module.escape(tiktok_data.get("music_title", "Unknown"))
    music_author = html_module.escape(tiktok_data.get("music_author", "Unknown"))
    music_url = tiktok_data.get("music_url", "")

    msg = (
        f"🔍 <b>Shazam - Music Detection</b>\n\n"
        f"🎵 <b>Title:</b> {music_title}\n"
        f"👤 <b>Artist:</b> {music_author}\n"
    )

    if music_url:
        msg += f"\n<a href=\"{html_module.escape(music_url)}\">🎧 Listen Online</a>"

    await query.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ─── Callback: Preview ───────────────────────────────────────
async def callback_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Preview button - delete menu and send in-app playable video preview."""
    query = update.callback_query
    video_id = query.data.replace("preview_", "", 1)
    chat_id = query.message.chat_id
    await query.answer("📺 Preparing preview...")

    # Delete previous menu directly
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")

    try:
        tiktok_data = context.bot_data.get("video_cache", {}).get(video_id)
        if not tiktok_data:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Video data not found. Please resend the TikTok link.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Use play_url for preview (lower quality / faster load)
        play_url = tiktok_data.get("play_url") or tiktok_data.get("hdplay_url", "")
        original_url = tiktok_data.get("original_url", "")

        if play_url:
            sent = False
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/",
                }
                async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
                    resp = await client.get(play_url, headers=headers)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        v_bytes = BytesIO(resp.content)
                        v_bytes.name = f"preview_{video_id}.mp4"
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=v_bytes,
                            caption=f"▷ <b>Video Preview</b>\n👤 @{html_module.escape(tiktok_data.get('author_username', ''))}",
                            parse_mode=ParseMode.HTML,
                            supports_streaming=True,
                        )
                        sent = True
            except Exception as e:
                logger.warning(f"Failed to send video preview stream: {e}")

            if not sent:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"▷ <b>Preview</b>\n\n<a href=\"{html_module.escape(play_url)}\">▶️ Watch preview</a>\n🔗 <a href=\"{html_module.escape(original_url)}\">Original TikTok link</a>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"▷ <b>Preview</b>\n\n🔗 <a href=\"{html_module.escape(original_url)}\">Open on TikTok</a>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as err:
        logger.error(f"Error in preview callback: {err}")


# ─── Callback Router ─────────────────────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to the appropriate handler."""
    query = update.callback_query
    data = query.data

    if data.startswith("recheck_"):
        await callback_recheck(update, context)
    elif data.startswith("check_"):
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
        await query.answer("❓ Unknown action.")



# ─── Message Handler ─────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all text messages - check if they contain TikTok URLs."""
    text = update.message.text or ""

    if TIKTOK_URL_RE.search(text):
        await handle_tiktok_link(update, context)
    else:
        await update.message.reply_text(
            "🎬 Send a TikTok video link to get started!\n\n"
            "Example:\n"
            "<code>https://www.tiktok.com/@username/video/1234567890</code>",
            parse_mode=ParseMode.HTML,
        )


# ─── Post Init (set bot commands) ────────────────────────────
async def post_init(application) -> None:
    """Set bot commands menu after initialization."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Usage guide"),
        BotCommand("about", "About bot & VQ Score"),
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
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is not set!")
        print("")
        print("Setup steps:")
        print("  1. Open @BotFather on Telegram")
        print("  2. Send /newbot and follow instructions")
        print("  3. Copy your bot token")
        print("  4. Create .env file with:")
        print("     TELEGRAM_BOT_TOKEN=your_token_here")
        print("━" * 50)
        return

    print("━" * 50)
    print("🎬 TikTok Video Analyzer Bot")
    print("━" * 50)
    print("🔄 Starting bot...")

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

    print("✅ Bot is running! Press Ctrl+C to stop.")
    print("━" * 50)

    # Start polling
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
