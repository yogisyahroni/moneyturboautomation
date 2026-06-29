"""
Smart Scene Matcher — Mencocokkan scene video dengan narasi/scrip
Pake AI lewat 9router buat matching yang cerdas
"""
import json
import os
import re
from typing import List, Dict, Optional
from loguru import logger

from app.new_config import config


def _call_llm(prompt: str, temperature: float = 0.3) -> str:
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
            temperature=temperature,
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


# ─── AI Scene Matcher ─────────────────────────────────────────────────

def match_scenes_to_clips_ai(
    scenes: List[Dict],
    clip_paths: List[str],
    video_subject: str
) -> List[Dict]:
    """
    AI-POWERED Scene Matcher — pake LLM buat matching scene → clip secara SEMANTIS

    Cara kerja:
    1. Kirim semua scene (narasi + keywords) + semua clip path ke LLM
    2. LLM menentukan clip mana yang paling cocok buat setiap scene
    3. Output: mapping scene_index → clip_path

    Args:
        scenes: List of scene dicts (dari generate_narasi)
        clip_paths: List of path ke video clips (dari YouTube / Pexels)
        video_subject: Topik video

    Returns:
        List of {scene_index, clip_path, start_time, duration, narasi, keywords}
    """
    if not scenes:
        logger.warning("match_scenes_to_clips_ai: no scenes to match")
        return []

    if not clip_paths:
        logger.info("match_scenes_to_clips_ai: no clips available, using empty matches")
        return []

    logger.info(f"🧠 AI Scene Matching: {len(scenes)} scenes, {len(clip_paths)} clips")

    # Build scene descriptions for LLM
    scene_descs = []
    for s in scenes:
        scene_descs.append(
            f"Scene {s.get('scene', 0)}: '{s.get('narasi', '')[:120]}...' "
            f"keywords: {s.get('keywords', [])} "
            f"duration: {s.get('duration', 8)}s"
        )

    # Build clip list for LLM (short names)
    clip_names = []
    for i, cp in enumerate(clip_paths):
        clip_names.append(f"  [{i}] {os.path.basename(cp)} ({os.path.getsize(cp) // (1024*1024)} MB)" if os.path.exists(cp) else f"  [{i}] {os.path.basename(cp)}")

    prompt = f"""Kamu adalah ahli edit video. Tugasmu: cocokkan setiap SCENE naskah dengan CLIP video yang paling cocok secara visual dan tematis.

TOPIK VIDEO: {video_subject}

=== SCENES (naskah) ===
{chr(10).join(scene_descs)}

=== AVAILABLE CLIPS ===
{chr(10).join(clip_names)}

=== TUGAS ===
Untuk setiap scene, pilih clip yang PALING COCOK secara visual.
Pertimbangkan:
- Kesesuaian topik/konteks antara narasi dengan visual clip
- Durasi clip harus cukup untuk scene (clip >= scene duration)
- Satu clip bisa dipake untuk MAX 2 scene (jika terpaksa)

Output HARUS berupa JSON array:
[
  {{
    "scene_index": 0,
    "best_clip_index": 2,
    "confidence": 0.85,
    "reason": "clip ini menunjukkan grafik ekonomi yang cocok dengan narasi tentang pelemahan rupiah"
  }}
]

Gunakan 0-index untuk scene_index dan clip_index.
Confidence: 0.0 - 1.0 (seberapa yakin lo).
Reason: jelaskan kenapa clip ini cocok dalam 1 kalimat.
Hanya output JSON, jangan ada teks lain."""

    response = _call_llm(prompt, temperature=0.2)

    # Parse LLM response
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            mapping = json.loads(match.group())
        else:
            mapping = json.loads(response)

        logger.success(f"AI Matcher: LLM returned {len(mapping)} matches")

        # Build result list
        results = []
        used_clips_count = {}
        for m in mapping:
            si = m.get("scene_index")
            ci = m.get("best_clip_index")

            if si is None or ci is None:
                continue
            if ci < 0 or ci >= len(clip_paths):
                continue

            # Find the scene
            target_scene = None
            for s in scenes:
                if s.get("scene") == si:
                    target_scene = s
                    break
            if not target_scene:
                continue

            clip_path = clip_paths[ci]

            # Track usage
            used_clips_count[ci] = used_clips_count.get(ci, 0) + 1
            if used_clips_count[ci] > 2:
                continue  # max 2 scene per clip

            # Get clip duration
            clip_duration = _get_clip_duration(clip_path)
            target_duration = target_scene.get("duration", 8)
            actual_duration = min(clip_duration, target_duration + 2) if clip_duration > 0 else target_duration

            results.append({
                "scene_index": si,
                "narasi": target_scene.get("narasi", ""),
                "clip_path": clip_path,
                "start_time": 0,
                "duration": actual_duration,
                "keywords": target_scene.get("keywords", []),
                "confidence": m.get("confidence", 0.5),
                "reason": m.get("reason", ""),
            })

        if results:
            # Verify clips exist before finalizing
            valid_results = []
            for r in results:
                if r.get("clip_path") and os.path.exists(r["clip_path"]):
                    valid_results.append(r)
                else:
                    logger.warning(f"   ⚠️  AI matched clip not found: {r.get('clip_path')}")
            logger.success(f"✅ AI Matched {len(valid_results)}/{len(scenes)} scenes to clips")
            return valid_results

    except Exception as e:
        logger.warning(f"AI Matcher LLM parse failed: {e}")
        logger.debug(f"Raw LLM response: {response[:200]}")

    # Fallback: keyword-based matching
    logger.info("AI Matcher fallback: using keyword matching")
    return match_scenes_to_clips_keyword(scenes, clip_paths, video_subject)


def match_scenes_to_clips_keyword(
    scenes: List[Dict],
    clip_paths: List[str],
    video_subject: str
) -> List[Dict]:
    """
    Keyword-based scene matcher (fallback)
    """
    if not scenes or not clip_paths:
        return []

    matches = []
    used_clips = set()

    for scene in scenes:
        keywords = [k.lower() for k in scene.get("keywords", [])]
        target_duration = scene.get("duration", 8)

        best_clip = None
        best_score = -1

        for ci, clip_path in enumerate(clip_paths):
            if ci in used_clips:
                continue

            basename = os.path.basename(clip_path).lower()

            # Score: keyword overlap
            keyword_score = 0
            for kw in keywords:
                for kw_part in kw.split():
                    if kw_part.lower() in basename:
                        keyword_score += 0.3

            # Prefer unused clips
            freshness = 0.5 if ci not in used_clips else 0

            total_score = keyword_score + freshness
            if total_score > best_score:
                best_score = total_score
                best_clip = ci

        if best_clip is not None:
            used_clips.add(best_clip)
            clip_path = clip_paths[best_clip]
            clip_duration = _get_clip_duration(clip_path)
            actual_duration = min(clip_duration, target_duration + 2) if clip_duration > 0 else target_duration

            matches.append({
                "scene_index": scene.get("scene", 0),
                "narasi": scene.get("narasi", ""),
                "clip_path": clip_path,
                "start_time": 0,
                "duration": actual_duration,
                "keywords": keywords,
                "confidence": 0.5,
                "reason": "keyword fallback",
            })

    if not matches and clip_paths:
        # Fallback: sequential assignment
        for i, scene in enumerate(scenes[:len(clip_paths)]):
            clip_path = clip_paths[i]
            clip_duration = _get_clip_duration(clip_path)
            target_duration = scene.get("duration", 8)
            matches.append({
                "scene_index": scene.get("scene", i),
                "narasi": scene.get("narasi", ""),
                "clip_path": clip_path,
                "start_time": 0,
                "duration": min(clip_duration, target_duration + 2) if clip_duration > 0 else target_duration,
                "keywords": scene.get("keywords", []),
                "confidence": 0.3,
                "reason": "sequential fallback",
            })

    # Verify clips exist
    valid_matches = []
    for m in matches:
        if m.get("clip_path") and os.path.exists(m["clip_path"]):
            valid_matches.append(m)

    logger.success(f"Keyword Matcher: matched {len(valid_matches)} scenes")
    return valid_matches


def _get_clip_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe"""
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0


# ─── Legacy: Basic keyword matcher (dipertahankan untuk backward compat) ──

def match_scenes_to_clips(
    scenes: List[Dict],
    clip_info: List[Dict],
    video_subject: str
) -> List[Dict]:
    """
    Legacy: match scenes to clips (from clip_info dicts, not paths)
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

            duration_score = 1.0 - min(abs(clip_duration - target_duration), 30) / 30
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

    logger.success(f"Matched {len(matches)} scenes to clips (legacy)")
    return matches


if __name__ == "__main__":
    # Test
    result = generate_narasi("kenapa rupiah melemah", "Rupiah melemah karena faktor global dan domestik...", {"format": "short"})
    print(json.dumps(result, indent=2)[:1000])
