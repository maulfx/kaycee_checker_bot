import json
import asyncio
import logging
import shutil
import yt_dlp
from config import FFPROBE_PATH

logger = logging.getLogger(__name__)


def _clean_codec(codec: str) -> str:
    """Normalize codec string to clean identifier."""
    c = str(codec or "").lower()
    if "h265" in c or "hevc" in c or "hvc1" in c or "bytevc1" in c:
        return "hevc"
    if "h264" in c or "avc" in c:
        return "h264"
    if "av1" in c or "av01" in c:
        return "av1"
    if "vp9" in c or "vp09" in c:
        return "vp9"
    return codec if codec else "h264"


def _is_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system."""
    return shutil.which(FFPROBE_PATH) is not None


def _extract_ytdlp_sync(url: str) -> dict | None:
    """
    Synchronously extract detailed format and quality info using yt-dlp.
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
            return info
    except Exception as e:
        logger.warning(f"yt-dlp extraction failed for {url}: {e}")
        return None


async def extract_all_qualities_ytdlp(url: str) -> dict:
    """
    Extract all adaptive video qualities (1080p, 720p, 540p at 60/30 fps, codecs, sizes)
    using yt-dlp asynchronously.
    """
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, _extract_ytdlp_sync, url)
    if not info:
        return {}

    formats = info.get("formats", [])
    parsed_streams = []
    
    for f in formats:
        # Skip pure audio tracks unless analyzing audio
        vcodec = f.get("vcodec")
        if vcodec == "none" or not vcodec:
            continue
            
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        fps = int(round(f.get("fps") or 30))
        tbr = f.get("tbr") or f.get("vbr") or 0
        bitrate_kbps = int(tbr) if tbr > 0 else 0
        bitrate_bps = bitrate_kbps * 1000
        size_bytes = int(f.get("filesize") or f.get("filesize_approx") or 0)
        stream_url = f.get("url", "")
        format_id = f.get("format_id", "")
        format_note = f.get("format_note", "")
        cleaned_codec = _clean_codec(vcodec)
        
        max_d = max(w, h)
        res_label = f"{max_d}p{fps}" if max_d > 0 else "Unknown"

        gear_name = format_id or format_note or f"{max_d}p"

        parsed_streams.append({
            "gear": gear_name,
            "format_id": format_id,
            "codec": cleaned_codec,
            "raw_codec": vcodec,
            "bitrate": bitrate_bps,
            "bitrate_kbps": bitrate_kbps,
            "width": w,
            "height": h,
            "fps": fps,
            "data_size": size_bytes,
            "url": stream_url,
            "quality_label": res_label,
            "protocol": f.get("protocol", ""),
            "acodec": f.get("acodec", ""),
            "dynamic_range": f.get("dynamic_range", "SDR"),
        })

    # Sort descending by resolution (pixels), then fps, then bitrate
    parsed_streams.sort(
        key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("fps", 0), x.get("bitrate", 0)),
        reverse=True
    )

    best_stream = parsed_streams[0] if parsed_streams else {}
    best_w = best_stream.get("width") or int(info.get("width") or 0)
    best_h = best_stream.get("height") or int(info.get("height") or 0)
    best_fps = best_stream.get("fps") or int(round(info.get("fps") or 30))
    best_bitrate = best_stream.get("bitrate_kbps") or int(info.get("tbr") or info.get("vbr") or 0)
    best_codec = best_stream.get("codec") or _clean_codec(info.get("vcodec", "h264"))
    best_size = best_stream.get("data_size") or int(info.get("filesize") or info.get("filesize_approx") or 0)

    return {
        "title": info.get("title", ""),
        "duration": float(info.get("duration") or 0),
        "width": best_w,
        "height": best_h,
        "fps": best_fps,
        "bitrate_kbps": best_bitrate,
        "codec": best_codec,
        "file_size_bytes": best_size,
        "play_url": best_stream.get("url") or info.get("url", ""),
        "streams": parsed_streams,
        "browser_quality": _calculate_quality_tier(best_w, best_h, 30, "browser"),
        "phone_quality": _calculate_quality_tier(best_w, best_h, best_fps, "phone"),
        "ytdlp_available": True,
    }


async def analyze_video(video_url: str, fallback_data: dict = None) -> dict:
    """
    Analyze video quality using yt-dlp (deep stream/format extractor) and ffprobe.
    
    Extracts all adaptive qualities (1080p, 720p, 540p at 60/30fps),
    codecs (HEVC, H.264, AV1), bitrates, frame rates, and sizes.
    """
    fallback_data = fallback_data or {}
    
    w = fallback_data.get("width", 0)
    h = fallback_data.get("height", 0)
    br = fallback_data.get("bitrate_kbps", 0)
    cd = fallback_data.get("codec", "h264")
    orig_url = fallback_data.get("original_url") or fallback_data.get("url") or video_url
    
    result = {
        "width": w,
        "height": h,
        "codec": cd,
        "codec_long": cd,
        "profile": "",
        "bitrate_kbps": br,
        "fps": fallback_data.get("fps", 30),
        "duration": fallback_data.get("duration", 0),
        "file_size_bytes": fallback_data.get("size", 0),
        "audio_codec": "",
        "audio_bitrate_kbps": 0,
        "audio_sample_rate": 0,
        "format_name": "mp4",
        "ffprobe_available": False,
        "ytdlp_available": False,
        "streams": fallback_data.get("bitrate_info", []),
        # Quality tiers
        "browser_quality": fallback_data.get("browser_quality") or _calculate_quality_tier(w, h, 30, "browser"),
        "phone_quality": fallback_data.get("phone_quality") or _calculate_quality_tier(w, h, 30, "phone"),
    }
    
    # ─── 1. Primary Method: yt-dlp Deep Format Extractor ───
    if orig_url:
        try:
            ytdlp_res = await extract_all_qualities_ytdlp(orig_url)
            if ytdlp_res and ytdlp_res.get("streams"):
                result["ytdlp_available"] = True
                if ytdlp_res.get("width"):
                    result["width"] = ytdlp_res["width"]
                if ytdlp_res.get("height"):
                    result["height"] = ytdlp_res["height"]
                if ytdlp_res.get("fps"):
                    result["fps"] = ytdlp_res["fps"]
                if ytdlp_res.get("bitrate_kbps"):
                    result["bitrate_kbps"] = ytdlp_res["bitrate_kbps"]
                if ytdlp_res.get("codec"):
                    result["codec"] = ytdlp_res["codec"]
                    result["codec_long"] = ytdlp_res["codec"]
                if ytdlp_res.get("file_size_bytes"):
                    result["file_size_bytes"] = ytdlp_res["file_size_bytes"]
                if ytdlp_res.get("duration"):
                    result["duration"] = ytdlp_res["duration"]
                
                result["streams"] = ytdlp_res["streams"]
                result["browser_quality"] = ytdlp_res["browser_quality"]
                result["phone_quality"] = ytdlp_res["phone_quality"]
                logger.info(f"yt-dlp extracted {len(ytdlp_res['streams'])} quality streams successfully")
        except Exception as e:
            logger.warning(f"yt-dlp analysis encountered an error: {e}")

    # ─── 2. Secondary Method: ffprobe Deep Stream Inspection ───
    target_probe_url = video_url or (result["streams"][0]["url"] if result.get("streams") else "")
    if target_probe_url and _is_ffprobe_available():
        result["ffprobe_available"] = True
        try:
            cmd = [
                FFPROBE_PATH,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                target_probe_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=20.0
            )
            
            if process.returncode == 0:
                probe_data = json.loads(stdout.decode())
                video_stream = None
                audio_stream = None
                for stream in probe_data.get("streams", []):
                    if stream.get("codec_type") == "video" and video_stream is None:
                        video_stream = stream
                    elif stream.get("codec_type") == "audio" and audio_stream is None:
                        audio_stream = stream
                
                if video_stream:
                    if video_stream.get("width") and not result["width"]:
                        result["width"] = int(video_stream.get("width"))
                    if video_stream.get("height") and not result["height"]:
                        result["height"] = int(video_stream.get("height"))
                    if video_stream.get("codec_name"):
                        result["codec"] = _clean_codec(video_stream.get("codec_name"))
                        result["codec_long"] = video_stream.get("codec_long_name", result["codec"])
                    result["profile"] = video_stream.get("profile", "")
                    
                    fps_str = video_stream.get("r_frame_rate", "30/1")
                    try:
                        num, den = fps_str.split("/")
                        parsed_fps = round(int(num) / int(den))
                        if parsed_fps > 0:
                            result["fps"] = parsed_fps
                    except (ValueError, ZeroDivisionError):
                        pass
                    
                    bitrate = video_stream.get("bit_rate")
                    if bitrate and int(bitrate) > 0:
                        result["bitrate_kbps"] = int(bitrate) // 1000
                
                if audio_stream:
                    result["audio_codec"] = audio_stream.get("codec_name", "")
                    audio_br = audio_stream.get("bit_rate")
                    if audio_br:
                        result["audio_bitrate_kbps"] = int(audio_br) // 1000
                    result["audio_sample_rate"] = int(audio_stream.get("sample_rate", 0))
                
                format_info = probe_data.get("format", {})
                result["format_name"] = format_info.get("format_name", "mp4")
                if format_info.get("duration") and not result["duration"]:
                    result["duration"] = float(format_info.get("duration"))
                if result["bitrate_kbps"] == 0 and format_info.get("bit_rate"):
                    result["bitrate_kbps"] = int(format_info.get("bit_rate")) // 1000
                if result["file_size_bytes"] == 0 and format_info.get("size"):
                    result["file_size_bytes"] = int(format_info.get("size"))
                    
        except Exception as e:
            logger.warning(f"ffprobe execution warning: {e}")

    # Re-calculate quality tiers with the most accurate resolution and FPS
    result["browser_quality"] = _calculate_quality_tier(result["width"], result["height"], 30, "browser")
    result["phone_quality"] = _calculate_quality_tier(result["width"], result["height"], result["fps"], "phone")
    
    return result


def _calculate_quality_tier(width: int, height: int, fps: int = 30, device: str = "phone") -> str:
    """Calculate display quality tier string (e.g., '1080p60', '720p60')."""
    max_dim = max(width, height)
    
    if max_dim >= 2160:
        res = "2160p"
    elif max_dim >= 1440:
        res = "1440p"
    elif max_dim >= 1080:
        res = "1080p"
    elif max_dim >= 720:
        res = "720p"
    elif max_dim >= 480:
        res = "480p"
    elif max_dim >= 360:
        res = "360p"
    else:
        res = f"{max_dim}p" if max_dim > 0 else "Unknown"
    
    display_fps = 60 if fps >= 50 else 30
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
