"""
Template System — Load dan apply template style untuk video
"""
import os
import yaml
from typing import Dict, Optional, List
from loguru import logger


TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")

# Template bawaan (built-in)
BUILTIN_TEMPLATES = {
    "kamar-film-dokumenter": {
        "name": "Kamar Film Style — Dokumenter Ekonomi",
        "description": "Gaya dokumenter ekonomi ala Kamar Film — deep research, narasi tenang, 16:9",
        "format": "long",
        "research": {
            "sources": ["web", "news"],
            "depth": 5,
            "language": "id",
        },
        "narration": {
            "voice": "id-ID-GadisNeural",
            "speed": 1.0,
            "style": "dokumenter-tenang",
            "hook": "Pertanyaan pembuka",
        },
        "visual": {
            "scene_duration": 8,
            "transition": "fade",
            "aspect_ratio": "16:9",
            "resolution": "1920x1080",
        },
        "subtitle": {
            "font": "BeVietnamPro-Bold.ttf",
            "position": "bottom",
            "size": 54,
            "color": "#FFFFFF",
            "outline_color": "#000000",
            "outline_width": 1.5,
            "background": True,
        },
        "audio": {
            "bgm": "cinematic-documentary",
            "bgm_volume": 0.12,
        },
        "youtube_search": {
            "max_results": 5,
            "min_duration": 30,
            "relevance_language": "id",
        },
    },
    "edukasi-shorts": {
        "name": "Edukasi Shorts — Cepat & Padat",
        "description": "Konten edukasi pendek 9:16, gaya TikTok/Reels, fast cut",
        "format": "short",
        "research": {
            "sources": ["web"],
            "depth": 3,
            "language": "id",
        },
        "narration": {
            "voice": "id-ID-ArdiNeural",
            "speed": 1.15,
            "style": "kasual-cepat",
            "hook": "Mulai dengan pertanyaan retoris",
        },
        "visual": {
            "scene_duration": 4,
            "transition": "fade",
            "aspect_ratio": "9:16",
            "resolution": "1080x1920",
        },
        "subtitle": {
            "font": "BeVietnamPro-Bold.ttf",
            "position": "center",
            "size": 64,
            "color": "#FFFFFF",
            "outline_color": "#000000",
            "outline_width": 2.0,
            "background": True,
        },
        "audio": {
            "bgm": "upbeat-corporate",
            "bgm_volume": 0.1,
        },
        "youtube_search": {
            "max_results": 3,
            "min_duration": 15,
            "relevance_language": "id",
        },
    },
    "storytelling-motivasi": {
        "name": "Storytelling Motivasi",
        "description": "Konten storytelling inspiratif dengan narasi emosional",
        "format": "short",
        "research": {
            "sources": ["web"],
            "depth": 2,
            "language": "id",
        },
        "narration": {
            "voice": "id-ID-GadisNeural",
            "speed": 0.95,
            "style": "storytelling-emosional",
            "hook": "Cerita pembuka",
        },
        "visual": {
            "scene_duration": 6,
            "transition": "fade",
            "aspect_ratio": "9:16",
            "resolution": "1080x1920",
        },
        "subtitle": {
            "font": "BeVietnamPro-Bold.ttf",
            "position": "center",
            "size": 60,
            "color": "#FFFFFF",
            "outline_color": "#000000",
            "outline_width": 2.0,
            "background": True,
        },
        "audio": {
            "bgm": "cinematic-emotional",
            "bgm_volume": 0.15,
        },
        "youtube_search": {
            "max_results": 3,
            "min_duration": 20,
            "relevance_language": "id",
        },
    },
}


def load_template(template_name: str) -> Optional[Dict]:
    """
    Load template dari file YAML atau built-in
    
    Priority:
    1. File template di templates/<name>.yaml
    2. Built-in templates
    
    Args:
        template_name: Nama template (tanpa .yaml)
    
    Returns:
        Dict template config, atau None jika gak ketemu
    """
    # 1. Cek file YAML
    yaml_path = os.path.join(TEMPLATES_DIR, f"{template_name}.yaml")
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f)
                logger.success(f"Loaded template from file: {yaml_path}")
                return template
        except Exception as e:
            logger.error(f"Failed to load template file {yaml_path}: {e}")
    
    # 2. Cek built-in
    if template_name in BUILTIN_TEMPLATES:
        logger.success(f"Loaded built-in template: {template_name}")
        return dict(BUILTIN_TEMPLATES[template_name])
    
    # 3. Fallback: edukasi-shorts
    logger.warning(f"Template '{template_name}' not found, using 'edukasi-shorts' as fallback")
    return dict(BUILTIN_TEMPLATES["edukasi-shorts"])


def list_templates() -> Dict[str, str]:
    """List semua template yang tersedia"""
    templates = {}
    
    # Built-in
    for name, tpl in BUILTIN_TEMPLATES.items():
        templates[name] = tpl.get("description", name)
    
    # File YAML
    if os.path.exists(TEMPLATES_DIR):
        for f in os.listdir(TEMPLATES_DIR):
            if f.endswith(".yaml") or f.endswith(".yml"):
                name = os.path.splitext(f)[0]
                if name not in templates:
                    templates[name] = f"Custom: {f}"
    
    return templates


def extract_template_from_url(youtube_url: str) -> Dict:
    """
    Ekstrak template dari video YouTube referensi
    
    Menganalisa:
    - Format (short/long) dari aspect ratio
    - Durasi total
    - Style narasi
    - Dll.
    
    Returns:
        Template config yang bisa langsung dipakai
    """
    from app.youtube.engine import get_video_info
    
    info = get_video_info(youtube_url)
    if not info:
        logger.warning("Gagal extract info video, pake default")
        return dict(BUILTIN_TEMPLATES["edukasi-shorts"])
    
    duration = info.get("duration", 0)
    is_short = duration < 120  # <2 menit = short
    
    logger.info(f"Extracted template from: {info['title']}")
    logger.info(f"  Duration: {duration}s → {'Short' if is_short else 'Long'} format")
    
    base = dict(BUILTIN_TEMPLATES["edukasi-shorts" if is_short else "kamar-film-dokumenter"])
    base["source_url"] = youtube_url
    base["source_title"] = info.get("title", "")
    base["source_channel"] = info.get("channel", "")
    
    return base
