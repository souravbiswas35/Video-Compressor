---
title: Video Compressor
emoji: 🎬
colorFrom: purple
colorTo: teal
sdk: gradio
sdk_version: "4.0.0"
app_file: app.py
pinned: false
license: mit
---

# 🎬 Video Compressor

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![Gradio](https://img.shields.io/badge/Gradio-4.0-orange?style=flat-square)
![FFmpeg](https://img.shields.io/badge/FFmpeg-H.265-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)
![Free](https://img.shields.io/badge/Hosting-Free-teal?style=flat-square)

> Upload a ZIP of short videos → compress with H.265 → download renamed ZIP. No visible quality loss. Fully public and free.

---

## ⚡ How It Works

```
Upload ZIP  →  Extract videos  →  Compress (parallel)  →  Serial rename  →  Download ZIP
```

1. You upload a ZIP file (e.g. `SB01 - পতাকা [Potaka].zip`)
2. The app extracts all videos inside
3. Compresses every video in parallel using FFmpeg H.265
4. Renames them serially from the ZIP filename
5. Repacks into a ZIP with the same name → you download it

---

## 🏷️ Auto Naming Rule

| Input ZIP | Prefix Detected | Output Videos |
|---|---|---|
| `SB01 - পতাকা [Potaka].zip` | `পতাকা [Potaka]` | `পতাকা [Potaka]_01.mp4`, `_02.mp4`… |
| `EP03 - নদী [River].zip` | `নদী [River]` | `নদী [River]_01.mp4`, `_02.mp4`… |
| `MyVideos.zip` | `MyVideos` | `MyVideos_01.mp4`, `_02.mp4`… |

> **Rule:** Takes the part **after ` - `** in the ZIP filename. If no ` - ` found, uses the full name.

---

## ⚙️ Settings

| Setting | Default | Options | Effect |
|---|---|---|---|
| **CRF Quality** | `28` | 18 → 38 | Lower = better quality, larger file |
| **Codec** | `libx265` | libx265, libx264 | H.265 = 50% smaller; H.264 = max compatibility |
| **Preset** | `ultrafast` | ultrafast / fast / medium / slow | Faster = quicker encode, slightly larger file |
| **Resolution** | Original | Original / 720p / 480p / 360p | Lower = much smaller file |
| **Audio** | Keep | Keep / Remove | Remove saves 5–15 KB per video |

---

## 📊 CRF Quality Guide

| CRF Range | Quality | Best For |
|---|---|---|
| 18 – 23 | 🔵 Near-lossless | Archiving, master copies |
| **24 – 28** | **🟣 Excellent ✦ Recommended** | **Short clips, general use** |
| 29 – 32 | 🟢 Very Good | Social media, messaging |
| 33 – 38 | 🟡 Acceptable | Tiny previews, thumbnails |

---

## 🚀 Preset Speed Guide

| Preset | Speed | Compression |
|---|---|---|
| `ultrafast` ✦ | ⚡⚡⚡⚡ 10× faster | Good |
| `fast` | ⚡⚡⚡ | Better |
| `medium` | ⚡⚡ | Great |
| `slow` | ⚡ | Best |

> For 2–4 second clips, `ultrafast` quality is virtually identical to `slow`. Use `ultrafast` always.

---

## 📁 Project Files

| File | Purpose |
|---|---|
| `app.py` | Main app — Gradio UI + FFmpeg engine + parallel compression + ZIP in/out + serial naming |
| `requirements.txt` | One dependency: `gradio>=4.0.0` (FFmpeg pre-installed on HF servers) |
| `README.md` | This file — includes HF Spaces config header |
| `.gitignore` | Keeps ZIPs, cache, temp files out of the repo |

---

## 🛠️ Deploy to Hugging Face (5 min)

1. **GitHub** → New repo `video-compressor` → upload all 4 files
2. **Hugging Face** → New Space → name: `video-compressor` → SDK: **Gradio** → Visibility: **Public**
3. Space **Settings** → Repository → **Link to GitHub** → select your repo
4. Wait ~2 min → live at `huggingface.co/spaces/YOUR-USERNAME/video-compressor`

---

## 📦 Supported Formats

Input: `.mp4` `.mov` `.avi` `.mkv` `.webm` `.m4v` `.flv`
Output: `.mp4` (H.265, web-optimized with faststart)

---

## 📄 License

MIT — free to use, modify, and deploy.
