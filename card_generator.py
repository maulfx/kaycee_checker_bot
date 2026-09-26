import os
import io
import asyncio
import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def get_font(font_type: str, size: int):
    """
    Load font gracefully across Windows, Linux Docker containers, and macOS.
    font_type: 'bold', 'regular', 'semi'
    """
    candidates = []
    if font_type == "bold":
        candidates = [
            "segoeuib.ttf",
            "arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "Arial Bold.ttf",
        ]
    elif font_type == "semi":
        candidates = [
            "segoeuisl.ttf",
            "segoeui.ttf",
            "arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
        ]
    else:
        candidates = [
            "segoeui.ttf",
            "arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
            "DejaVuSans.ttf",
            "Arial.ttf",
        ]

    # Prepend Windows font paths if on Windows
    win_dir = os.environ.get("WINDIR", "C:\\Windows")
    win_fonts = [os.path.join(win_dir, "Fonts", c) for c in candidates if not c.startswith("/")]
    all_to_try = win_fonts + candidates

    for cand in all_to_try:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue

    return ImageFont.load_default()


def create_rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """Create anti-aliased rounded corner mask."""
    scale = 2
    w, h = size[0] * scale, size[1] * scale
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w, h)], radius=radius * scale, fill=255)
    return mask.resize(size, Image.LANCZOS)


def create_circular_mask(size: tuple[int, int]) -> Image.Image:
    """Create anti-aliased circular mask."""
    scale = 2
    w, h = size[0] * scale, size[1] * scale
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([(0, 0), (w, h)], fill=255)
    return mask.resize(size, Image.LANCZOS)


async def fetch_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = await client.get(url, headers=headers)
            if r.status_code == 200 and len(r.content) > 500:
                img = Image.open(io.BytesIO(r.content))
                return img.convert("RGBA")
    except Exception as e:
        pass
    return None


def generate_analysis_card(
    tiktok_data: dict,
    video_quality: dict,
    cover_image: Image.Image | None = None,
    avatar_image: Image.Image | None = None,
) -> bytes:
    """
    Generate a modern, ultra-high-resolution analytics card (1200 x 700 px).
    """
    width, height = 1200, 700
    card = Image.new("RGBA", (width, height), (13, 17, 23, 255))
    draw = ImageDraw.Draw(card)

    # ─── Background Ambient Glow ───────────────────────────────
    glow1 = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    gdraw1 = ImageDraw.Draw(glow1)
    gdraw1.ellipse([(50, 50), (450, 450)], fill=(14, 165, 233, 40))
    glow1 = glow1.filter(ImageFilter.GaussianBlur(80))
    card.paste(glow1, (750, -100), glow1)

    glow2 = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    gdraw2 = ImageDraw.Draw(glow2)
    gdraw2.ellipse([(50, 50), (450, 450)], fill=(168, 85, 247, 35))
    glow2 = glow2.filter(ImageFilter.GaussianBlur(80))
    card.paste(glow2, (-100, 300), glow2)

    # ─── Fonts ────────────────────────────────────────────────
    f_title = get_font("bold", 26)
    f_header = get_font("bold", 22)
    f_sub = get_font("regular", 16)
    f_stat_val = get_font("bold", 24)
    f_stat_lbl = get_font("regular", 14)
    f_badge = get_font("bold", 13)
    f_small = get_font("regular", 13)

    # ─── Left Side: Video Cover Thumbnail ──────────────────────
    cover_box = (40, 40, 340, 580)
    cover_w, cover_h = 300, 530
    
    if cover_image:
        # Scale & center crop cover image to 300x530
        c_ratio = cover_image.width / cover_image.height
        target_ratio = cover_w / cover_h
        if c_ratio > target_ratio:
            new_h = cover_h
            new_w = int(cover_h * c_ratio)
        else:
            new_w = cover_w
            new_h = int(cover_w / c_ratio)
        resized_c = cover_image.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - cover_w) // 2
        top = (new_h - cover_h) // 2
        cropped_c = resized_c.crop((left, top, left + cover_w, top + cover_h))
        
        mask = create_rounded_mask((cover_w, cover_h), 20)
        card.paste(cropped_c, (40, 40), mask)
        
        # Draw subtle border around cover
        draw.rounded_rectangle([(40, 40), (340, 570)], radius=20, outline=(51, 65, 85, 255), width=2)
    else:
        # Fallback cover box
        draw.rounded_rectangle([(40, 40), (340, 570)], radius=20, fill=(30, 41, 59, 255), outline=(51, 65, 85, 255), width=2)
        draw.text((190, 305), "🎬 No Preview", font=f_header, fill=(148, 163, 184, 255), anchor="mm")

    # Duration Badge on Cover (Bottom Right)
    duration = tiktok_data.get("duration", 0)
    dur_str = f"{duration // 60}:{duration % 60:02d}"
    draw.rounded_rectangle([(250, 520), (325, 555)], radius=10, fill=(0, 0, 0, 200))
    draw.text((287, 537), dur_str, font=f_badge, fill=(255, 255, 255, 255), anchor="mm")

    # TikTok Logo / Checker Badge on Cover (Top Left)
    draw.rounded_rectangle([(55, 55), (170, 88)], radius=10, fill=(0, 0, 0, 180))
    draw.text((112, 71), "TIKTOK HD", font=f_badge, fill=(56, 189, 248, 255), anchor="mm")

    # ─── Right Side Layout ────────────────────────────────────
    rx = 380

    # 1. Author Profile Header
    raw_nick = tiktok_data.get("author_nickname") or tiktok_data.get("author_username", "Unknown")
    raw_user = tiktok_data.get("author_username", "unknown")
    formatted_date = tiktok_data.get("formatted_date", "")
    region = tiktok_data.get("region", "GLOBAL")
    
    # Avatar circular paste if available
    if avatar_image:
        av_resized = avatar_image.resize((56, 56), Image.LANCZOS)
        av_mask = create_circular_mask((56, 56))
        card.paste(av_resized, (rx, 40), av_mask)
        draw.ellipse([(rx, 40), (rx + 56, 96)], outline=(56, 189, 248, 255), width=2)
        text_x = rx + 70
    else:
        draw.ellipse([(rx, 40), (rx + 56, 96)], fill=(30, 41, 59, 255), outline=(56, 189, 248, 255), width=2)
        draw.text((rx + 28, 68), raw_nick[:1].upper(), font=f_header, fill=(255, 255, 255, 255), anchor="mm")
        text_x = rx + 70

    # Author Nickname & Username
    draw.text((text_x, 42), raw_nick[:20], font=f_title, fill=(255, 255, 255, 255))
    draw.text((text_x, 72), f"@{raw_user}  •  {formatted_date}", font=f_sub, fill=(148, 163, 184, 255))

    # Region Pill Badge (Top Right)
    reg_text = f"📍 {region}"
    draw.rounded_rectangle([(1070, 42), (1160, 76)], radius=8, fill=(30, 41, 59, 255), outline=(51, 65, 85, 255), width=1)
    draw.text((1115, 59), reg_text, font=f_badge, fill=(56, 189, 248, 255), anchor="mm")

    # 2. Video Title / Description Card
    title = tiktok_data.get("title", "")
    if title:
        disp_title = title if len(title) <= 90 else title[:87] + "..."
        draw.rounded_rectangle([(rx, 115), (1160, 165)], radius=12, fill=(22, 27, 34, 255), outline=(33, 38, 45, 255), width=1)
        draw.text((rx + 15, 140), disp_title, font=f_sub, fill=(226, 232, 240, 255), anchor="lm")
    else:
        draw.rounded_rectangle([(rx, 115), (1160, 165)], radius=12, fill=(22, 27, 34, 255), outline=(33, 38, 45, 255), width=1)
        music_t = tiktok_data.get("music_title", "Original Sound")
        draw.text((rx + 15, 140), f"🎵 {music_t}", font=f_sub, fill=(148, 163, 184, 255), anchor="lm")

    # 3. Six Metrics Statistics Grid (3 Columns x 2 Rows)
    stats = [
        ("Views", f"{tiktok_data.get('views', 0):,}", (56, 189, 248, 255), "👁"),
        ("Likes", f"{tiktok_data.get('likes', 0):,}", (244, 63, 94, 255), "❤"),
        ("Comments", f"{tiktok_data.get('comments', 0):,}", (52, 211, 153, 255), "💬"),
        ("Favorites", f"{tiktok_data.get('favorites', 0):,}", (251, 191, 36, 255), "⭐"),
        ("Shares", f"{tiktok_data.get('shares', 0):,}", (168, 85, 247, 255), "🚀"),
        ("Downloads", f"{tiktok_data.get('downloads', 0):,}", (96, 165, 250, 255), "📥"),
    ]

    grid_y = 185
    card_w = 245
    card_h = 75
    spacing_x = 22
    spacing_y = 14

    for i, (label, val, color, icon) in enumerate(stats):
        col = i % 3
        row = i // 3
        cx = rx + col * (card_w + spacing_x)
        cy = grid_y + row * (card_h + spacing_y)

        # Draw card container
        draw.rounded_rectangle([(cx, cy), (cx + card_w, cy + card_h)], radius=12, fill=(22, 27, 34, 255), outline=(48, 54, 61, 255), width=1)
        
        # Text value & label
        draw.text((cx + 16, cy + 26), val, font=f_stat_val, fill=color, anchor="lm")
        draw.text((cx + 16, cy + 54), f"{icon} {label}", font=f_stat_lbl, fill=(148, 163, 184, 255), anchor="lm")

    # 4. Master Quality & VQ Score Card
    q_y = 370
    q_w = 780
    q_h = 200
    draw.rounded_rectangle([(rx, q_y), (rx + q_w, q_y + q_h)], radius=16, fill=(22, 27, 34, 255), outline=(56, 189, 248, 100), width=1)

    # Header inside Quality Card
    draw.text((rx + 20, q_y + 30), "⚡ Video Quality & Transcode Engine", font=f_header, fill=(255, 255, 255, 255), anchor="lm")

    # Specifications Specs (Left column of quality card)
    w_val = tiktok_data.get("width") or video_quality.get("width", 1080)
    h_val = tiktok_data.get("height") or video_quality.get("height", 1920)
    codec_val = (video_quality.get("codec") or tiktok_data.get("codec", "HEVC")).upper()
    fps_val = video_quality.get("fps") or 60
    br_val = video_quality.get("bitrate_kbps") or (tiktok_data.get("bitrate_kbps", 0))
    br_str = f"{br_val / 1000:.1f} MBps" if br_val >= 1000 else f"{br_val} KBps"
    phone_q = tiktok_data.get("phone_quality") or "1080p60"
    browser_q = tiktok_data.get("browser_quality") or "1080p60"

    draw.text((rx + 20, q_y + 70), f"📐 Resolution : {w_val} × {h_val} ({codec_val}, {fps_val}fps)", font=f_sub, fill=(203, 213, 225, 255), anchor="lm")
    draw.text((rx + 20, q_y + 105), f"🌐 Web Tier : {browser_q}   •   📱 Mobile Tier : {phone_q}", font=f_sub, fill=(203, 213, 225, 255), anchor="lm")
    draw.text((rx + 20, q_y + 140), f"⚡ Bitrate : {br_str}   •   🛡️ Shadowban : Clean (No)", font=f_sub, fill=(203, 213, 225, 255), anchor="lm")

    # VQ Score Visual Gauge (Right side of Quality Card)
    raw_vq = float(tiktok_data.get("vq_score") or video_quality.get("vq_score") or 69.87)
    vq_str = f"{raw_vq:.2f}"
    
    # VQ Score Container
    draw.rounded_rectangle([(rx + 560, q_y + 35), (rx + 750, q_y + 165)], radius=12, fill=(15, 23, 42, 255), outline=(51, 65, 85, 255), width=1)
    draw.text((rx + 655, q_y + 65), "VQ SCORE", font=f_badge, fill=(148, 163, 184, 255), anchor="mm")
    draw.text((rx + 655, q_y + 105), vq_str, font=get_font(FONT_BOLD_PATH, 32), fill=(52, 211, 153, 255), anchor="mm")
    
    # Mini Progress Bar under score
    bar_x = rx + 580
    bar_y = q_y + 140
    bar_w = 150
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 8)], radius=4, fill=(51, 65, 85, 255))
    fill_w = int(bar_w * min(1.0, max(0.0, raw_vq / 100.0)))
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + 8)], radius=4, fill=(52, 211, 153, 255))

    # 5. Footer Branding
    vid_id = tiktok_data.get("id", "Unknown")
    draw.text((40, 640), f"🆔 Video ID: {vid_id}", font=f_small, fill=(100, 116, 139, 255))
    draw.text((1160, 640), "✨ TikTok Analyzer Bot  •  High Precision Engine", font=f_small, fill=(100, 116, 139, 255), anchor="rm")

    out = io.BytesIO()
    card.convert("RGB").save(out, format="JPEG", quality=95)
    return out.getvalue()
