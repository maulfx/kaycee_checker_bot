# 🎬 TikTok Video Analyzer & Downloader Bot

Bot Telegram modern yang menganalisis kualitas video TikTok secara mendalam dan menyediakan fitur download multi-resolusi. Cukup kirim link video TikTok, bot akan mengirimkan kartu infografis visual, statistik lengkap, analisis kualitas (Phone/Browser tier), dan VQ Score.

![Platform](https://img.shields.io/badge/Platform-Telegram-blue?logo=telegram)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)
![License](https://img.shields.io/badge/License-MIT-purple)

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|---|---|
| 🖼 **Visual Infographic Card** | Otomatis membuat gambar ringkasan visual HD (Pillow) berisi avatar profil kreator, cover blur, badge Phone/Browser tier, dan indikator skor kompresi |
| 📊 **Statistik Lengkap** | Menampilkan jumlah views, likes, komentar, bookmarks/favorit, shares, dan downloads langsung dari TikTok |
| ℹ️ **Info Akun & Region** | Username & nickname kreator, Video ID, negara sumber video (dengan bendera & nama negara), serta deteksi potensi shadow ban |
| 🔍 **Analisis Kualitas Detail** | Deteksi Phone tier & Browser tier, resolusi native, video codec (AV1/HEVC/H.264), bitrate, frame rate (fps), dan ukuran file |
| 📱 **Native Expandable Streams** | Daftar stream URL tiap resolusi disajikan rapi dalam container lipat Telegram (`<blockquote expandable>`) yang dapat di-tap langsung |
| ⚡ **VQ Compression Score** | Skor kompresi video modern (0.0 = *No Compress / Lossless Quality*, semakin rendah semakin jernih kualitas aslinya) |
| 📥 **Multi-Resolution Download** | Tombol instan untuk mengunduh video per resolusi (**576p**, **720p**, **1080p**, dan **Original HD**) |
| 🎵 **Audio MP3 & Musik** | Ekstraksi audio MP3 jernih dan deteksi metadata musik / audio latar |
| 🏷 **Klasifikasi Kategori** | Analisis otomatis topik dan kategori video dari hashtag |
| 🔄 **In-Place Recheck** | Tombol interaktif untuk memperbarui analisis tanpa membuat pesan baru di chat |
| 🛡 **Multi-Engine Fallback** | Integrasi TikWM API, yt-dlp, curl_cffi, dan direct scraping untuk kehandalan ekstraksi tanpa hambatan |

---

## 🚀 Panduan Instalasi

### Prasyarat

- **Python 3.11+** ([Download Python](https://www.python.org/downloads/))
- **FFmpeg / ffprobe** (Sangat disarankan untuk analisis bitrate & codec detail) ([Download FFmpeg](https://ffmpeg.org/download.html))
- **Token Bot Telegram** (Dapatkan dari [@BotFather](https://t.me/BotFather))

---

### Langkah Setup

#### 1. Masuk ke Direktori Project
```bash
cd kaycee_checker_bot
```

#### 2. Buat Virtual Environment
```bash
# Buat virtual environment
python -m venv venv

# Aktivasi di Windows
venv\Scripts\activate

# Aktivasi di macOS/Linux
source venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

*(Di Windows, Anda juga dapat menjalankan `setup.bat` untuk setup otomatis).*

#### 4. Konfigurasi Token (`.env`)
Salin file `.env.example` menjadi `.env`:
```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Buka file `.env` dan masukkan token bot dari BotFather:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
```

#### 5. (Opsional) Install FFmpeg
FFmpeg diperlukan agar bot dapat membaca codec, bitrate per frame, dan framerate secara akurat:

- **Windows (via winget):**
  ```bash
  winget install ffmpeg
  ```
- **macOS (via Homebrew):**
  ```bash
  brew install ffmpeg
  ```
- **Linux (Debian/Ubuntu):**
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```

#### 6. Jalankan Bot
```bash
python bot.py
```

---

## 📱 Alur Penggunaan

1. Buka bot di Telegram dan tekan `/start`.
2. Kirimkan link video TikTok (mendukung format `tiktok.com/@user/video/...`, `vt.tiktok.com/...`, maupun `vm.tiktok.com/...`).
3. Bot akan langsung menampilkan thumbnail video, statistik dasar, dan tombol aksi:
   - **Tombol Download (576p, 720p, 1080p, Original HD)**: Langsung mengunduh video sesuai pilihan.
   - **Tombol MP3**: Mengunduh audio dalam format MP3.
   - **Tombol 🔍 Check**: Menganalisis kualitas penuh, menampilkan kartu visual HD, detail bitrate/codec, stream link lipat, dan VQ Score.
   - **Tombol 🔄 Recheck**: Memeriksa ulang kualitas secara real-time.

---

## 📊 Panduan VQ Compression Score

Skor VQ mengukur tingkat kompresi/distorsi video terhadap kualitas lossless master. **Skor lebih rendah menunjukkan kualitas yang lebih murni dan minim kompresi:**

| Skor Kompresi | Grade | Keterangan Kualitas |
|---|---|---|
| **0 – 10** | 🟢 A+ | **No Compress** – Kualitas lossless / pristine |
| **11 – 20** | 🟢 A | **Low Compression** – Sangat bagus |
| **21 – 35** | 🟡 B | **Moderate** – Bagus & jernih |
| **36 – 50** | 🟡 C | **Fair** – Kualitas standar/cukup |
| **51 – 65** | 🟠 D | **Compressed** – Di bawah rata-rata |
| **> 65** | 🔴 F | **Heavy Compression** – Kompresi berat |

### Komponen Penilaian VQ:
- **Resolusi**: Perbandingan pixel terhadap standar 1080p (1080×1920).
- **Efisiensi Bitrate (BPP)**: Rasio bit-per-pixel terhadap frame rate.
- **Modernitas Codec**: Bobot efisiensi `AV1` > `HEVC/H.265` > `H.264`.
- **Frame Rate (FPS)**: Kelancaran video (60fps > 30fps > 24fps).

---

## 🗂 Struktur File Project

```
kaycee_checker_bot/
├── bot.py              # Main entry point & handler interaksi bot Telegram
├── tiktok_api.py       # Fetching data TikTok (TikWM API, yt-dlp & fallback scraper)
├── video_analyzer.py   # Analisis teknis video (ffprobe, bitrate, codec, resolusi)
├── vq_score.py         # Kalkulasi VQ Compression Score & grading sistem
├── card_generator.py   # Pembuat kartu infografis visual hasil analisis (Pillow)
├── formatter.py        # Pemformat pesan HTML, blockquote expandable & styling UI
├── emoji_icons.py      # Modul Custom Telegram Premium Emojis & fallback icon
├── fetch_emoji.py      # Helper discovery custom emoji Telegram
├── config.py           # Konfigurasi, token, kategori hashtag & bendera negara
├── requirements.txt    # Daftar dependensi Python
├── setup.bat           # Script otomatisasi setup venv & requirements untuk Windows
├── .env.example        # Template konfigurasi environment variable
└── README.md           # Dokumentasi lengkap bot (file ini)
```

---

## 🔧 Panduan Membuat Bot di BotFather

1. Buka Telegram dan cari **@BotFather**.
2. Kirim perintah `/newbot`.
3. Masukkan nama tampilan bot (contoh: `TikTok Quality Checker`).
4. Masukkan username unik yang berakhiran `bot` (contoh: `kaycee_checker_bot`).
5. Salin token API yang diberikan ke dalam file `.env`.

---

## 📝 Lisensi

Proyek ini dilisensikan di bawah lisensi [MIT](LICENSE) — Bebas digunakan dan dikembangkan.
