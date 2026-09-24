"""
Video Quality Analyzer module.
Uses ffprobe to extract detailed video quality information
(codec, bitrate, resolution, frame rate, etc.)
Falls back gracefully to extracted API metadata if ffprobe is unavailable.
"""

import json
import asyncio
import logging
import shutil
from config import FFPROBE_PATH

logger = logging.getLogger(__name__)


def _is_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system."""
    return shutil.which(FFPROBE_PATH) is not None


async def analyze_video(video_url: str, fallback_data: dict = None) -> dict:
    """
    Analyze video quality using ffprobe.
    
    Runs ffprobe on the video URL (supports HTTP URLs directly)
    and extracts codec, bitrate, resolution, fps, and audio info.
    
    Falls back to extracted API data if ffprobe is unavailable or fails.
    """
    fallback_data = fallback_data or {}
    
    w = fallback_data.get("width", 0)
    h = fallback_data.get("height", 0)
    br = fallback_data.get("bitrate_kbps", 0)
    cd = fallback_data.get("codec", "h264")
    
    result = {
        "width": w,
        "height": h,
        "codec": cd,
        "codec_long": cd,
        "profile": "",
        "bitrate_kbps": br,
        "fps": 30,
        "duration": fallback_data.get("duration", 0),
        "file_size_bytes": 0,
        "audio_codec": "",
        "audio_bitrate_kbps": 0,
        "audio_sample_rate": 0,
        "format_name": "mp4",
        "ffprobe_available": False,
        # Quality tiers
        "browser_quality": fallback_data.get("browser_quality") or _calculate_quality_tier(w, h, 30, "browser"),
        "phone_quality": fallback_data.get("phone_quality") or _calculate_quality_tier(w, h, 30, "phone"),
    }
    
    if not video_url:
        logger.warning("No video URL provided for analysis")
        return result
    
    if not _is_ffprobe_available():
        logger.warning("ffprobe not found. Using API metadata for video quality analysis.")
        return result
    
    result["ffprobe_available"] = True
    
    try:
        # Run ffprobe on the URL directly (no download needed)
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            video_url
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30.0
        )
        
        if process.returncode != 0:
            logger.warning(f"ffprobe failed (code {process.returncode}), using fallback metadata")
            return result
        
        probe_data = json.loads(stdout.decode())
        
        # Extract video stream info
        video_stream = None
        audio_stream = None
        
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = stream
        
        # Parse video stream
        if video_stream:
            if video_stream.get("width"):
                result["width"] = int(video_stream.get("width"))
            if video_stream.get("height"):
                result["height"] = int(video_stream.get("height"))
            if video_stream.get("codec_name"):
                result["codec"] = video_stream.get("codec_name")
                result["codec_long"] = video_stream.get("codec_long_name", result["codec"])
            result["profile"] = video_stream.get("profile", "")
            
            # Parse FPS from r_frame_rate (e.g., "30/1" or "30000/1001")
            fps_str = video_stream.get("r_frame_rate", "30/1")
            try:
                num, den = fps_str.split("/")
                result["fps"] = round(int(num) / int(den))
            except (ValueError, ZeroDivisionError):
                result["fps"] = 30
            
            # Parse bitrate
            bitrate = video_stream.get("bit_rate")
            if bitrate:
                result["bitrate_kbps"] = int(bitrate) // 1000
        
        # Parse audio stream
        if audio_stream:
            result["audio_codec"] = audio_stream.get("codec_name", "")
            audio_br = audio_stream.get("bit_rate")
            if audio_br:
                result["audio_bitrate_kbps"] = int(audio_br) // 1000
            result["audio_sample_rate"] = int(audio_stream.get("sample_rate", 0))
        
        # Parse format info
        format_info = probe_data.get("format", {})
        result["format_name"] = format_info.get("format_name", "mp4")
        if format_info.get("duration"):
            result["duration"] = float(format_info.get("duration"))
        
        # Overall bitrate from format (if not from stream)
        if result["bitrate_kbps"] == 0:
            format_bitrate = format_info.get("bit_rate")
            if format_bitrate:
                result["bitrate_kbps"] = int(format_bitrate) // 1000
        
        # File size
        file_size = format_info.get("size")
        if file_size:
            result["file_size_bytes"] = int(file_size)
        
        # Recalculate quality tiers
        result["browser_quality"] = _calculate_quality_tier(
            result["width"], result["height"], result["fps"], "browser"
        )
        result["phone_quality"] = _calculate_quality_tier(
            result["width"], result["height"], result["fps"], "phone"
        )
        
    except asyncio.TimeoutError:
        logger.error("ffprobe timed out, using fallback metadata")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ffprobe output: {e}")
    except Exception as e:
        logger.error(f"Error analyzing video: {e}")
    
    return result


def _calculate_quality_tier(width: int, height: int, fps: int, device: str) -> str:
    """Calculate display quality tier string (e.g., '1080p30', '720p60')."""
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
        res = f"{max_dim}p" if max_dim > 0 else "Unknown"
    
    if device == "phone":
        display_fps = 60 if fps >= 50 else 30
    else:
        display_fps = 30
    
    return f"{res}{display_fps}" if res != "Unknown" else "Unknown"


def format_bitrate(kbps: int) -> str:
    """Format bitrate into human-readable string."""
    if kbps >= 1000:
        return f"{kbps / 1000:.1f} MBps"
    return f"{kbps} KBps"


def format_file_size(bytes_size: int) -> str:
    """Format file size into human-readable string."""
    if bytes_size == 0:
        return "Unknown"
    
    if bytes_size >= 1073741824:  # GB
        return f"{bytes_size / 1073741824:.1f} GB"
    elif bytes_size >= 1048576:  # MB
        return f"{bytes_size / 1048576:.1f} MB"
    elif bytes_size >= 1024:  # KB
        return f"{bytes_size / 1024:.1f} KB"
    return f"{bytes_size} B"
