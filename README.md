# 🎬 TikTok Video Analyzer Bot

Bot Telegram yang menganalisis kualitas video TikTok secara otomatis. Cukup kirim link video TikTok, bot akan mengirimkan analisis lengkap termasuk statistik, kualitas video, dan VQ Score.

![Preview](https://img.shields.io/badge/Platform-Telegram-blue?logo=telegram)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)

---

## ✨ Fitur

| Fitur | Deskripsi |
|-------|-----------|
| 📊 **Statistik Lengkap** | Views, likes, komentar, favorit/bookmarks, shares, downloads langsung dari TikTok API |
| ℹ️ **Informasi & Region** | Video ID, sumber video, region negara (bendera), deteksi potensi shadow ban |
| ☆ **Analisis Kualitas** | Browser tier, Phone tier, resolusi, codec (HEVC/H.264), bitrate, frame rate (fps), ukuran file |
| 📱 **Native Expandable Streams** | List resolusi & stream link disajikan dalam container `<blockquote expandable>` yang bisa di-tap langsung |
| ⚡ **VQ Score Modern** | Skor kompresi (0 = No Compress / Lossless Quality) |
| 🔄 **In-Place Recheck** | Tombol Recheck interaktif untuk memperbarui analisis tanpa membuat pesan baru |
| 📥 **Multi-Resolution Download** | Download video instan per resolusi (576p, 720p, 1080p, Original HD) |
| 🎵 **MP3 & Shazam** | Ekstrak audio MP3 dan deteksi musik otomatis |
| 🏷 **Deteksi Kategori** | Analisis otomatis topik dan kategori video dari hashtag |

---

## 🚀 Instalasi

### Prasyarat

- **Python 3.11+** ([Download](https://www.python.org/downloads/))
- **FFmpeg** (opsional, untuk analisis kualitas detail) ([Download](https://ffmpeg.org/download.html))
- **Token Bot Telegram** (dari [@BotFather](https://t.me/BotFather))

### Langkah Setup

#### 1. Clone/Download project

```bash
cd tiktok-analyzer-bot
```

#### 2. Buat Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Buat file `.env`

```bash
# Salin template
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux
```

Edit `.env` dan masukkan token bot:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
```

#### 5. (Opsional) Install FFmpeg

FFmpeg diperlukan untuk analisis kualitas video yang detail (codec, bitrate, fps).

**Windows:**
```bash
# Menggunakan winget
winget install ffmpeg

# Atau download dari https://ffmpeg.org/download.html
# Tambahkan ke PATH
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

#### 6. Jalankan bot

```bash
python bot.py
```

---

## 📱 Cara Penggunaan

1. **Buka Telegram** dan cari bot kamu
2. **Kirim /start** untuk memulai
3. **Salin link TikTok** dari aplikasi TikTok (Share → Copy Link)
4. **Kirim link** ke chat bot
5. **Tunggu beberapa detik** - analisis akan muncul otomatis!

### Format link yang didukung:
```
https://www.tiktok.com/@username/video/1234567890
https://vm.tiktok.com/XXXXXXX/
https://vt.tiktok.com/XXXXXXX/
```

---

## 📊 VQ Score Guide

| Score | Grade | Keterangan |
|-------|-------|------------|
| 90-100 | 🟢 A+ | Excellent - Kualitas terbaik |
| 80-89 | 🟢 A | Very Good - Sangat bagus |
| 70-79 | 🟡 B | Good - Bagus |
| 60-69 | 🟡 C | Fair - Cukup |
| 50-59 | 🟠 D | Below Average - Di bawah rata-rata |
| 40-49 | 🔴 E | Poor - Kurang |
| 0-39 | 🔴 F | Very Poor - Sangat kurang |

### Faktor VQ Score:
- **Resolusi** (30%): Pixel count relatif terhadap 1080p
- **Bitrate** (30%): Efisiensi bits-per-pixel
- **Codec** (20%): AV1 > HEVC > H264
- **Frame Rate** (20%): 60fps > 30fps > 24fps

---

## 🗂 Struktur Project

```
tiktok-analyzer-bot/
├── bot.py              # Main entry point, Telegram bot
├── tiktok_api.py       # TikTok data fetching (TikWM API)
├── video_analyzer.py   # Video quality analysis (ffprobe)
├── vq_score.py         # VQ Score calculation
├── formatter.py        # Message formatting
├── config.py           # Configuration & constants
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
└── README.md           # Documentation (file ini)
```

---

## 🔧 Mendapatkan Token Bot dari BotFather

1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot`
3. Masukkan nama bot (contoh: `TikTok Analyzer`)
4. Masukkan username bot (contoh: `tiktok_analyzer_bot`)
5. BotFather akan memberikan token, salin ke file `.env`

---

## ⚠️ Catatan Penting

- Bot menggunakan **TikWM API** (unofficial) untuk mengambil data TikTok
- **FFmpeg/ffprobe** bersifat opsional tetapi sangat disarankan untuk analisis kualitas yang detail
- Deteksi **shadow ban** menggunakan heuristic sederhana dan mungkin tidak 100% akurat
- **Kategori** di-infer dari hashtag video, bukan dari kategori resmi TikTok
- Rate limit mungkin berlaku - hindari spam request yang berlebihan

---

## 📝 License

MIT License - Free to use and modify.
