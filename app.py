import gradio as gr
import os
import zipfile
import subprocess
import tempfile
import shutil
import glob
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SUPPORTED = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv')

def get_serial_prefix(name: str) -> str:
    if ' - ' in name:
        return name.split(' - ', 1)[1].strip()
    return name.strip()

def extract_videos(zip_path: str, work_dir: str) -> list:
    extracted = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.namelist()
        for member in members:
            if '__MACOSX' in member or os.path.basename(member).startswith('.'):
                continue
            ext = os.path.splitext(member)[1].lower()
            if ext in SUPPORTED:
                fname = os.path.basename(member)
                if not fname:
                    continue
                target = os.path.join(work_dir, fname)
                with zf.open(member) as src, open(target, 'wb') as dst:
                    dst.write(src.read())
                extracted.append(target)
    return sorted(extracted)

def compress_one(vpath, out_path, crf, codec, preset, max_width, keep_audio):
    if max_width:
        vf = f'scale=min({max_width}\\,iw):-2'
    else:
        vf = 'scale=trunc(iw/2)*2:trunc(ih/2)*2'
    cmd = ['ffmpeg', '-y', '-i', vpath, '-vf', vf,
           '-c:v', codec, '-crf', str(crf), '-preset', preset]
    if codec == 'libx265':
        cmd += ['-tag:v', 'hvc1']
    cmd += (['-c:a', 'aac', '-b:a', '64k'] if keep_audio else ['-an'])
    cmd += ['-movflags', '+faststart', out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr

def make_log_row(color, icon, msg):
    palette = {
        'blue':   ('#1e3a5f', '#60a5fa'),
        'purple': ('#2d1f5e', '#a78bfa'),
        'teal':   ('#0f3d30', '#34d399'),
        'amber':  ('#3d2800', '#fbbf24'),
        'green':  ('#0f3320', '#4ade80'),
        'coral':  ('#3d1515', '#f87171'),
        'gray':   ('#1e1e2e', '#94a3b8'),
    }
    bg, fg = palette.get(color, palette['gray'])
    return (
        f'<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 12px;'
        f'margin:3px 0;border-radius:8px;background:{bg};border-left:3px solid {fg};'
        f'font-size:12.5px;font-family:\'JetBrains Mono\',monospace;'
        f'animation:fadeIn 0.25s ease;line-height:1.5">'
        f'<span style="flex-shrink:0">{icon}</span>'
        f'<span style="color:{fg};word-break:break-word">{msg}</span></div>'
    )

def make_progress_html(pct, label='', phase='compress'):
    colors = {
        'extract':  'linear-gradient(90deg,#3b82f6,#60a5fa)',
        'compress': 'linear-gradient(90deg,#7c3aed,#a78bfa,#34d399)',
        'pack':     'linear-gradient(90deg,#d97706,#fbbf24)',
        'done':     'linear-gradient(90deg,#059669,#34d399)',
    }
    bar_color = colors.get(phase, colors['compress'])
    glow = {'extract':'#3b82f6','compress':'#7c3aed','pack':'#d97706','done':'#059669'}.get(phase,'#7c3aed')
    return f'''
<div style="margin:10px 0 6px">
  <div style="display:flex;justify-content:space-between;align-items:center;
    font-size:12px;color:rgba(255,255,255,0.55);margin-bottom:6px;font-family:monospace">
    <span>{label}</span>
    <span style="font-size:16px;font-weight:700;color:white">{pct:.0f}%</span>
  </div>
  <div style="height:10px;background:rgba(255,255,255,0.08);border-radius:10px;
    overflow:hidden;box-shadow:inset 0 1px 3px rgba(0,0,0,0.4)">
    <div style="height:100%;width:{pct}%;background:{bar_color};border-radius:10px;
      transition:width 0.35s ease;box-shadow:0 0 12px {glow}88"></div>
  </div>
</div>'''

def wrap_log(rows, pbar_html=''):
    anim = '<style>@keyframes fadeIn{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:translateY(0)}}</style>'
    content = ''.join(rows)
    return (
        f'<div style="font-family:monospace;font-size:12.5px">{anim}{pbar_html}'
        f'<div style="max-height:400px;overflow-y:auto;padding-right:4px;'
        f'scrollbar-width:thin;scrollbar-color:#4c1d95 #1e1e2e">{content}</div></div>'
    )

def run_wrapper(zip_file, crf, codec, preset, max_width_choice, keep_audio):
    width_map = {"Original (keep)": None, "720p": 720, "480p": 480, "360p": 360}
    max_width  = width_map.get(max_width_choice, None)
    output_ext = 'mp4'
    logs       = []
    upload_start = time.time()

    def emit(pct, label, phase, status, out=None):
        pbar = make_progress_html(pct, label, phase)
        return wrap_log(logs, pbar), status, out

    # Validate
    if zip_file is None:
        logs.append(make_log_row('coral', '❌', 'No file uploaded. Please upload a ZIP file.'))
        yield wrap_log(logs, make_progress_html(0,'Waiting…','extract')), '❌ Upload a ZIP first', None
        return

    zip_path = zip_file.name
    zip_name = os.path.basename(zip_path)
    zip_size_mb = os.path.getsize(zip_path) / (1024*1024)

    if not zip_name.lower().endswith('.zip'):
        logs.append(make_log_row('coral','❌',f'Must be a .zip file. Got: {zip_name}'))
        yield wrap_log(logs), '❌ Wrong file type', None
        return

    upload_time = time.time() - upload_start
    logs.append(make_log_row('blue','📤',
        f'Received: <b>{zip_name}</b> — {zip_size_mb:.1f} MB '
        f'(upload: {upload_time:.1f}s)'))
    yield *emit(3,'Reading ZIP…','extract',f'📦 Reading {zip_name}…'),

    # Setup temp dirs
    work_dir   = tempfile.mkdtemp()
    input_dir  = os.path.join(work_dir,'input')
    output_dir = os.path.join(work_dir,'output')
    os.makedirs(input_dir,  exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    zip_stem      = os.path.splitext(zip_name)[0]
    serial_prefix = get_serial_prefix(zip_stem)
    output_zip_name = zip_name

    try:
        # Extract
        t0 = time.time()
        logs.append(make_log_row('blue','📂',f'Extracting videos from ZIP…'))
        yield *emit(6,'Extracting…','extract','📂 Extracting videos…'),

        videos = extract_videos(zip_path, input_dir)
        total  = len(videos)
        extract_time = time.time() - t0

        if total == 0:
            logs.append(make_log_row('coral','❌','No supported videos found in ZIP.'))
            logs.append(make_log_row('gray','ℹ️','Supported: .mp4 .mov .avi .mkv .webm .m4v .flv'))
            yield wrap_log(logs, make_progress_html(0,'Failed','extract')), '❌ No videos in ZIP', None
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        logs.append(make_log_row('teal','✅',
            f'Extracted <b>{total}</b> video(s) in {extract_time:.1f}s'))
        logs.append(make_log_row('purple','🏷️',
            f'Serial prefix: <b>{serial_prefix}</b>'))
        logs.append(make_log_row('gray','⚙️',
            f'CRF:{crf} · Codec:{codec} · Preset:{preset} · '
            f'Res:{max_width or "original"} · Audio:{"on" if keep_audio else "off"}'))
        logs.append(make_log_row('purple','🚀',
            f'Starting parallel compression — {min(4,total)} threads…'))
        yield *emit(10,'Starting compression…','compress',f'🚀 Compressing 0/{total}…'),

        # Compress parallel
        results_map = {}
        errors      = []
        done_count  = [0]
        lock        = threading.Lock()
        t_compress  = time.time()

        def task(args):
            idx, vpath = args
            serial_name = f'{serial_prefix}_{idx:02d}.{output_ext}'
            out_path    = os.path.join(output_dir, serial_name)
            t           = time.time()
            ok, err     = compress_one(vpath, out_path, crf, codec, preset, max_width, keep_audio)
            elapsed     = time.time() - t
            with lock:
                done_count[0] += 1
            if ok:
                orig_kb = os.path.getsize(vpath)    / 1024
                comp_kb = os.path.getsize(out_path) / 1024
                return idx, {
                    'ok':True,'input':os.path.basename(vpath),
                    'output':out_path,'output_name':serial_name,
                    'original_kb':round(orig_kb,1),'compressed_kb':round(comp_kb,1),
                    'savings_pct':round((1-comp_kb/orig_kb)*100,1),
                    'elapsed':round(elapsed,1)
                }
            return idx, {'ok':False,'input':os.path.basename(vpath),'error':err[:150]}

        workers = min(4, total)
        tasks   = list(enumerate(videos, start=1))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(task, t) for t in tasks]
            for fut in as_completed(futures):
                idx, res = fut.result()
                d = done_count[0]
                pct = 10 + 78 * (d / total)
                elapsed_total = time.time() - t_compress
                eta = (elapsed_total / d) * (total - d) if d > 0 else 0

                if res['ok']:
                    results_map[idx] = res
                    savings_color = '#4ade80' if res['savings_pct'] > 90 else '#fbbf24'
                    logs.append(make_log_row('teal','✔',
                        f'[{d}/{total}] <b>{res["output_name"]}</b> &nbsp;'
                        f'{res["original_kb"]:.0f}KB → '
                        f'<b>{res["compressed_kb"]:.0f}KB</b> '
                        f'<span style="color:{savings_color}">(-{res["savings_pct"]}%)</span> '
                        f'<span style="opacity:0.5">{res["elapsed"]}s</span>'))
                else:
                    errors.append(res)
                    logs.append(make_log_row('coral','❌',
                        f'[{d}/{total}] {res["input"]}: {res.get("error","unknown error")}'))

                eta_str = f'ETA {eta:.0f}s' if eta > 1 else 'almost done'
                yield *emit(
                    pct,
                    f'Compressing {d}/{total} — {eta_str}',
                    'compress',
                    f'⚡ {d}/{total} done — {pct:.0f}%'
                ),

        if not results_map:
            logs.append(make_log_row('coral','❌','All videos failed.'))
            yield wrap_log(logs, make_progress_html(0,'Failed','compress')), '❌ All failed', None
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        compress_time = time.time() - t_compress

        # Pack ZIP
        logs.append(make_log_row('amber','📦',
            f'Packing {len(results_map)} videos into ZIP…'))
        yield *emit(90,'Packing ZIP…','pack','📦 Packing ZIP…'),

        out_zip_path = os.path.join(work_dir, output_zip_name)
        with zipfile.ZipFile(out_zip_path,'w',zipfile.ZIP_DEFLATED) as zf:
            for i in sorted(results_map.keys()):
                r = results_map[i]
                zf.write(r['output'], r['output_name'])

        zip_kb   = os.path.getsize(out_zip_path) / 1024
        sorted_r = [results_map[i] for i in sorted(results_map.keys())]
        t_orig   = sum(r['original_kb']   for r in sorted_r)
        t_comp   = sum(r['compressed_kb'] for r in sorted_r)
        t_save   = (1 - t_comp / t_orig) * 100 if t_orig > 0 else 0
        total_time = time.time() - upload_start

        logs.append(make_log_row('green','━━','━'*42))
        logs.append(make_log_row('green','🎉',
            f'<b>Done!</b> {len(results_map)}/{total} videos compressed'))
        logs.append(make_log_row('green','📊',
            f'Size: {t_orig:.0f} KB → <b>{t_comp:.0f} KB</b> '
            f'| Saved <b style="color:#4ade80">{t_save:.1f}%</b>'))
        logs.append(make_log_row('green','⏱️',
            f'Compress time: {compress_time:.0f}s '
            f'| Total time: {total_time:.0f}s'))
        logs.append(make_log_row('green','📦',
            f'Output ZIP: <b>{output_zip_name}</b> ({zip_kb:.0f} KB)'))
        if errors:
            logs.append(make_log_row('coral','⚠️',
                f'{len(errors)} video(s) failed — check errors above'))

        yield (
            wrap_log(logs, make_progress_html(100,'✅ Complete!','done')),
            f'✅ Done! {len(results_map)}/{total} · saved {t_save:.1f}% · {total_time:.0f}s total',
            out_zip_path
        )

    except Exception as e:
        logs.append(make_log_row('coral','❌',f'Unexpected error: {str(e)}'))
        yield wrap_log(logs, make_progress_html(0,'Error','extract')), f'❌ Error: {e}', None
        shutil.rmtree(work_dir, ignore_errors=True)


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
* { box-sizing: border-box; }

body, .gradio-container {
    background: #0d0d1a !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    min-height: 100vh;
}
.gradio-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding: 16px 20px !important;
}

/* Transparent blocks */
.block, .form, .gap, .padded { background: transparent !important; }
.contain { background: transparent !important; }

/* All panels */
.gr-panel, .gr-box { background: transparent !important; }

/* Upload zone — FULL SIZE */
.upload-zone { width: 100% !important; }
.upload-zone > .wrap,
.upload-zone .file-preview-holder,
.upload-zone > div {
    min-height: 200px !important;
    width: 100% !important;
    border: 2px dashed rgba(167,139,250,0.5) !important;
    border-radius: 14px !important;
    background: rgba(124,58,237,0.06) !important;
    transition: all 0.3s ease !important;
    cursor: pointer !important;
}
.upload-zone > .wrap:hover,
.upload-zone > div:hover {
    border-color: #a78bfa !important;
    background: rgba(124,58,237,0.12) !important;
    box-shadow: 0 0 24px rgba(124,58,237,0.2) !important;
}
.upload-zone .icon-wrap svg { color: #a78bfa !important; width: 40px !important; height: 40px !important; }
.upload-zone p { color: rgba(255,255,255,0.6) !important; font-size: 14px !important; }

/* Labels */
label > span, .label-wrap > span, span.svelte-1gfkn6j {
    color: rgba(255,255,255,0.6) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}

/* Slider */
input[type=range] { accent-color: #7c3aed !important; }
.gr-slider input[type=number], input[type=number] {
    background: rgba(124,58,237,0.15) !important;
    border: 1px solid rgba(167,139,250,0.3) !important;
    color: #a78bfa !important;
    border-radius: 6px !important;
}

/* Radio buttons */
fieldset { border: none !important; }
.gr-radio label, .radio-group label {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: rgba(255,255,255,0.7) !important;
    font-size: 12px !important;
    padding: 6px 12px !important;
    cursor: pointer !important;
    transition: all 0.2s !important;
}
.gr-radio label:hover { border-color: rgba(167,139,250,0.5) !important; }
input[type=radio]:checked + label,
input[type=radio]:checked ~ span {
    background: rgba(124,58,237,0.25) !important;
    border-color: #a78bfa !important;
    color: #a78bfa !important;
}

/* Checkbox */
input[type=checkbox] { accent-color: #34d399 !important; transform: scale(1.2); }
.gr-checkbox label { color: rgba(255,255,255,0.75) !important; font-size: 13px !important; }

/* Textbox (status) */
.status-box textarea, .status-box input,
#status textarea, #status input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    color: rgba(255,255,255,0.85) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* Log HTML area */
.log-wrap { min-height: 420px !important; }

/* RUN BUTTON */
#run-btn, #run-btn button {
    width: 100% !important;
    padding: 16px !important;
    background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 50%, #0ea5e9 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    letter-spacing: 0.03em !important;
    cursor: pointer !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 24px rgba(124,58,237,0.5) !important;
    text-shadow: 0 1px 4px rgba(0,0,0,0.3) !important;
}
#run-btn:hover, #run-btn button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 32px rgba(124,58,237,0.7) !important;
}
#run-btn:active, #run-btn button:active {
    transform: translateY(0px) !important;
}

/* Download file */
.dl-file .file-preview, .dl-file > div {
    background: rgba(5,150,105,0.1) !important;
    border: 1px solid rgba(52,211,153,0.3) !important;
    border-radius: 12px !important;
}
.dl-file a { color: #34d399 !important; }

/* Card wrapper for sections */
.card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 12px;
}
.sec-title {
    font-size: 11px;
    font-weight: 700;
    color: rgba(255,255,255,0.4);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: rgba(255,255,255,0.04); border-radius: 4px; }
::-webkit-scrollbar-thumb { background: #4c1d95; border-radius: 4px; }
"""

HEADER = """
<div style="text-align:center;padding:24px 20px 18px;
  background:linear-gradient(135deg,rgba(124,58,237,0.12),rgba(79,70,229,0.08),rgba(14,165,233,0.08));
  border:1px solid rgba(167,139,250,0.15);border-radius:18px;margin-bottom:16px">
  <div style="font-size:2.4rem;font-weight:800;letter-spacing:-0.02em;
    background:linear-gradient(90deg,#a78bfa 0%,#60a5fa 50%,#34d399 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    background-clip:text;margin-bottom:6px">🎬 Video Compressor</div>
  <div style="color:rgba(255,255,255,0.45);font-size:13px;margin-bottom:14px">
    H.265 HEVC · Parallel 4-thread · Auto serial naming · ZIP in → ZIP out · Free & Public
  </div>
  <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
    <span style="background:rgba(167,139,250,0.15);color:#a78bfa;border:1px solid rgba(167,139,250,0.25);
      padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700">H.265 HEVC</span>
    <span style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.25);
      padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700">~98% smaller</span>
    <span style="background:rgba(96,165,250,0.15);color:#60a5fa;border:1px solid rgba(96,165,250,0.25);
      padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700">Ultrafast encode</span>
    <span style="background:rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.25);
      padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700">4 parallel threads</span>
    <span style="background:rgba(248,113,113,0.15);color:#f87171;border:1px solid rgba(248,113,113,0.25);
      padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700">Free · MIT</span>
  </div>
</div>
"""

PIPELINE = """
<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;justify-content:center;
  padding:10px 0 14px">
  <div style="background:rgba(167,139,250,0.12);border:1px solid rgba(167,139,250,0.25);
    border-radius:10px;padding:7px 14px;font-size:12px;font-weight:600;color:#a78bfa">
    📤 Upload ZIP</div>
  <span style="color:rgba(255,255,255,0.2);font-size:18px">→</span>
  <div style="background:rgba(96,165,250,0.12);border:1px solid rgba(96,165,250,0.25);
    border-radius:10px;padding:7px 14px;font-size:12px;font-weight:600;color:#60a5fa">
    📂 Extract</div>
  <span style="color:rgba(255,255,255,0.2);font-size:18px">→</span>
  <div style="background:rgba(251,191,36,0.12);border:1px solid rgba(251,191,36,0.25);
    border-radius:10px;padding:7px 14px;font-size:12px;font-weight:600;color:#fbbf24">
    ⚡ Compress (4×)</div>
  <span style="color:rgba(255,255,255,0.2);font-size:18px">→</span>
  <div style="background:rgba(52,211,153,0.12);border:1px solid rgba(52,211,153,0.25);
    border-radius:10px;padding:7px 14px;font-size:12px;font-weight:600;color:#34d399">
    🏷️ Serial rename</div>
  <span style="color:rgba(255,255,255,0.2);font-size:18px">→</span>
  <div style="background:rgba(248,113,113,0.12);border:1px solid rgba(248,113,113,0.25);
    border-radius:10px;padding:7px 14px;font-size:12px;font-weight:600;color:#f87171">
    📥 Download ZIP</div>
</div>
"""

NAMING = """
<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
  border-radius:10px;padding:12px 14px;margin-top:10px">
  <div style="font-size:10px;font-weight:700;color:rgba(255,255,255,0.35);
    letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px">Auto naming rule</div>
  <div style="font-family:monospace;font-size:11.5px;line-height:2">
    <span style="color:#a78bfa">SB05 - কাগজ [Kagoz].zip</span>
    <span style="color:rgba(255,255,255,0.25)"> → </span>
    <span style="color:#34d399">কাগজ [Kagoz]_01.mp4</span>
    <span style="color:rgba(255,255,255,0.25)">, _02…</span><br>
    <span style="color:#a78bfa">EP01 - পতাকা [Potaka].zip</span>
    <span style="color:rgba(255,255,255,0.25)"> → </span>
    <span style="color:#34d399">পতাকা [Potaka]_01.mp4</span>
    <span style="color:rgba(255,255,255,0.25)">, _02…</span><br>
    <span style="color:#a78bfa">MyVideos.zip</span>
    <span style="color:rgba(255,255,255,0.25)"> → </span>
    <span style="color:#34d399">MyVideos_01.mp4</span>
    <span style="color:rgba(255,255,255,0.25)">, _02…</span>
  </div>
  <div style="font-size:10.5px;color:rgba(255,255,255,0.3);margin-top:6px">
    Rule: part after " - " becomes the prefix. No " - " → full name used.
  </div>
</div>
"""

UPLOAD_TIP = """
<div style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);
  border-radius:8px;padding:10px 14px;margin-top:8px;font-size:11.5px;
  color:rgba(251,191,36,0.85);line-height:1.6">
  ⚡ <b>Upload tip:</b> Upload speed depends on your internet connection.
  Keep ZIP under 500 MB for best HF performance. Compression starts immediately after upload.
</div>
"""

FOOTER = """
<div style="text-align:center;padding:14px 0 6px;
  color:rgba(255,255,255,0.2);font-size:11px;letter-spacing:0.03em">
  souravbiswas35 · Hugging Face Spaces · H.265 Video Compressor · MIT License
</div>
"""

with gr.Blocks(css=CSS, title="🎬 Video Compressor") as demo:

    gr.HTML(HEADER)
    gr.HTML(PIPELINE)

    with gr.Row(equal_height=False):

        # ── LEFT: Input + Settings ────────────────────────────────────────────
        with gr.Column(scale=5):

            gr.HTML('<div class="sec-title">📤 Upload ZIP File</div>')
            zip_input = gr.File(
                label="Drop your ZIP here or click to browse",
                file_types=[".zip"],
                type="filepath",
                elem_classes=["upload-zone"],
                height=200,
            )
            gr.HTML(UPLOAD_TIP)
            gr.HTML(NAMING)

            gr.HTML('<div class="sec-title" style="margin-top:20px">⚙️ Compression Settings</div>')

            crf_slider = gr.Slider(
                minimum=18, maximum=38, value=28, step=1,
                label="CRF Quality  (18 = best quality · 38 = smallest file · 28 ✅ recommended)"
            )
            with gr.Row():
                codec_radio = gr.Radio(
                    choices=["libx265", "libx264"],
                    value="libx265",
                    label="Codec  (H.265=smallest · H.264=max compat)"
                )
                preset_radio = gr.Radio(
                    choices=["ultrafast", "fast", "medium", "slow"],
                    value="ultrafast",
                    label="Speed  (ultrafast ✅ · slow=best ratio)"
                )
            with gr.Row():
                width_radio = gr.Radio(
                    choices=["Original (keep)", "720p", "480p", "360p"],
                    value="Original (keep)",
                    label="Resolution  (resize = much smaller file)"
                )
                audio_check = gr.Checkbox(
                    value=True,
                    label="Keep Audio  (uncheck = remove, saves 5–15 KB/video)"
                )

            run_btn = gr.Button("🚀  Compress Videos Now", elem_id="run-btn")

        # ── RIGHT: Live progress + Download ──────────────────────────────────
        with gr.Column(scale=6):

            gr.HTML('<div class="sec-title">📊 Live Progress</div>')

            status_box = gr.Textbox(
                value="⏳ Waiting for upload…",
                label="Status",
                interactive=False,
                elem_id="status",
                elem_classes=["status-box"]
            )

            log_area = gr.HTML(
                value=f'<div style="background:rgba(0,0,0,0.35);border:1px solid '
                      f'rgba(255,255,255,0.07);border-radius:12px;padding:16px;'
                      f'min-height:420px;color:rgba(255,255,255,0.3);font-size:12px;'
                      f'font-family:monospace;line-height:1.8">'
                      f'📋 Compression logs will stream here live…<br><br>'
                      f'Each video shows:<br>'
                      f'&nbsp;&nbsp;✔ [done/total] filename — original → compressed (savings%)<br>'
                      f'&nbsp;&nbsp;⏱️ per-video time · total time · ETA<br>'
                      f'&nbsp;&nbsp;📦 final ZIP size</div>',
                label="Live Compression Log",
                elem_classes=["log-wrap"]
            )

            gr.HTML('<div class="sec-title" style="margin-top:16px">📥 Download Result</div>')

            download_file = gr.File(
                label="Compressed ZIP — ready when done",
                interactive=False,
                elem_classes=["dl-file"]
            )

    gr.HTML(FOOTER)

    run_btn.click(
        fn=run_wrapper,
        inputs=[zip_input, crf_slider, codec_radio, preset_radio, width_radio, audio_check],
        outputs=[log_area, status_box, download_file],
        show_progress=False
    )

if __name__ == "__main__":
    demo.launch()
