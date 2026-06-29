#!/usr/bin/env python3
"""
MoneyTurbo Automation — CLI Runner
====================================
Pipeline lengkap: Research → Narasi → YouTube Search → Scene Match → Render

Cara pakai:
  python run.py --prompt "kenapa rupiah melemah" --template kamar-film-dokumenter --format short
  python run.py --prompt "kenapa rupiah melemah"  # default template
  python run.py --list-templates
  python run.py --extract-template "https://youtu.be/xxx"
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from loguru import logger

# ─── Config ──────────────────────────────────────────────────────────

# Default config — bisa di override via environment variable
DEFAULT_CONFIG = {
    "llm_provider": "openai",
    "openai_api_key": "sk-9router",
    "openai_base_url": "http://localhost:20128/v1",
    "openai_model_name": "gratis",
    "pexels_api_keys": ["SLOaFHz0krNOovfSTSUCHHHmc5f1ogtDzjoRPAjIyXfyt5XP8yKpbay2"],
}

# Paksa config sebelum import module lain
os.environ["MONEYTURBO_CONFIG"] = json.dumps(DEFAULT_CONFIG)

import app.research.search as research
import app.youtube.engine as yt
import app.matcher.matcher as matcher
import app.template.loader as tpl


def setup_logging(verbose: bool = False):
    """Setup logging"""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")


def main():
    parser = argparse.ArgumentParser(
        description="MoneyTurbo Automation — Bikin video otomatis dari prompt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python run.py --prompt "kenapa rupiah melemah?" --template kamar-film-dokumenter
  python run.py --prompt "cara kerja AI" --format short
  python run.py --list-templates
  python run.py --extract-template "https://youtu.be/vKVlghqgjg0"
        """
    )
    
    # Main options
    parser.add_argument("--prompt", "-p", type=str, help="Topik video (misal: 'kenapa rupiah melemah?')")
    parser.add_argument("--template", "-t", type=str, default="edukasi-shorts", 
                        help="Nama template (default: edukasi-shorts)")
    parser.add_argument("--format", "-f", type=str, choices=["short", "long"], default=None,
                        help="Override format video (short=9:16, long=16:9)")
    
    # Pipeline options
    parser.add_argument("--skip-research", action="store_true", help="Skip research step")
    parser.add_argument("--skip-youtube", action="store_true", help="Skip YouTube search & download")
    parser.add_argument("--skip-render", action="store_true", help="Skip render (just prepare)")
    
    # Research options
    parser.add_argument("--research-only", action="store_true", help="Hanya research, jangan generate video")
    parser.add_argument("--sources", type=int, default=5, help="Jumlah sumber research")
    
    # YouTube options
    parser.add_argument("--yt-urls", type=str, nargs="+", help="YouTube URL manual (skip search)")
    parser.add_argument("--yt-keywords", type=str, nargs="+", help="Kata kunci YouTube (override)")
    
    # Template tools
    parser.add_argument("--list-templates", action="store_true", help="List semua template")
    parser.add_argument("--extract-template", type=str, metavar="YT_URL", 
                        help="Ekstrak template dari video YouTube")
    
    # Output
    parser.add_argument("--output-dir", "-o", type=str, default="output",
                        help="Directory output video")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # ─── Mode: List Templates ─────────────────────────────────────
    if args.list_templates:
        templates = tpl.list_templates()
        print("\n📋 Template Tersedia:")
        print("═" * 50)
        for name, desc in sorted(templates.items()):
            print(f"  • {name:30s} — {desc}")
        print()
        return 0
    
    # ─── Mode: Extract Template ───────────────────────────────────
    if args.extract_template:
        logger.info(f"🎯 Extracting template from: {args.extract_template}")
        template = tpl.extract_template_from_url(args.extract_template)
        print("\n📋 Template Extract Result:")
        print("═" * 50)
        print(json.dumps(template, indent=2))
        
        # Simpan ke file
        output_path = "extracted_template.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved to: {output_path}")
        return 0
    
    # ─── Mode: Generate Video ─────────────────────────────────────
    if not args.prompt:
        parser.print_help()
        print("\n❌ Error: --prompt required (kecuali --list-templates)")
        return 1
    
    prompt = args.prompt
    template_name = args.template
    output_dir = args.output_dir
    
    logger.info(f"🚀 Starting MoneyTurbo Automation")
    logger.info(f"   Prompt   : {prompt}")
    logger.info(f"   Template : {template_name}")
    
    # Load template
    template = tpl.load_template(template_name)
    if not template:
        logger.error(f"Template '{template_name}' not found")
        return 1
    
    if args.format:
        template["format"] = args.format
    
    format_type = template.get("format", "short")
    logger.info(f"   Format   : {format_type}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 1: RESEARCH
    # ═══════════════════════════════════════════════════════════════
    research_text = ""
    if not args.skip_research:
        logger.info("")
        logger.info("═" * 50)
        logger.info("📚 STEP 1/4: RESEARCH")
        logger.info("═" * 50)
        
        result = research.research_topic(prompt, max_sources=args.sources)
        research_text = result.get("combined_text", "")
        
        if result.get("error"):
            logger.warning(f"Research returned error: {result['error']}")
            research_text = f"Topik: {prompt}. Tidak ada referensi khusus."
        else:
            logger.info(f"✅ Research selesai: {len(result.get('sources', []))} sumber ditemukan")
            logger.info(f"📄 Total teks referensi: {len(research_text)} karakter")
        
        # Save research results
        with open(os.path.join(output_dir, "research.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    
    if args.research_only:
        logger.info("✅ Research only mode — selesai")
        return 0
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 2: GENERATE NARASI
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("═" * 50)
    logger.info("✍️  STEP 2/4: GENERATE NARASI")
    logger.info("═" * 50)
    
    narration = matcher.generate_narasi(prompt, research_text, template)
    
    if not narration or not narration.get("scenes"):
        logger.error("Gagal generate narasi!")
        return 1
    
    logger.info(f"✅ Narasi selesai: {len(narration['scenes'])} scene, {narration['total_duration']:.0f}s total")
    for scene in narration["scenes"]:
        logger.info(f"   Scene {scene.get('scene', 0)}: {scene.get('narasi', '')[:60]}... ({scene.get('duration', 0)}s)")
    
    # Save script
    with open(os.path.join(output_dir, "narasi.json"), "w", encoding="utf-8") as f:
        json.dump(narration, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "script.txt"), "w", encoding="utf-8") as f:
        f.write(narration.get("script", ""))
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 3: YOUTUBE SEARCH + DOWNLOAD
    # ═══════════════════════════════════════════════════════════════
    downloaded_videos = []
    scene_clips = []
    
    if not args.skip_youtube:
        logger.info("")
        logger.info("═" * 50)
        logger.info("🎬 STEP 3/4: YOUTUBE SEARCH & DOWNLOAD")
        logger.info("═" * 50)
        
        # Collect keywords from all scenes
        all_keywords = set()
        for scene in narration["scenes"]:
            for kw in scene.get("keywords", []):
                all_keywords.add(kw)
        
        yt_search_keywords = args.yt_keywords or list(all_keywords)[:3]
        
        # Jika ada URL manual
        if args.yt_urls:
            logger.info(f"📥 Using manual URLs: {args.yt_urls}")
            for url in args.yt_urls:
                video_path = yt.download_video(url, os.path.join(output_dir, "yt_downloads"))
                if video_path:
                    downloaded_videos.append(video_path)
        else:
            # Search YouTube
            for kw in yt_search_keywords:
                logger.info(f"🔍 Searching YouTube for: '{kw}'")
                videos = yt.search_youtube(kw, max_results=template.get("youtube_search", {}).get("max_results", 3))
                
                if videos:
                    # Download video pertama
                    target = videos[0]
                    logger.info(f"   Found: {target['title']} ({target['duration_str']})")
                    video_path = yt.download_video(target["url"], os.path.join(output_dir, "yt_downloads"))
                    if video_path:
                        downloaded_videos.append(video_path)
                        break  # Cukup 1 video dulu untuk MVP
            
            if not downloaded_videos:
                logger.warning("⚠️  No YouTube videos downloaded. Will try Pexels as fallback.")
        
        # Scene detection untuk setiap video yang didownload
        yt_dir = os.path.join(output_dir, "yt_downloads")
        scenes_dir = os.path.join(output_dir, "scenes")
        
        for video_path in downloaded_videos:
            logger.info(f"🎬 Detecting scenes in: {os.path.basename(video_path)}")
            scenes = yt.detect_scenes(video_path, threshold=25.0)
            
            if scenes:
                clips = yt.extract_scene_clips(video_path, scenes, scenes_dir, 
                                                min_duration=3.0, max_duration=15.0)
                scene_clips.extend(clips)
                
                # Save scene info
                with open(os.path.join(output_dir, f"scenes_{os.path.basename(video_path)}.json"), 
                          "w", encoding="utf-8") as f:
                    json.dump(scenes, f, indent=2)
        
        logger.info(f"📦 Total scene clips: {len(scene_clips)}")
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 4: SMART MATCHING + RENDER
    # ═══════════════════════════════════════════════════════════════
    if not args.skip_render:
        logger.info("")
        logger.info("═" * 50)
        logger.info("🎯 STEP 4/4: MATCHING & RENDER")
        logger.info("═" * 50)
        
        # Match scenes to clips
        if scene_clips:
            matches = matcher.match_scenes_to_clips(
                narration["scenes"], scene_clips, prompt
            )
            logger.info(f"✅ Matched {len(matches)} scenes to clips")
            
            with open(os.path.join(output_dir, "matches.json"), "w", encoding="utf-8") as f:
                json.dump(matches, f, indent=2, ensure_ascii=False)
        else:
            logger.info("⚠️  No scene clips available — akan pake Pexels footage (default MoneyPrinterTurbo)")
            matches = []
        
        # ─── Final: Render via MoneyPrinterTurbo ─────────────────
        # Kita pake existing MoneyPrinterTurbo render engine
        
        script_text = narration.get("script", "")
        search_terms = []
        for scene in narration["scenes"]:
            for kw in scene.get("keywords", []):
                if kw not in search_terms:
                    search_terms.append(kw)
        
        logger.info("🎥 Rendering video...")
        logger.info(f"   Script length : {len(script_text)} chars")
        logger.info(f"   Search terms  : {search_terms[:5]}")
        logger.info(f"   Format        : {format_type}")
        
        # Save final params
        render_params = {
            "prompt": prompt,
            "template": template_name,
            "format": format_type,
            "script": script_text,
            "search_terms": search_terms[:5],
            "total_clips": len(scene_clips),
            "total_duration": narration.get("total_duration", 0),
        }
        with open(os.path.join(output_dir, "render_params.json"), "w", encoding="utf-8") as f:
            json.dump(render_params, f, indent=2, ensure_ascii=False)
        
        logger.info("")
        logger.info("═" * 50)
        logger.info("✅ PIPELINE SELESAI!")
        logger.info("═" * 50)
        logger.info(f"📁 Output: {os.path.abspath(output_dir)}")
        logger.info(f"📄 Script: {os.path.abspath(os.path.join(output_dir, 'script.txt'))}")
        logger.info(f"📊 Narasi: {os.path.abspath(os.path.join(output_dir, 'narasi.json'))}")
        logger.info(f"🎬 Clips  : {len(scene_clips)} scene clips")
        logger.info(f"🔍 Terms  : {search_terms[:5]}")
        logger.info("")
        logger.info("💡 Untuk render final, buka WebUI MoneyPrinterTurbo dan:")
        logger.info("   1. Paste script dari script.txt")
        logger.info(f"   2. Set search terms: {', '.join(search_terms[:3])}")
        logger.info("   3. Set video source ke Pexels")
        logger.info("   4. Klik Generate Video!")
    else:
        logger.info("")
        logger.info("═" * 50)
        logger.info("✅ PREPARATION SELESAI (--skip-render)")
        logger.info("═" * 50)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
