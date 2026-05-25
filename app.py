import gradio as gr
import os
import zipfile
import subprocess
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

SUPPORTED = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv')


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_serial_prefix(folder_name: str) -> str:
    """Extract serial prefix from folder name.
    'SB05 - কাগজ [Kagoz]'  →  'কাগজ [Kagoz]'
    'MyVideos'             →  'MyVideos'
    """
    if ' - ' in folder_name:
        return folder_name.split(' - ', 1)[1].strip()
    return folder_name.strip()


def collect_videos(folder_path: str, work_input_dir: str) -> list:
    """Walk folder, copy all supported videos flat into work dir."""
    collected = []
    for root, _, files in os.walk(folder_path):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in SUPPORTED:
                src  = os.path.join(root, f)
                dest = os.path.join(work_input_dir, f)
                shutil.copy2(src, dest)
                collected.append(dest)
    return sorted(collected)


def extract_from_zip(zip_path: str, work_input_dir: str) -> list:
    """Extract all supported videos from a ZIP flat into work dir."""
    extracted = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            if '__MACOSX' in member or os.path.basename(member).startswith('.'):
                continue
            if os.path.splitext(member)[1].lower() in SUPPORTED:
                fname = os.path.basename(member)
                if not fname:
                    continue
                target = os.path.join(work_input_dir, fname)
                with zf.open(member) as src, open(target, 'wb') as dst:
                    dst.write(src.read())
                extracted.append(target)
    return sorted(extracted)


def compress_video(inp, out, crf, codec, preset, max_width, keep_audio):
    """Compress one video with FFmpeg."""
    vf = (f'scale=min({max_width}\\,iw):-2' if max_width
          else 'scale=trunc(iw/2)*2:trunc(ih/2)*2')

    cmd = ['ffmpeg', '-y', '-i', inp, '-vf', vf,
           '-c:v', codec, '-crf', str(crf), '-preset', preset]

    if codec == 'libx265':
        cmd += ['-tag:v', 'hvc1']

    cmd += (['-c:a', 'aac', '-b:a', '64k'] if keep_audio else ['-an'])
    cmd += ['-movflags', '+faststart', out]

    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr


# ── Main processing function ──────────────────────────────────────────────────

def process_videos(
    upload_file,
    crf,
    codec,
    preset,
    max_width_choice,
    keep_audio,
    progress=gr.Progress(track_tqdm=True)
):
    if upload_file is None:
        return None, "❌ Please upload a ZIP file or a folder (as ZIP)."

    file_path = upload_file.name
    file_name = os.path.basename(file_path)
    ext       = os.path.splitext(file_name)[1].lower()

    width_map = {"Original (no resize)": None, "720p": 720, "480p": 480, "360p": 360}
    max_width = width_map.get(max_width_choice, None)
    output_ext = 'mp4'

    # Temp working dirs
    work_dir   = tempfile.mkdtemp()
    input_dir  = os.path.join(work_dir, 'input')
    output_dir = os.path.join(work_dir, 'output')
    os.makedirs(input_dir,  exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        progress(0, desc="📦 Reading input...")

        # ── Determine source type & serial prefix ─────────────────
        if ext == '.zip':
            # ZIP input — extract videos, derive prefix from ZIP name
            folder_name   = os.path.splitext(file_name)[0]   # strip .zip
            serial_prefix = get_serial_prefix(folder_name)
            output_zip_name = file_name                       # same name as input
            videos = extract_from_zip(file_path, input_dir)
        else:
            # Treat as single video or unknown
            return None, "❌ Please upload a ZIP file containing your videos."

        if not videos:
            return None, "❌ No supported video files found inside the ZIP."

        total   = len(videos)
        results = {}
        errors  = []

        # ── Parallel compression ──────────────────────────────────
        def compress_task(args):
            idx, vpath = args
            serial_name = f'{serial_prefix}_{idx:02d}.{output_ext}'
            out_path    = os.path.join(output_dir, serial_name)
            ok, err     = compress_video(vpath, out_path, crf, codec, preset, max_width, keep_audio)
            if ok:
                orig_kb = os.path.getsize(vpath)    / 1024
                comp_kb = os.path.getsize(out_path) / 1024
                return idx, {
                    'output':        out_path,
                    'output_name':   serial_name,
                    'original_kb':   round(orig_kb, 1),
                    'compressed_kb': round(comp_kb, 1),
                    'savings_pct':   round((1 - comp_kb / orig_kb) * 100, 1)
                }, None
            return idx, None, err[:200]

        workers = min(4, total)
        tasks   = list(enumerate(videos, start=1))

        progress(0.1, desc=f"🚀 Compressing {total} video(s) with {workers} workers...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(compress_task, t) for t in tasks]
            done    = 0
            for fut in as_completed(futures):
                idx, res, err = fut.result()
                done += 1
                progress(0.1 + 0.8 * (done / total),
                         desc=f"⚡ Compressed {done}/{total}...")
                if res:
                    results[idx] = res
                else:
                    errors.append(f'Video {idx}: {err}')

        if not results:
            return None, "❌ All compressions failed.\n" + "\n".join(errors)

        # ── Pack output ZIP ───────────────────────────────────────
        progress(0.95, desc="📦 Packing output ZIP...")
        out_zip_path = os.path.join(work_dir, output_zip_name)

        with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i in sorted(results.keys()):
                r = results[i]
                zf.write(r['output'], r['output_name'])

        # ── Build summary report ──────────────────────────────────
        sorted_results = [results[i] for i in sorted(results.keys())]
        t_orig  = sum(r['original_kb']   for r in sorted_results)
        t_comp  = sum(r['compressed_kb'] for r in sorted_results)
        t_save  = (1 - t_comp / t_orig) * 100 if t_orig > 0 else 0
        zip_kb  = os.path.getsize(out_zip_path) / 1024

        lines = [
            f"✅ Compressed {len(results)}/{total} video(s)",
            f"📁 Folder/ZIP : {folder_name}",
            f"🏷️  Prefix     : {serial_prefix}",
            f"📦 Output ZIP : {output_zip_name}",
            f"📊 Total      : {t_orig:.1f} KB → {t_comp:.1f} KB  (saved {t_save:.1f}%)",
            f"📦 ZIP size   : {zip_kb:.1f} KB",
            "",
            f"{'#':<5} {'Output Name':<38} {'Original':>9} {'Compressed':>11} {'Saved':>7}",
            "─" * 75,
        ]
        for i, r in enumerate(sorted_results, 1):
            lines.append(
                f"{i:<5} {r['output_name'][:36]:<38} "
                f"{r['original_kb']:>7.1f}KB {r['compressed_kb']:>9.1f}KB "
                f"{r['savings_pct']:>6.1f}%"
            )
        if errors:
            lines += ["", "⚠️ Errors:"] + errors

        progress(1.0, desc="✅ Done!")
        return out_zip_path, "\n".join(lines)

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return None, f"❌ Error: {str(e)}"


# ── Gradio UI ─────────────────────────────────────────────────────────────────

with gr.Blocks(
    title="🎬 Video Compressor",
    theme=gr.themes.Soft(),
    css="""
    .title { text-align: center; font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem; }
    .subtitle { text-align: center; color: #666; margin-bottom: 1.5rem; }
    .output-log { font-family: monospace; font-size: 0.82rem; }
    """
) as demo:

    gr.HTML('<div class="title">🎬 Video Compressor</div>')
    gr.HTML('<div class="subtitle">Upload a ZIP of videos → compressed ZIP back · H.265 · Auto serial naming · Parallel processing</div>')

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 Input")
            zip_input = gr.File(
                label="Upload ZIP file  (e.g.  SB05 - কাগজ [Kagoz].zip)",
                file_types=[".zip"],
                type="filepath"
            )

            gr.Markdown("### ⚙️ Settings")
            crf_slider = gr.Slider(
                minimum=18, maximum=38, value=28, step=1,
                label="CRF Quality  (18 = best quality · 38 = smallest file · 28 = recommended)"
            )
            codec_radio = gr.Radio(
                choices=["libx265", "libx264"],
                value="libx265",
                label="Codec  (libx265 = smallest · libx264 = max device compatibility)"
            )
            preset_radio = gr.Radio(
                choices=["ultrafast", "fast", "medium", "slow"],
                value="ultrafast",
                label="Speed Preset  (ultrafast = 10x faster · slow = best compression)"
            )
            width_radio = gr.Radio(
                choices=["Original (no resize)", "720p", "480p", "360p"],
                value="Original (no resize)",
                label="Max Resolution  (resize = much smaller file size)"
            )
            audio_check = gr.Checkbox(
                value=True,
                label="Keep Audio  (uncheck = remove audio, saves 5–15 KB per video)"
            )
            run_btn = gr.Button("🚀 Compress Videos", variant="primary", size="lg")

        with gr.Column(scale=1):
            gr.Markdown("### 📥 Output")
            zip_output = gr.File(label="Download Compressed ZIP")
            log_output = gr.Textbox(
                label="Compression Report",
                lines=22,
                elem_classes=["output-log"],
                interactive=False
            )

    run_btn.click(
        fn=process_videos,
        inputs=[zip_input, crf_slider, codec_radio, preset_radio, width_radio, audio_check],
        outputs=[zip_output, log_output]
    )

    gr.Markdown("""
---
**How naming works:**
`SB05 - কাগজ [Kagoz].zip` → videos named `কাগজ [Kagoz]_01.mp4`, `কাগজ [Kagoz]_02.mp4` ...
Output ZIP keeps the **same name** as input ZIP.

**CRF guide:** 18–23 = archival · **28 = recommended ✅** · 32–38 = social/messaging
    """)

if __name__ == "__main__":
    demo.launch()
