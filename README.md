---
title: Video Compressor
emoji: 🎬
colorFrom: purple
colorTo: indigo
sdk: gradio
sdk_version: 5.43.0
python_version: '3.10'
app_file: app.py
pinned: false
license: mit
short_description: Compress short videos inside a ZIP — H.265
---


<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=38&duration=3000&pause=1000&color=A855F7&center=true&vCenter=true&width=600&height=80&lines=%F0%9F%8E%AC+Video+Compressor;H.265+%E2%80%A2+ZIP+In+%2F+ZIP+Out;Fast+%E2%80%A2+Free+%E2%80%A2+Lossless" alt="Typing SVG" />

<br/>

<img src="https://img.shields.io/badge/Python-3.10+-3B82F6?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Gradio-4.0-F97316?style=for-the-badge&logo=gradio&logoColor=white" />
<img src="https://img.shields.io/badge/FFmpeg-H.265-22C55E?style=for-the-badge&logo=ffmpeg&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-A855F7?style=for-the-badge" />
<img src="https://img.shields.io/badge/Hosting-100%25%20Free-14B8A6?style=for-the-badge&logo=huggingface&logoColor=white" />

<br/><br/>

<a href="https://huggingface.co/spaces/souravbiswas35/Video-Compressor">
  <img src="https://img.shields.io/badge/%F0%9F%9A%80%20Launch%20App-Live%20on%20HF%20Spaces-A855F7?style=for-the-badge" />
</a>
&nbsp;
<a href="https://huggingface.co/souravbiswas35">
  <img src="https://img.shields.io/badge/HF%20Profile-souravbiswas35-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" />
</a>

<br/><br/>

> **Upload a ZIP of short videos → compress with H.265 → download renamed ZIP.**  
> No visible quality loss. Fully public and free.

---

</div>

## ✨ What This Does

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│   Upload ZIP  ──►  Extract  ──►  Compress (H.265)  ──►  Download   │
│                          [ parallel FFmpeg ]                       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

1. 📤 You upload a ZIP file (e.g. `SB01 - পতাকা [Potaka].zip`)
2. 📂 The app extracts all videos inside
3. ⚡ Compresses every video **in parallel** using FFmpeg H.265
4. 🏷️ Renames them serially from the ZIP filename
5. 📦 Repacks into a ZIP with the same name → you download it

---

## 🏷️ Auto Naming Rule

| Input ZIP | Prefix Detected | Output Videos |
|:---|:---|:---|
| `SB01 - পতাকা [Potaka].zip` | `পতাকা [Potaka]` | `পতাকা [Potaka]_01.mp4`, `_02.mp4`… |
| `EP03 - নদী [River].zip` | `নদী [River]` | `নদী [River]_01.mp4`, `_02.mp4`… |
| `MyVideos.zip` | `MyVideos` | `MyVideos_01.mp4`, `_02.mp4`… |

> **Rule:** Takes the part **after ` - `** in the ZIP filename. If no ` - ` is found, uses the full base name.

---

## ⚙️ Settings

| Setting | Default | Options | Effect |
|:---|:---:|:---|:---|
| 🎯 **CRF Quality** | `28` | 18 → 38 | Lower = better quality, larger file |
| 🎞️ **Codec** | `libx265` | libx265, libx264 | H.265 = ~50% smaller; H.264 = max compat |
| 🚀 **Preset** | `ultrafast` | ultrafast / fast / medium / slow | Faster = quicker encode, slightly larger |
| 📐 **Resolution** | Original | Original / 720p / 480p / 360p | Lower = much smaller file |
| 🔊 **Audio** | Keep | Keep / Remove | Remove saves 5–15 KB per video |

---

## 📊 CRF Quality Reference

```
18 ──────────────────────────────────────────────── 38
│                                                    │
🔵 Near-lossless   🟣 Excellent ★   🟢 Very Good   🟡 OK
│  Archiving        │ General use    │ Social media  │ Previews
18─────────23      24──────28       29──────32      33────38
```

| Range | Quality | Best For |
|:---:|:---|:---|
| 18 – 23 | 🔵 **Near-lossless** | Archiving, master copies |
| **24 – 28** | 🟣 **Excellent ✦ Recommended** | **Short clips, general use** |
| 29 – 32 | 🟢 **Very Good** | Social media, messaging |
| 33 – 38 | 🟡 **Acceptable** | Tiny previews, thumbnails |

---

## 🚀 Preset Speed Guide

| Preset | Speed | Compression |
|:---|:---:|:---|
| `ultrafast` ✦ | ⚡⚡⚡⚡ 10× faster | Good |
| `fast` | ⚡⚡⚡ | Better |
| `medium` | ⚡⚡ | Great |
| `slow` | ⚡ | Best |

> 💡 For 2–4 second clips, `ultrafast` quality is virtually identical to `slow`. **Use `ultrafast` always.**

---

## 📦 Supported Formats

```
Input:   .mp4  .mov  .avi  .mkv  .webm  .m4v  .flv
Output:  .mp4  (H.265 · web-optimized · faststart)
```

---

## 📁 Project Files

| File | Purpose |
|:---|:---|
| `app.py` | Main app — Gradio UI + FFmpeg engine + parallel compression + ZIP in/out + serial naming |
| `requirements.txt` | One dependency: `gradio>=4.0.0` (FFmpeg pre-installed on HF servers) |
| `README.md` | This file — includes HF Spaces config header |
| `.gitignore` | Keeps ZIPs, cache, and temp files out of the repo |

---

## 🛠️ Deploy Your Own (5 min)

```bash
# Step 1 — Push to GitHub
git init && git add . && git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/video-compressor
git push -u origin main

# Step 2 — Create HF Space
# huggingface.co → New Space → SDK: Gradio → Public

# Step 3 — Link GitHub repo in Space Settings → Repository

# Done ✅  Live in ~2 minutes
```

| Step | Action |
|:---:|:---|
| 1️⃣ | **GitHub** → New repo `video-compressor` → upload all 4 files |
| 2️⃣ | **Hugging Face** → New Space → SDK: **Gradio** → Visibility: **Public** |
| 3️⃣ | Space **Settings** → Repository → **Link to GitHub** → select your repo |
| 4️⃣ | Wait ~2 min → live at `huggingface.co/spaces/YOUR-USERNAME/video-compressor` |

---

## 📄 License

```
MIT License — free to use, modify, and deploy.
© 2026 souravbiswas35
```

---

<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=14&duration=4000&pause=500&color=14B8A6&center=true&vCenter=true&width=500&lines=Built+with+%E2%9D%A4%EF%B8%8F+by+souravbiswas35;Powered+by+FFmpeg+%2B+Gradio+%2B+HF+Spaces;Open+Source+%E2%80%A2+Free+Forever" alt="Footer Typing" />

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-souravbiswas35-181717?style=flat-square&logo=github)](https://github.com/souravbiswas35)
[![HF Profile](https://img.shields.io/badge/HF%20Profile-souravbiswas35-FFD21E?style=flat-square&logo=huggingface&logoColor=black)](https://huggingface.co/souravbiswas35)
[![HF Space](https://img.shields.io/badge/HF%20Space-Video%20Compressor-A855F7?style=flat-square&logo=huggingface)](https://huggingface.co/spaces/souravbiswas35/Video-Compressor)

</div>
