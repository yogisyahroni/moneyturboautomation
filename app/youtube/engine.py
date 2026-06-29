"""
YouTube Engine — Search, Download, dan Scene Detection
Menggunakan youtube-search-python + yt-dlp + scenedetect (semua gratis)
"""
import os
import re
import json
import subprocess
from typing import List, Dict, Optional, Tuple
from loguru import logger

# ─── YouTube Search ──────────────────────────────────────────────────

def search_youtube(query: str, max_results: int = 5, language: str = "id") -> List[Dict]:
    """
    Cari video di YouTube berdasarkan kata kunci
    
    Returns:
        List of {title, url, duration, channel, description}
    """
    try:
        from youtube_search import YoutubeSearch
    except ImportError:
        logger.error("youtube-search-python not installed. Install with: pip install youtube-search-python")
        return []
    
    try:
        results = YoutubeSearch(query, max_results=max_results).to_dict()
        videos = []
        for r in results:
            # Convert duration "5:30" → detik
            dur_str = r.get("duration", "0:00")
            parts = list(map(int, dur_str.split(":")))
            duration_secs = sum(p * 60 ** (len(parts) - 1 - i) for i, p in enumerate(parts))
            
            videos.append({
                "title": r.get("title", ""),
                "url": f"https://youtube.com{r.get('url_suffix', '')}" if r.get("url_suffix") else "",
                "duration": duration_secs,
                "duration_str": dur_str,
                "channel": r.get("channel", ""),
                "thumbnail": r.get("thumbnails", [""])[0] if r.get("thumbnails") else "",
                "description": r.get("long_desc", "")[:200],
            })
        
        logger.success(f"YouTube search: found {len(videos)} videos for '{query}'")
        return videos
    except Exception as e:
        logger.error(f"YouTube search failed: {e}")
        return []


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats"""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_video_info(url: str) -> Optional[Dict]:
    """
    Dapatkan info video YouTube via yt-dlp (tanpa download)
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return {
                "title": data.get("title", ""),
                "duration": data.get("duration", 0),
                "channel": data.get("channel", ""),
                "description": data.get("description", "")[:500],
                "tags": data.get("tags", []),
                "categories": data.get("categories", []),
                "webpage_url": data.get("webpage_url", ""),
            }
        else:
            logger.warning(f"yt-dlp info failed: {result.stderr[:200]}")
            return None
    except Exception as e:
        logger.warning(f"yt-dlp info error: {e}")
        return None


# ─── YouTube Download ────────────────────────────────────────────────

def download_video(url: str, output_dir: str) -> Optional[str]:
    """
    Download video YouTube via yt-dlp
    
    Args:
        url: YouTube URL
        output_dir: Directory untuk simpan video
    
    Returns:
        Path to downloaded file, or None if failed
    """
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        logger.info(f"⬇️  Downloading: {url}")
        output_template = os.path.join(output_dir, "%(title).100s.%(ext)s")
        
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
                "--merge-output-format", "mp4",
                "-o", output_template,
                "--no-playlist",
                "--quiet",
                url,
            ],
            capture_output=True, text=True, timeout=600
        )
        
        if result.returncode == 0:
            # Find the downloaded file
            for f in os.listdir(output_dir):
                if f.endswith(".mp4"):
                    path = os.path.join(output_dir, f)
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    logger.success(f"✅ Downloaded: {f} ({size_mb:.1f} MB)")
                    return path
        else:
            logger.error(f"yt-dlp failed: {result.stderr[:300]}")
            return None
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None


def download_video_by_id(video_id: str, output_dir: str) -> Optional[str]:
    """Download video by YouTube ID"""
    url = f"https://youtube.com/watch?v={video_id}"
    return download_video(url, output_dir)


# ─── Scene Detection ─────────────────────────────────────────────────

def detect_scenes(video_path: str, threshold: float = 20.0) -> List[Dict]:
    """
    Deteksi scene perubahan dalam video pake PySceneDetect
    
    Args:
        video_path: Path ke file video
        threshold: Sensitivitas deteksi scene (makin kecil makin sensitif)
    
    Returns:
        List of {start_time, end_time, duration}
    """
    try:
        from scenedetect import detect, ContentDetector, split_video_ffmpeg
        
        logger.info(f"🎬 Detecting scenes in: {os.path.basename(video_path)}")
        
        scene_list = detect(video_path, ContentDetector(threshold=threshold))
        
        scenes = []
        for i, scene in enumerate(scene_list):
            start = scene[0].get_seconds()
            end = scene[1].get_seconds()
            scenes.append({
                "index": i,
                "start_time": start,
                "end_time": end,
                "duration": end - start,
                "start_ts": str(scene[0]),
                "end_ts": str(scene[1]),
            })
        
        logger.success(f"Found {len(scenes)} scenes in video")
        return scenes
    except ImportError:
        logger.warning("scenedetect not installed. Install with: pip install scenedetect")
        return _detect_scenes_ffmpeg(video_path, threshold)
    except Exception as e:
        logger.error(f"Scene detection failed: {e}")
        return []


def _detect_scenes_ffmpeg(video_path: str, threshold: float = 0.3) -> List[Dict]:
    """
    Fallback scene detection pake ffmpeg (tanpa scenedetect)
    """
    try:
        logger.info("Using ffmpeg scene detection (fallback)")
        result = subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-filter:v", f"select='gt(scene,{threshold})',showinfo",
                "-f", "null", "-"
            ],
            capture_output=True, text=True, timeout=300
        )
        
        scenes = []
        times = []
        # Parse showinfo output
        for line in result.stderr.split("\n"):
            m = re.search(r"pts_time:([\d.]+)", line)
            if m:
                times.append(float(m.group(1)))
        
        prev = 0.0
        for i, t in enumerate(times):
            scenes.append({
                "index": i,
                "start_time": prev,
                "end_time": t,
                "duration": t - prev,
                "start_ts": f"{prev:.1f}s",
                "end_ts": f"{t:.1f}s",
            })
            prev = t
        
        # Last scene to end
        scenes.append({
            "index": len(scenes),
            "start_time": prev,
            "end_time": 0,  # unknown
            "duration": 0,
            "start_ts": f"{prev:.1f}s",
            "end_ts": "end",
        })
        
        logger.success(f"Found {len(scenes)} scenes (ffmpeg fallback)")
        return scenes
    except Exception as e:
        logger.error(f"FFmpeg scene detection failed: {e}")
        return []


def extract_scene_clips(video_path: str, scenes: List[Dict], output_dir: str, 
                        min_duration: float = 3.0, max_duration: float = 15.0) -> List[Dict]:
    """
    Ekstrak scene-scene jadi file terpisah
    
    Args:
        video_path: Source video
        scenes: List of scene info
        output_dir: Output directory
        min_duration: Minimal durasi scene (detik), skip yang lebih pendek
        max_duration: Maksimal durasi scene
        
    Returns:
        List of {scene_index, path, duration}
    """
    os.makedirs(output_dir, exist_ok=True)
    clips = []
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    
    for scene in scenes:
        duration = scene.get("duration", 0)
        if duration < min_duration:
            continue
        if max_duration and duration > max_duration:
            duration = max_duration
        
        start = scene["start_time"]
        end = start + min(duration, max_duration) if max_duration else scene["end_time"]
        
        output_path = os.path.join(output_dir, f"{video_name}_scene{scene['index']:03d}.mp4")
        
        try:
            subprocess.run(
                ["ffmpeg", "-i", video_path,
                 "-ss", str(start),
                 "-to", str(end),
                 "-c", "copy", "-avoid_negative_ts", "1",
                 "-y", output_path],
                capture_output=True, timeout=120
            )
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                clips.append({
                    "scene_index": scene["index"],
                    "path": output_path,
                    "start_time": start,
                    "end_time": end,
                    "duration": end - start,
                })
                logger.info(f"  Extracted scene {scene['index']}: {end-start:.1f}s")
        except Exception as e:
            logger.warning(f"Failed to extract scene {scene['index']}: {e}")
    
    logger.success(f"Extracted {len(clips)} scene clips")
    return clips
