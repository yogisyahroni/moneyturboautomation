"""
Smart Scene Matcher — Mencocokkan scene video dengan narasi/scrip
Pake AI lewat 9router buat matching yang cerdas
"""
import json
import re
from typing import List, Dict, Optional
from loguru import logger

from app.new_config import config


def _call_llm(prompt: str) -> str:
    """
    Panggil LLM via OpenAI-compatible API (9router)
    """
    from openai import OpenAI
    
    llm_provider = config.app.get("llm_provider", "openai")
    api_key = config.app.get(f"{llm_provider}_api_key", "")
    base_url = config.app.get(f"{llm_provider}_base_url", "http://localhost:20128/v1")
    model_name = config.app.get(f"{llm_provider}_model_name", "gratis")
    
    if not api_key:
        api_key = "sk-9router"  # fallback
    
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""


# ─── Narasi Generator ─────────────────────────────────────────────────

def generate_narasi(topic: str, research_text: str, template: Dict, language: str = "id") -> Dict:
    """
    Generate narasi/scrip berdasarkan hasil research + template
    
    Args:
        topic: Topik video
        research_text: Hasil research dari internet
        template: Template config
        
    Returns:
        {
            "script": "full script text",
            "scenes": [
                {"index": 0, "narasi": "...", "keywords": [...], "duration": 8},
                ...
            ]
        }
    """
    
    is_short = template.get("format", "short") == "short"
    scene_count = 5 if is_short else 12
    total_duration = 45 if is_short else 360  # 45 detik untuk short, 6 menit untuk long
    
    system_prompt = f"""Kamu adalah penulis naskah video dokumenter gaya Indonesia.
Buat naskah video tentang topik berikut berdasarkan referensi yang diberikan.

Format: {"Short video (9:16, gaya TikTok/Reels, 30-60 detik)" if is_short else "Long video dokumenter (16:9, 5-10 menit)"}

Buat naskah dalam {scene_count} bagian/scene.

Output HARUS berupa JSON array dengan format:
[
  {{
    "scene": 0,
    "narasi": "teks narasi untuk scene ini...",
    "keywords": ["kata kunci 1", "kata kunci 2"],
    "duration": 8
  }}
]

Aturan:
- Scene 0 = HOOK (pembuka yang bikin penasaran)
- Scene terakhir = KESIMPULAN/CTA
- Setiap scene punya 3-5 keywords untuk cari footage
- Duration per scene: {"5-10 detik" if is_short else "15-40 detik"}
- Narasi pake bahasa Indonesia yang natural, kayak ngomong
- Jangan pake markdown atau formatting"""
    
    user_prompt = f"""Topik: {topic}

Referensi:
{research_text[:4000]}

Buat naskah video dengan format JSON array seperti yang diminta."""
    
    logger.info("🤖 Generating script with AI...")
    response = _call_llm(f"{system_prompt}\n\n{user_prompt}")
    
    try:
        # Coba parse JSON dari response
        # Cari array dalam response
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            scenes = json.loads(match.group())
        else:
            scenes = json.loads(response)
        
        # Format ulang
        script_parts = []
        for s in scenes:
            script_parts.append(s.get("narasi", ""))
        
        return {
            "script": "\n\n".join(script_parts),
            "scenes": scenes,
            "total_duration": sum(s.get("duration", 8) for s in scenes),
        }
    except Exception as e:
        logger.warning(f"Failed to parse AI response as JSON: {e}")
        logger.debug(f"Raw response: {response[:500]}")
        
        # Fallback: bikin struktur manual dari response text
        return {
            "script": response,
            "scenes": [
                {
                    "scene": 0,
                    "narasi": response[:200],
                    "keywords": [topic],
                    "duration": 10,
                }
            ],
            "total_duration": 10,
        }


# ─── Scene Matcher ───────────────────────────────────────────────────

def match_scenes_to_clips(
    scenes: List[Dict],
    clip_info: List[Dict],
    video_subject: str
) -> List[Dict]:
    """
    Match scene ke clip video yang tersedia
    
    Strategi:
    1. Ambil keywords dari setiap scene
    2. Cari clip yang paling relevan berdasarkan keyword matching
    3. Urutkan sesuai urutan scene
    
    Returns:
        List of {scene_index, clip_path, start_time, duration, narasi}
    """
    if not scenes or not clip_info:
        return []
    
    matches = []
    used_clips = set()
    
    for scene in scenes:
        keywords = [k.lower() for k in scene.get("keywords", [])]
        target_duration = scene.get("duration", 8)
        
        best_clip = None
        best_score = -1
        
        for ci, clip in enumerate(clip_info):
            if ci in used_clips:
                continue
            
            clip_duration = clip.get("duration", 0)
            if clip_duration < 2:
                continue
            
            # Score based on duration proximity
            duration_score = 1.0 - min(abs(clip_duration - target_duration), 30) / 30
            
            # Keywords matching (simple)
            clip_path = clip.get("path", "").lower()
            keyword_score = 0
            for kw in keywords:
                for kw_part in kw.split():
                    if kw_part in clip_path:
                        keyword_score += 0.2
            
            total_score = duration_score + keyword_score
            if total_score > best_score:
                best_score = total_score
                best_clip = ci
        
        if best_clip is not None and best_clip not in used_clips:
            used_clips.add(best_clip)
            clip = clip_info[best_clip]
            
            matches.append({
                "scene_index": scene.get("scene", 0),
                "narasi": scene.get("narasi", ""),
                "clip_path": clip.get("path", ""),
                "start_time": max(0, clip.get("start_time", 0)),
                "duration": min(clip.get("duration", 10), target_duration + 2),
                "keywords": keywords,
            })
    
    if not matches and clip_info:
        # Fallback: pake clip urutan
        for i, scene in enumerate(scenes[:len(clip_info)]):
            clip = clip_info[i]
            if i < len(used_clips):
                continue
            matches.append({
                "scene_index": scene.get("scene", 0),
                "narasi": scene.get("narasi", ""),
                "clip_path": clip.get("path", ""),
                "start_time": max(0, clip.get("start_time", 0)),
                "duration": min(clip.get("duration", 10), 8),
                "keywords": scene.get("keywords", []),
            })
    
    logger.success(f"Matched {len(matches)} scenes to clips")
    return matches


if __name__ == "__main__":
    # Test
    result = generate_narasi("kenapa rupiah melemah", "Rupiah melemah karena faktor global dan domestik...", {"format": "short"})
    print(json.dumps(result, indent=2)[:1000])
