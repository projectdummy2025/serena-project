import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from app import config
from app import formatter

logger = logging.getLogger(__name__)

USER_CONVERSATION_HISTORY: Dict[int, List[Dict[str, str]]] = {}

GREETING_PATTERNS = [
    r"^(selamat\s+(malam|pagi|siang|sore))",
    r"^(halo|hai|hello|hi|hey)\b",
    r"^(siapa\s+(kamu|anda))",
    r"^(terima\s+kasih|makasih|thanks|thank\s+you)",
    r"^(apa\s+kabar|gimana)",
    r"^(bisa\s+bantu\s+apa)"
]

TASK_KEYWORDS = [
    "buat", "buatkan", "bikin", "edit", "perbaiki", "fix", "test", "uji", "run", 
    "jalankan", "hapus", "refactor", "tambah", "tambahkan", "analisis", "baca",
    "git", "commit", "build", "script", "file", "berkas", "fungsi", "def ",
    "import ", "class ", "code", "kode", "bug", "error", "proyek", "direktori"
]

HISTORY_FILE = os.path.join(config.WORKSPACE_DIR, ".conversation_history.json")

def load_history_from_disk() -> Dict[int, List[Dict[str, str]]]:
    """Load conversation history from JSON file on disk."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception as err:
            logger.warning(f"Kendala membaca berkas riwayat percakapan: {err}")
    return {}

def save_history_to_disk():
    """Save conversation history to JSON file on disk."""
    try:
        data = {str(k): v for k, v in USER_CONVERSATION_HISTORY.items()}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as err:
        logger.warning(f"Kendala menyimpan berkas riwayat percakapan: {err}")

def get_history(user_id: int) -> List[Dict[str, str]]:
    """Retrieve conversation history for a specific user."""
    if not USER_CONVERSATION_HISTORY:
        loaded = load_history_from_disk()
        USER_CONVERSATION_HISTORY.update(loaded)
    if user_id not in USER_CONVERSATION_HISTORY:
        USER_CONVERSATION_HISTORY[user_id] = []
    return USER_CONVERSATION_HISTORY[user_id]

def add_to_history(user_id: int, role: str, content: str):
    """Add a message to user conversation history and persist to disk."""
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > 16:
        USER_CONVERSATION_HISTORY[user_id] = history[-16:]
    save_history_to_disk()

def clear_history(user_id: int):
    """Clear conversation history for a user and save to disk."""
    USER_CONVERSATION_HISTORY[user_id] = []
    save_history_to_disk()

_openai_client: Optional[AsyncOpenAI] = None

def get_openai_client() -> Optional[AsyncOpenAI]:
    """Get AsyncOpenAI client singleton if API key is configured."""
    global _openai_client
    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your_openai_api_key_here":
        return None
    if _openai_client is None:
        _openai_client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL
        )
    return _openai_client

def fallback_intent_classification(text: str) -> str:
    """Classify intent using rule-based fallback if AI API is unavailable."""
    cleaned = text.strip().lower()
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, cleaned) and not any(kw in cleaned for kw in TASK_KEYWORDS):
            return "CHAT"
    if len(cleaned) <= 30 and not any(kw in cleaned for kw in TASK_KEYWORDS):
        return "CHAT"
    return "TASK"

async def generate_welcome_message(user_name: str, user_id: int) -> str:
    """Generate dynamic AI welcome message via Serena (Orchestrator AI)."""
    client = get_openai_client()
    now_str = datetime.now().strftime("%A, %d %B %Y - %H:%M:%S WIB")
    
    if not client:
        return formatter.format_start_message()

    system_prompt = (
        "Anda adalah Serena, Agent Master sekaligus Manajer Eksekutif untuk sistem perusahaan satu orang (One-Person Company).\n"
        "Pengguna baru saja menekan perintah /start atau memulai obrolan.\n"
        "PERATURAN MUTLAK:\n"
        "1. DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
        "2. Wajib memberikan spasi SEBELUM dan SESUDAH titik dua pada setiap label/poin. Contoh: 'Manajemen Tugas : Prioritas' (BUKAN 'Manajemen Tugas: Prioritas').\n"
        "3. DILARANG menggunakan tanda '>' di awal paragraf.\n"
        f"Informasi Waktu Sekarang: {now_str}.\n"
        f"Nama Pengguna: {user_name}.\n\n"
        "Tugas Anda: Berikan sapaan selamat datang yang hangat, ramah, manusiawi, dan profesional. "
        "Sapa pengguna sesuai waktu saat ini (pagi/siang/sore/malam), perkenalkan diri Anda sebagai Serena yang siap membantu mengelola pekerjaan, riset web, tugas koding, dan pencatatan Otak Kedua (Obsidian). "
        "DILARANG menyebutkan jalur direktori teknis seperti /home/ahmad/..."
    )

    try:
        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Mohon berikan sapaan selamat datang awal."}
            ],
            temperature=0.7
        )
        msg = response.choices[0].message.content or formatter.format_start_message()
        add_to_history(user_id, "assistant", msg)
        return msg
    except Exception as err:
        logger.error(f"Kendala pembuatan sapaan AI: {err}")
        return formatter.format_start_message()

async def orchestrate_request(user_prompt: str, user_id: int) -> Dict[str, Any]:
    """
    Orchestrate user request using OpenAI-compatible model with conversation history & system context.
    """
    client = get_openai_client()
    
    if not client:
        logger.info("OpenAI API Key tidak dikonfigurasi. Menggunakan klasifikasi Orchestrator aturan lokal.")
        intent = fallback_intent_classification(user_prompt)
        return {
            "intent": intent,
            "chat_response": "",
            "claude_instruction": user_prompt
        }

    now_str = datetime.now().strftime("%A, %d %B %Y - %H:%M:%S WIB")
    
    system_prompt = (
        "Anda adalah Serena, Agent Master sekaligus Manajer Eksekutif untuk sistem perusahaan satu orang (One-Person Company).\n"
        "Anda berkomunikasi secara manusiawi, ramah, sopan, santun, hangat, dan profesional dengan pemilik/pendiri (pengguna).\n"
        "PERATURAN MUTLAK: DILARANG MENGGUNAKAN EMOJI SAMA SEKALI dalam seluruh teks balasan Anda.\n"
        f"Informasi Konteks Sistem Saat Ini:\n"
        f"- Waktu/Jam Sekarang: {now_str}\n"
        f"- Direktori Kerja Aktif: {config.WORKSPACE_DIR}\n\n"
        "Anda membawahi spesialis rekayasa teknis bernama 'Claude Code' yang bertugas mengeksekusi perintah koding, build, test, dan manipulasi berkas.\n\n"
        "Tugas Anda:\n"
        "1. Analisis pesan pengguna secara seksama dengan memperhitungkan riwayat percakapan sebelumnya.\n"
        "2. Tentukan apakah pesan adalah percakapan/sapaan/tanya-jawab biasa ('CHAT') atau instruksi tugas teknis/koding/manipulasi berkas ('TASK').\n"
        "3. Berikan keluaran dalam format JSON valid berikut:\n"
        "{\n"
        '  "intent": "CHAT" atau "TASK",\n'
        '  "chat_response": "Balas secara langsung, ramah, manusiawi, dan konsisten dengan riwayat percakapan jika intent CHAT, kosongkan jika TASK",\n'
        '  "claude_instruction": "Instruksi teknis presisi untuk diberikan kepada Claude Code (anak buah Anda) jika intent TASK, kosongkan jika CHAT"\n'
        "}"
    )

    history = get_history(user_id)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        
        intent = data.get("intent", "TASK")
        chat_response = data.get("chat_response", "")
        claude_instruction = data.get("claude_instruction", user_prompt)
        
        if intent == "CHAT" and chat_response:
            add_to_history(user_id, "user", user_prompt)
            add_to_history(user_id, "assistant", chat_response)

        return {
            "intent": intent,
            "chat_response": chat_response,
            "claude_instruction": claude_instruction
        }
    except Exception as err:
        logger.error(f"Kendala pada OpenAI Orchestrator AI: {err}. Beralih ke penanganan fallback.")
        intent = fallback_intent_classification(user_prompt)
        return {
            "intent": intent,
            "chat_response": "",
            "claude_instruction": user_prompt
        }

async def curate_claude_output(user_prompt: str, claude_raw_output: str, user_id: int) -> str:
    """
    Curate raw execution output from Claude Code into a clean executive summary by Serena.
    """
    client = get_openai_client()
    if not client:
        return claude_raw_output

    now_str = datetime.now().strftime("%H:%M:%S WIB")
    system_prompt = (
        "Anda adalah Serena, Agent Master / Manajer Eksekutif.\n"
        "PERATURAN MUTLAK: DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
        "Gunakan format Markdown Telegram yang rapi (teks tebal *Judul Bagian*, poin - , blok kode ```...```, monospace `kode`, dan kutipan > ) agar laporan tampak sangat profesional, terstruktur, dan mudah dibaca.\n"
        f"Waktu Sekarang: {now_str}.\n"
        "Anak buah Anda (Claude Code) telah selesai melaksanakan tugas teknis di sistem.\n"
        "Tugas Anda: Rangkum dan kemas laporan hasil eksekusi tersebut menjadi narasi laporan eksekutif yang manusiawi, rapi, ramah, dan profesional untuk disajikan kepada pemilik/pendiri."
    )

    user_content = (
        f"Instruksi Pengguna: {user_prompt}\n\n"
        f"Hasil Eksekusi Claude Code:\n{claude_raw_output}"
    )

    try:
        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3
        )
        curated_text = response.choices[0].message.content or claude_raw_output
        
        add_to_history(user_id, "user", user_prompt)
        add_to_history(user_id, "assistant", curated_text)
        
        return curated_text
    except Exception as err:
        logger.error(f"Kendala kurasi Orchestrator AI: {err}")
        return claude_raw_output
