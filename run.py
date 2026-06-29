#!/usr/bin/env python3
"""
MoneyTurbo Automation — CLI Runner v2
=======================================
Pipeline FULLY AUTOMATED: Research → Narasi → Render via API

Cara pakai:
  python run.py --prompt "kenapa rupiah melemah" --template kamar-film-dokumenter
  python run.py --prompt "cara kerja AI" --format short
  python run.py --list-templates
  python run.py --extract-template "https://youtu.be/xxx"
"""
import argparse
import json
import os
import sys
import time
import subprocess
import signal
import atexit
from pathlib import Path

# Add project root to path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from loguru import logger

# ─── Config ──────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "llm_provider": "openai",
    "openai_api_key": "sk-9router",
    "openai_base_url": "http://localhost:20128/v1",
    "openai_model_name": "gratis",
    "pexels_api_keys": ["SLOaFHz0krNOovfSTSUCHHHmc5f1ogtDzjoRPAjIyXfyt5XP8yKpbay2"],
}

os.environ["MONEYTURBO_CONFIG"] = json.dumps(DEFAULT_CONFIG)

import app.research.search as research
import app.youtube.engine as yt
import app.matcher.matcher as matcher
import app.template.loader as tpl

API_BASE = "http://localhost:8080/api/v1"

# Track background server process
_server_proc = None


def setup_logging(verbose: bool = False):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")


def _ensure_backend():
    """Make sure the FastAPI backend (port 8080) is running"""
    global _server_proc
    
    # Cek apakah backend udah jalan
    import requests
    try:
        r = requests.get(f"{API_BASE}/tasks?page=1&page_size=1", timeout=3)
        if r.status_code < 500:
            logger.info("✅ Backend API sudah berjalan di port 8080")
            return True
    except requests.exceptions.ConnectionError:
        pass
    
    logger.info("🚀 Menjalankan backend server di port 8080...")
    
    # Start backend di background
    uvicorn_path = None
    for p in [os.path.join(root_dir, ".venv", "Scripts", "uvicorn"),
              "uvicorn",
              os.path.join(sys.prefix, "Scripts", "uvicorn")]:
        if p == "uvicorn" or os.path.isfile(p) or os.path.isfile(p + ".exe"):
            uvicorn_path = p
            break
    
    cmd = [uvicorn_path or "uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8080"]
    
    _server_proc = subprocess.Popen(
        cmd,
        cwd=root_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    
    # Tunggu sampai siap
    for i in range(15):
        time.sleep(1)
        try:
            r = requests.get(f"{API_BASE}/tasks?page=1&page_size=1", timeout=2)
            if r.status_code < 500:
                logger.success("✅ Backend API siap!")
                return True
        except requests.exceptions.ConnectionError:
            continue
    
    logger.error("❌ Gagal menjalankan backend server!")
    return False


def _stop_server():
    """Cleanup backend server at exit"""
    global _server_proc
    if _server_proc:
        _server_proc.terminate()
        _server_proc.wait(timeout=5)
        _server_proc = None


atexit.register(_stop_server)


_VALIDATE_ASPECTS = {
    "short": "9:16",
    "long": "16:9",
}


def _aspect_from_format(fmt: str) -> str:
    return _VALIDATE_ASPECTS.get(fmt, "Portrait 9:16")


def create_video_task(script: str, subject: str, terms: list, template: dict, fmt: str) -> dict:
    """
    Call POST /api/v1/videos to create a video generation task
    
    Returns: {task_id, ...} or error
    """
    import requests
    
    aspect = _aspect_from_format(fmt)
    is_short = fmt == "short"
    
    body = {
        "video_subject": subject,
        "video_script": script,
        "video_terms": terms or [subject],
        "video_aspect": aspect,
        "video_concat_mode": "random",
        "video_clip_duration": template.get("visual", {}).get("scene_duration", 5),
        "video_count": 1,
        "voice_name": template.get("narration", {}).get("voice", "id-ID-GadisNeural"),
        "voice_volume": 1.0,
        "voice_rate": template.get("narration", {}).get("speed", 1.0),
        "bgm_type": "random",
        "bgm_volume": 0.2,
        "subtitle_enabled": True,
        "subtitle_position": "bottom" if is_short else "bottom",
        "font_name": template.get("subtitle", {}).get("font", "Poppins-Bold.ttf"),
        "text_fore_color": template.get("subtitle", {}).get("color", "#FFFFFF"),
        "font_size": template.get("subtitle", {}).get("size", 60),
        "stroke_color": template.get("subtitle", {}).get("outline_color", "#000000"),
        "stroke_width": template.get("subtitle", {}).get("outline_width", 1.5),
        "video_source": "pexels",
        "match_materials_to_script": False,
    }
    
    logger.info(f"🎬 Mengirim task ke API...")
    logger.debug(f"   Body: {json.dumps(body, indent=2)[:300]}")
    
    try:
        r = requests.post(f"{API_BASE}/videos", json=body, timeout=10)
        result = r.json()
        
        if result.get("status") == 200:
            task_id = result.get("data", {}).get("task_id", "")
            logger.success(f"✅ Task created: {task_id}")
            return {"task_id": task_id, "success": True}
        else:
            error_msg = result.get("message", r.text)
            logger.error(f"❌ API error: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.exceptions.ConnectionError:
        logger.error("❌ Gagal konek ke API backend! Pastikan port 8080 aktif.")
        return {"success": False, "error": "Connection refused"}
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


def wait_for_task(task_id: str, timeout: int = 600, poll_interval: int = 5) -> dict:
    """
    Poll task status sampai selesai
    
    States API:
      1  = TASK_STATE_COMPLETE   ✅
      -1 = TASK_STATE_FAILED     ❌
      4  = TASK_STATE_PROCESSING ⏳
    
    Returns: {success, videos, combined_videos, error}
    """
    import requests
    
    logger.info(f"⏳ Menunggu task selesai... (timeout: {timeout}s)")
    
    start = time.time()
    last_progress = -1
    stuck_count = 0
    
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{API_BASE}/tasks/{task_id}", timeout=10)
            result = r.json()
            data = result.get("data", {})
            
            state = data.get("state", 0)
            progress = data.get("progress", 0)
            
            # Print progress bar kalo berubah
            if progress != last_progress:
                bar_len = 20
                filled = int(bar_len * progress / 100)
                bar = "█" * filled + "░" * (bar_len - filled)
                logger.info(f"   [{bar}] {progress}%")
                last_progress = progress
                stuck_count = 0
            else:
                stuck_count += 1
            
            if state == 1:  # TASK_STATE_COMPLETE ✅
                videos = data.get("videos", [])
                combined = data.get("combined_videos", [])
                logger.success(f"✅ Video selesai!")
                for v in videos:
                    logger.info(f"   🎬 {v}")
                return {"success": True, "videos": videos, "combined_videos": combined}
            
            elif state == -1:  # TASK_STATE_FAILED ❌
                error = data.get("error", "Unknown error")
                logger.error(f"❌ Task error: {error}")
                return {"success": False, "error": str(error)}
            
            # else: state == 4 (processing) atau lainnya — lanjut polling
            time.sleep(poll_interval)
            
        except KeyboardInterrupt:
            logger.warning("⚠️ Dihentikan user")
            return {"success": False, "error": "Cancelled"}
        except Exception as e:
            logger.warning(f"⚠️ Poll error: {e}")
            time.sleep(poll_interval)
    
    logger.error(f"❌ Timeout setelah {timeout}s")
    return {"success": False, "error": "Timeout"}


def download_video_result(url: str, output_path: str) -> str:
    """Download video hasil render"""
    import requests
    from urllib.parse import urlparse
    
    # Convert task:// relative URL ke absolute
    if url.startswith("/"):
        url = f"http://localhost:8080{url}"
    
    logger.info(f"⬇️  Downloading: {url}")
    
    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.success(f"✅ Downloaded: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
        return output_path
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return ""


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
    
    # Research options
    parser.add_argument("--research-only", action="store_true", help="Cuma research + narasi + simpan, jangan render")
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
    output_dir = os.path.abspath(args.output_dir)
    
    logger.info(f"🚀 🚀 🚀  MONEYTURBO AUTOMATION  🚀 🚀 🚀")
    logger.info(f"═" * 50)
    logger.info(f"   Prompt   : {prompt}")
    logger.info(f"   Template : {template_name}")
    logger.info(f"   Output   : {output_dir}")
    
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
        logger.info("📚 [1/4] RESEARCH — Mencari referensi dari internet")
        logger.info("═" * 50)
        
        result = research.research_topic(prompt, max_sources=args.sources)
        research_text = result.get("combined_text", "")
        
        if result.get("error"):
            logger.warning(f"⚠️  Research error: {result['error']}")
            research_text = f"Topik: {prompt}. Tidak ada referensi khusus."
        else:
            logger.info(f"✅ {len(result.get('sources', []))} sumber ditemukan")
            logger.info(f"📄 {len(research_text)} karakter referensi")
        
        with open(os.path.join(output_dir, "research.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    
    if args.research_only:
        logger.info("✅ Research only — selesai")
        return 0
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 2: GENERATE NARASI
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("═" * 50)
    logger.info("✍️  [2/4] NARASI — AI nulis script via 9router")
    logger.info("═" * 50)
    
    narration = matcher.generate_narasi(prompt, research_text, template)
    
    if not narration or not narration.get("scenes"):
        logger.error("❌ Gagal generate narasi!")
        return 1
    
    logger.info(f"✅ {len(narration['scenes'])} scene, {narration['total_duration']:.0f}s total durasi")
    for scene in narration["scenes"][:3]:
        logger.info(f"   ▶️  Scene {scene.get('scene', 0)}: {scene.get('narasi', '')[:70]}...")
    if len(narration["scenes"]) > 3:
        logger.info(f"   ... dan {len(narration['scenes'])-3} scene lainnya")
    
    # Save
    with open(os.path.join(output_dir, "narasi.json"), "w", encoding="utf-8") as f:
        json.dump(narration, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "script.txt"), "w", encoding="utf-8") as f:
        f.write(narration.get("script", ""))
    
    # Collect search terms
    script = narration.get("script", "")
    search_terms = []
    for scene in narration["scenes"]:
        for kw in scene.get("keywords", []):
            if kw not in search_terms:
                search_terms.append(kw)
    
    if not search_terms:
        search_terms = [prompt]
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 3: YOUTUBE SEARCH (opsional)
    # ═══════════════════════════════════════════════════════════════
    downloaded_videos = []
    if not args.skip_youtube:
        logger.info("")
        logger.info("═" * 50)
        logger.info("🎬 [3/4] YOUTUBE — Mencari video pendukung")
        logger.info("═" * 50)
        
        yt_search = args.yt_keywords or search_terms[:2]
        
        if args.yt_urls:
            for url in args.yt_urls:
                vpath = yt.download_video(url, os.path.join(output_dir, "yt_downloads"))
                if vpath:
                    downloaded_videos.append(vpath)
        else:
            for kw in yt_search:
                videos = yt.search_youtube(kw, max_results=1)
                if videos:
                    v = videos[0]
                    logger.info(f"   📥 Download: {v['title']} ({v['duration_str']})")
                    vpath = yt.download_video(v["url"], os.path.join(output_dir, "yt_downloads"))
                    if vpath:
                        downloaded_videos.append(vpath)
        
        if not downloaded_videos:
            logger.info("   ⚠️  YouTube skip — pake Pexels footage aja")
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 4: RENDER VIA API
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("═" * 50)
    logger.info("🎥 [4/4] RENDER — Generate video via MoneyPrinterTurbo engine")
    logger.info("═" * 50)
    
    # Pastikan backend jalan
    if not _ensure_backend():
        logger.error("❌ Gagal! Coba jalankan backend manual:")
        logger.error("   cd /e/moneyturboautomation && uvicorn app.asgi:app --port 8080")
        return 1
    
    # Kirim task ke API
    result = create_video_task(
        script=script,
        subject=prompt,
        terms=search_terms[:5],
        template=template,
        fmt=format_type
    )
    
    if not result.get("success"):
        logger.error("❌ Gagal membuat task video!")
        return 1
    
    task_id = result["task_id"]
    
    # Simpan task_id
    with open(os.path.join(output_dir, "task_id.txt"), "w") as f:
        f.write(task_id)
    
    # Poll sampai selesai
    task_result = wait_for_task(task_id)
    
    if not task_result.get("success"):
        logger.error(f"❌ Task gagal: {task_result.get('error')}")
        return 1
    
    # Download hasil video
    video_urls = task_result.get("videos", []) + task_result.get("combined_videos", [])
    
    if not video_urls:
        logger.warning("⚠️  Task selesai tapi video URL kosong. Cek di WebUI.")
        logger.info(f"   Task ID: {task_id}")
        logger.info(f"   WebUI: http://localhost:8501")
        return 0
    
    downloaded = []
    for url in video_urls:
        if url:
            filename = f"result_{Path(url).stem}.mp4" if "tasks/" in url else "result_final.mp4"
            out_path = os.path.join(output_dir, filename)
            final = download_video_result(url, out_path)
            if final:
                downloaded.append(final)
    
    # ─── Final Report ─────────────────────────────────────────────
    logger.info("")
    logger.info("═" * 60)
    logger.info("✅ ✅ ✅  PIPELINE SELESAI!  ✅ ✅ ✅")
    logger.info("═" * 60)
    logger.info(f"📥 Video tersimpan:")
    for v in downloaded:
        size = os.path.getsize(v) / (1024 * 1024)
        logger.info(f"   ▶️  {os.path.basename(v)} ({size:.1f} MB)")
    
    logger.info("")
    logger.info(f"📁 Folder output: {output_dir}")
    if downloaded:
        logger.info(f"🎬 Buka video: {downloaded[0]}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
