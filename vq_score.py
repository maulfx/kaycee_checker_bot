"""
Video Quality Score (VQ Score) Calculator.
Produces a 0-100 score based on resolution, bitrate efficiency,
codec modernity, and frame rate.
"""


def calculate_vq_score(
    width: int,
    height: int,
    bitrate_kbps: int,
    codec: str = "h264",
    fps: int | float = 30,
    **kwargs
) -> float:
    """
    Calculate Video Quality Score (0-100).
    
    Scoring breakdown:
    - Resolution:  0-30 points (based on pixel count vs TikTok max 1080p)
    - Bitrate:     0-30 points (bits-per-pixel efficiency)
    - Codec:       0-20 points (modern codec = higher score)
    - Frame Rate:  0-20 points (higher fps = higher score)
    
    Returns:
        float: VQ Score rounded to 2 decimal places
    """
    # Handle parameter swap if callers pass (w, h, br, fps, codec)
    if isinstance(codec, (int, float)) and isinstance(fps, str):
        codec, fps = fps, codec

    try:
        fps_num = float(fps)
    except (ValueError, TypeError):
        fps_num = 30.0

    width = int(width or 0)
    height = int(height or 0)
    bitrate_kbps = int(bitrate_kbps or 0)
    codec = str(codec or "h264")

    score = 0.0

    
    # ─── Resolution Score (max 30) ────────────────────────────
    total_pixels = width * height
    # Reference: TikTok max quality = 1080x1920 = 2,073,600 pixels
    ref_pixels = 2_073_600
    
    if total_pixels > 0:
        res_ratio = min(total_pixels / ref_pixels, 1.5)
        if res_ratio <= 1.0:
            res_score = res_ratio * 28
        else:
            # Bonus for exceeding 1080p but diminishing returns
            res_score = 28 + (res_ratio - 1.0) * 4
        score += min(res_score, 30)
    
    # ─── Bitrate Efficiency Score (max 30) ────────────────────
    if bitrate_kbps > 0 and total_pixels > 0:
        # Calculate bits per pixel per frame (BPP)
        bpp = (bitrate_kbps * 1000) / (total_pixels * max(fps_num, 1.0))
        
        # Ideal BPP ranges for good quality
        # Low: <0.04 (heavy compression), Good: 0.04-0.12, Excellent: 0.12+
        if bpp >= 0.15:
            bitrate_score = 30
        elif bpp >= 0.10:
            bitrate_score = 25 + (bpp - 0.10) * 100  # 25-30
        elif bpp >= 0.06:
            bitrate_score = 18 + (bpp - 0.06) * 175  # 18-25
        elif bpp >= 0.03:
            bitrate_score = 10 + (bpp - 0.03) * 266  # 10-18
        elif bpp >= 0.01:
            bitrate_score = 3 + (bpp - 0.01) * 350   # 3-10
        else:
            bitrate_score = bpp * 300  # 0-3
        
        score += min(bitrate_score, 30)
    
    # ─── Codec Score (max 20) ─────────────────────────────────
    codec_lower = (codec or "").lower()
    
    codec_scores = {
        "av1": 20, "av01": 20, "libaom": 20,
        "h265": 17, "hevc": 17, "hev1": 17, "libx265": 17,
        "vp9": 15, "vp09": 15, "libvpx-vp9": 15,
        "h264": 12, "avc": 12, "avc1": 12, "libx264": 12,
        "vp8": 8, "libvpx": 8,
        "mpeg4": 5, "mp4v": 5,
        "mpeg2": 3, "mpeg1": 2,
    }
    
    codec_score = 0
    for key, val in codec_scores.items():
        if key in codec_lower:
            codec_score = val
            break
    
    # If codec is unknown but video exists, give base score
    if codec_score == 0 and total_pixels > 0:
        codec_score = 8  # Assume basic codec
    
    score += codec_score
    
    # ─── Frame Rate Score (max 20) ────────────────────────────
    if fps_num >= 60:
        fps_score = 20
    elif fps_num >= 50:
        fps_score = 17
    elif fps_num >= 30:
        fps_score = 14
    elif fps_num >= 25:
        fps_score = 11
    elif fps_num >= 24:
        fps_score = 9
    elif fps_num >= 15:
        fps_score = 5
    elif fps_num > 0:
        fps_score = 2
    else:
        fps_score = 0
    
    score += fps_score
    
    return round(min(score, 100), 2)


def get_vq_grade(score: float) -> str:
    """Convert VQ Score to a letter grade with emoji."""
    if score >= 90:
        return "🟢 Excellent (A+)"
    elif score >= 80:
        return "🟢 Very Good (A)"
    elif score >= 70:
        return "🟡 Good (B)"
    elif score >= 60:
        return "🟡 Fair (C)"
    elif score >= 50:
        return "🟠 Below Average (D)"
    elif score >= 40:
        return "🔴 Poor (E)"
    else:
        return "🔴 Very Poor (F)"


def get_vq_bar(score: float, length: int = 10) -> str:
    """Create a visual progress bar for VQ Score."""
    filled = round(score / 100 * length)
    empty = length - filled
    
    if score >= 70:
        fill_char = "🟩"
    elif score >= 50:
        fill_char = "🟨"
    else:
        fill_char = "🟥"
    
    return fill_char * filled + "⬛" * empty
