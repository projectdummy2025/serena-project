import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from app import config
from app import formatter
from app.memory import vault_writer, obsidian_engine

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
    "import ", "class ", "code", "kode", "bug", "error", "proyek", "direktori", "skill"
]

SERENA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_skill",
            "description": "Simpan atau perbarui resep/SOP keterampilan baru (Skill) di Obsidian Vault (04-Skills/<skill_name>.md).",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Nama skill unik tanpa ekstensi, contoh: 'analisis_jurnal' atau 'penataan_rutinitas'"
                    },
                    "content": {
                        "type": "string",
                        "description": "Isi lengkap panduan SOP / langkah-langkah kerja Markdown tanpa emoji"
                    }
                },
                "required": ["skill_name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "Membaca resep/SOP keterampilan (Skill) dari Obsidian Vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Nama skill yang ingin dibaca"
                    }
                },
                "required": ["skill_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "Menampilkan daftar seluruh skill SOP yang tersimpan di Obsidian Vault.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_daily_log",
            "description": "Menambahkan entri ke log harian Obsidian Vault (02-Daily-Logs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Judul entri log"
                    },
                    "content": {
                        "type": "string",
                        "description": "Rincian isi entri log"
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_obsidian_vault",
            "description": "Mencari catatan rujukan di Obsidian Vault menggunakan pencarian vektor semantik.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Kata kunci atau kalimat pertanyaan pencarian"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def execute_tool(name: str, args: dict) -> str:
    """Execute a Serena function tool and return the string result."""
    try:
        if name == "save_skill":
            return vault_writer.save_skill(args.get("skill_name", ""), args.get("content", ""))
        elif name == "get_skill":
            return vault_writer.get_skill(args.get("skill_name", ""))
        elif name == "list_skills":
            skills = vault_writer.list_skills()
            if not skills:
                return "Belum ada skill yang tersimpan di Obsidian Vault (04-Skills)."
            return "Daftar Skill Tersimpan :\n- " + "\n- ".join(skills)
        elif name == "save_daily_log":
            file_path = vault_writer.append_to_daily_log(args.get("title", ""), args.get("content", ""))
            return f"Entri log harian tersimpan di: {file_path}"
        elif name == "search_obsidian_vault":
            return obsidian_engine.search_obsidian_vault(args.get("query", ""))
        else:
            return f"Tool '{name}' tidak ditemukan."
    except Exception as err:
        logger.error(f"Kendala eksekusi tool '{name}': {err}")
        return f"Gagal mengeksekusi tool {name}: {err}"


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
        "Anda adalah Serena, asisten pribadi dan partner berpikir pengguna.\n"
        "Pengguna baru saja menekan perintah /start atau menyapa Anda.\n"
        "PERATURAN MUTLAK:\n"
        "1. DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
        "2. DILARANG menggunakan tanda '>' di awal paragraf.\n"
        "3. DILARANG membuat daftar poin-poin/bullet points kaku.\n"
        f"Informasi Waktu Sekarang: {now_str}.\n"
        f"Nama Pengguna: {user_name}.\n\n"
        "Tugas Anda: Berikan sapaan selamat datang yang singkat, ramah, alami, dan manusiawi (1-3 kalimat). "
        "Sapa pengguna sesuai waktu saat ini (pagi/siang/sore/malam) dan sebut nama pengguna. "
        "Tanyakan secara hangat apakah ada yang bisa dibantu hari ini, atau apakah ada hal menarik yang ingin dibahas bersama."
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
    skills_list = vault_writer.list_skills()
    skills_context = "Daftar Skill Tersimpan Saat Ini :\n" + ("- " + "\n- ".join(skills_list) if skills_list else "- (Belum ada skill)")
    
    system_prompt = (
        "Anda adalah Serena, Agent Master sekaligus Manajer Eksekutif untuk sistem perusahaan satu orang (One-Person Company).\n"
        "Anda berkomunikasi secara manusiawi, ramah, sopan, santun, hangat, dan profesional dengan pemilik/pendiri (pengguna).\n"
        "PERATURAN MUTLAK:\n"
        "1. DILARANG MENGGUNAKAN EMOJI SAMA SEKALI dalam seluruh teks balasan Anda.\n"
        "2. Wajib memberikan spasi SEBELUM dan SESUDAH titik dua pada setiap label/poin. Contoh: 'Status : Aktif' (BUKAN 'Status: Aktif').\n"
        f"Informasi Konteks Sistem Saat Ini:\n"
        f"- Waktu/Jam Sekarang: {now_str}\n"
        f"- Direktori Kerja Aktif: {config.WORKSPACE_DIR}\n"
        f"{skills_context}\n\n"
        "Anda memiliki akses ke Tools berikut (save_skill, get_skill, list_skills, save_daily_log, search_obsidian_vault).\n"
        "Jika pengguna meminta membuat/menyimpan skill SOP baru, gunakan tool 'save_skill'.\n"
        "Jika pengguna meminta membaca/menampilkan skill, gunakan tool 'get_skill' atau 'list_skills'.\n"
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
        # Tool execution loop
        for _ in range(3):  # Limit tool execution turns to max 3 iterations
            response = await client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                tools=SERENA_TOOLS,
                temperature=0.3
            )
            response_msg = response.choices[0].message
            
            if response_msg.tool_calls:
                messages.append(response_msg)
                for tool_call in response_msg.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except Exception:
                        fn_args = {}
                    
                    tool_result = execute_tool(fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
                continue
            
            content = response_msg.content or "{}"
            try:
                data = json.loads(content)
                intent = data.get("intent", "CHAT")
                chat_response = data.get("chat_response", content)
                claude_instruction = data.get("claude_instruction", user_prompt)
            except Exception:
                intent = "CHAT"
                chat_response = content
                claude_instruction = ""

            if intent == "CHAT" and chat_response:
                add_to_history(user_id, "user", user_prompt)
                add_to_history(user_id, "assistant", chat_response)

            return {
                "intent": intent,
                "chat_response": chat_response,
                "claude_instruction": claude_instruction
            }

        return {
            "intent": "CHAT",
            "chat_response": "Proses eksekusi tool selesai.",
            "claude_instruction": ""
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
