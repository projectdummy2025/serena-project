# Panduan & Tutorial Penggunaan Telegram Bot Claude Code dengan Orchestrator AI & Second Brain

Dokumen ini berisi panduan langkah demi langkah (*tutorial*) untuk memasang, mengonfigurasi, dan menjalankan Telegram Bot integrasi Claude Code yang dikendalikan oleh **Orchestrator AI** (OpenAI-Compatible Model) dan **Second Brain (Obsidian Vault)**.

---

## Arsitektur & Cara Kerja

```
[Pengguna Telegram]
       │
       ▼
[Telegram Bot Handler] (bot.py)
       │
       ▼
[LangGraph Multi-Agent State Machine] (app/core/graph.py)
       │
       ├── Node 1: Vector Retrieval (app/memory/obsidian_engine.py)
       │           Mencari konteks relevan dari Obsidian Vault via LlamaIndex + ChromaDB
       │
       ├── Node 2: Supervisor Decision (app/core/supervisor.py)
       │           Serena (Model OpenAI Compatible) mengevaluasi intent & menyusun strategi
       │
       ├── Node 3: Worker Execution (app/services/)
       │           - Claude Worker: Claude Code CLI untuk tugas koding & terminal
       │           - Research Worker: DuckDuckGo & Jina AI untuk riset web
       │           - Obsidian Worker: Penulis/Pembaca catatan Obsidian Vault
       │
       ├── Node 4: ReAct Evaluation Loop (app/core/supervisor.py)
       │           Mengevaluasi hasil kerja Worker & memicu perbaikan mandiri jika error
       │
       └── Node 5: Executive Report & Daily Log (app/formatter.py)
                   Mengirim laporan tanpa emoji ke Telegram & mencatat ke Obsidian Daily Log
```

---

## Langkah 1: Persiapan Lingkungan Kerja

1. Masuk ke direktori proyek:
   ```bash
   cd ~/projects/claude-telegram
   ```

2. Buat dan aktifkan lingkungan virtual Python (`venv`):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Pasang seluruh dependensi yang diperlukan:
   ```bash
   pip install -r requirements.txt
   ```

---

## Langkah 2: Mengonfigurasi Berkas .env

Buka berkas `.env` di direktori proyek, lalu lengkapi konfigurasi berikut:

```env
# Token Bot Telegram dari @BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# ID Telegram Akun Anda dari @userinfobot
ALLOWED_USER_ID=your_telegram_user_id_here

# Direktori kerja target tempat Claude Code beroperasi
WORKSPACE_DIR=~/projects/claude-telegram

# Konfigurasi Obsidian Vault (Second Brain)
OBSIDIAN_VAULT_DIR=~/obsidian_vault

# Konfigurasi OpenAI Compatible API (Orchestrator AI)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

---

## Langkah 3: Menjalankan Bot

### Mode Produksi Standar:
```bash
python bot.py
```

### Mode Pengembangan (Auto-Restart Otomatis saat Ada Perubahan Kode):
```bash
watchfiles --filter python "python bot.py"
```

---

## Langkah 4: Cara Menggunakan Bot di Telegram

1. Buka aplikasi Telegram dan cari bot Anda.
2. Ketik perintah `/start` untuk memulai interaksi.
3. Kirimkan pesan sapaan, tugas koding, atau instruksi riset web:
   - **Sapaan / Percakapan**: `"Selamat Malam"` -> Balasan instan dan ramah dari Serena.
   - **Tugas Koding**: `"Buatkan script_uji.py"` -> Dikerjakan oleh Claude Code worker, dievaluasi, dan dicatat otomatis ke Obsidian Daily Log.
   - **Tugas Riset**: `"Risetkan tren AI Agentic 2026"` -> Dikerjakan oleh Sub-Agent Riset via DuckDuckGo, dicatat ke Obsidian Vault (`Kotak Masuk/`), dan dilaporkan ke Telegram.

### Perintah Pendukung:
- `/status` : Memeriksa kesiapan sistem, waktu, model Orchestrator AI, dan Claude CLI.
- `/reset`  : Mengosongkan ingatan riwayat percakapan.
- `/cwd`    : Menampilkan atau mengubah lokasi direktori kerja target.
- `/help`   : Menampilkan petunjuk bantuan penggunaan.
