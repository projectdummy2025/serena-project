import logging
import json
import re
from datetime import datetime
from typing import Dict, Any

from app import config
from app.services.orchestrator import (
    get_history,
    add_to_history,
    fallback_intent_classification,
    get_openai_client
)

logger = logging.getLogger(__name__)

def extract_json_data(text: str) -> Dict[str, Any]:
    """Robustly extract JSON object from raw LLM output string."""
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}

async def supervisor_reason_node(user_prompt: str, user_id: int, retrieved_context: str) -> Dict[str, Any]:
    """
    Supervisor Serena Reason & Planning Node.
    """
    client = get_openai_client()
    now_str = datetime.now().strftime("%A, %d %B %Y - %H:%M:%S WIB")

    if not client:
        intent = fallback_intent_classification(user_prompt)
        return {
            "intent": intent,
            "chat_response": "",
            "claude_instruction": user_prompt
        }

    from app.memory.vault_writer import get_user_profile
    user_profile = get_user_profile()

    system_prompt = (
        "Anda adalah Serena, asisten pribadi dan partner berpikir untuk pemilik/pendiri proyek.\n"
        "Anda berkomunikasi secara manusiawi, ramah, lugas, alami, dan profesional.\n"
        f"Profil & Memori Karakter Pengguna (Terus Berkembang) :\n{user_profile}\n\n"
        "PERATURAN MUTLAK:\n"
        "1. DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
        "2. DILARANG menggunakan tanda '>' di awal kalimat/paragraf.\n"
        "3. DILARANG menggunakan template kaku atau footer otomatis bertumpuk.\n"
        f"Informasi Waktu Sistem: {now_str}.\n"
        f"Direktori Kerja: {config.WORKSPACE_DIR}.\n\n"
        f"Konteks Rujukan Second Brain (Obsidian Vault):\n{retrieved_context}\n\n"
        "INTEGRASI SECOND BRAIN & HITL (HUMAN-IN-THE-LOOP):\n"
        "1. Jika balasan CHAT/BRAINSTORMING Anda memberikan penjelasan konsep teknis/arsitektur/wawasan berharga, tambahkan penawaran HITL di akhir balasan 'chat_response':\n"
        "   '📌 Saran Second Brain : Saya dapat merangkum konsep [Judul Konsep] ini ke Obsidian Vault Anda. Balas *ya simpan* jika Anda berkenan.'\n"
        "2. Jika pengguna setuju untuk menyimpan ('SAVE_NOTE'), secara otomatis buat catatan konsep yang rapi dan hubungkan secara kontekstual dengan catatan terkait di Vault.\n\n"
        "Tugas Anda:\n"
        "1. Analisis pesan pengguna dengan mempertimbangkan riwayat percakapan & Konteks Rujukan Second Brain di atas.\n"
        "2. Klasifikasikan intent secara akurat:\n"
        "   - 'CHAT': untuk percakapan/sapaan/pertanyaan umum.\n"
        "   - 'BRAINSTORMING': saat pengguna berdiskusi tentang ide baru, konsep proyek, atau perencanaan. Serena berdiskusi secara alami, merangkum poin inti pengguna, dan menanyakan apakah ide ini ingin dicatatkan ke folder Kotak Masuk Obsidian.\n"
        "   - 'SAVE_NOTE': saat pengguna menyetujui penyimpanan ide (misal: 'ya simpan', 'simpan ke vault', 'simpan catatan ini'). Serena mengekstrak ide asli pengguna secara alami, tepat, dan autentik dalam format Markdown yang rapi.\n"
        "     ATURAN PENAUTAN WIKILINK PRESISI:\n"
        "     - Evaluasi relevansi topik secara ketat: HANYA buat tautan WikiLink `[[WikiLink Target]]` dari 'Konteks Rujukan Second Brain' jika terdapat hubungan konsep/ilmu yang benar-benar kuat & substansial.\n"
        "     - DILARANG keras membuat tautan jika topik tidak berhubungan.\n"
        "     - Penempatan presisi: Sisipkan secara alami di dalam kalimat (in-line) ATAU letakkan di bagian paling bawah catatan pada seksi `## Konsep Terkait` jika tidak pas diselipkan di dalam paragraf utama.\n"
        "   - 'TASK': khusus untuk perintah koding/eksekusi terminal/manipulasi berkas proyek lokal.\n"
        "   - 'RESEARCH': khusus untuk tugas riset web.\n"
        "3. Berikan keluaran format JSON valid:\n"
        "{\n"
        '  "intent": "CHAT", "BRAINSTORMING", "SAVE_NOTE", "TASK", atau "RESEARCH",\n'
        '  "chat_response": "Jawaban ramah, alami, & informatif jika CHAT/BRAINSTORMING/SAVE_NOTE (kosongkan jika TASK/RESEARCH)",\n'
        '  "claude_instruction": "Instruksi teknis presisi untuk Claude Code jika TASK/RESEARCH, kosongkan jika CHAT/BRAINSTORMING/SAVE_NOTE",\n'
        '  "note_title": "Judul singkat & deskriptif jika intent SAVE_NOTE, kosongkan jika tidak",\n'
        '  "note_content": "Isi catatan ide autentik & alami dari pengguna jika intent SAVE_NOTE, kosongkan jika tidak"\n'
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
            temperature=0.3
        )
        content = response.choices[0].message.content or "{}"
        data = extract_json_data(content)
        
        intent = data.get("intent")
        if not intent:
            intent = fallback_intent_classification(user_prompt)

        chat_response = data.get("chat_response", "")
        claude_instruction = data.get("claude_instruction", user_prompt)

        if intent == "SAVE_NOTE":
            note_title = data.get("note_title", "").strip() or f"Ide_{datetime.now().strftime('%H%M%S')}"
            note_content = data.get("note_content", "").strip() or user_prompt
            try:
                from app.memory.vault_writer import save_concept_note
                saved_path = save_concept_note(
                    title=note_title,
                    content=note_content,
                    folder="Kotak Masuk",
                    tags=["brainstorming", "ide", "second-brain"]
                )
                if not chat_response:
                    chat_response = (
                        f"Catatan ide '{note_title}' berhasil disimpan di Obsidian Vault (Kotak Masuk).\n\n"
                        f"Ringkasan :\n{note_content}"
                    )
            except Exception as e:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.warning(f"({now_str}) Gagal menyimpan catatan ide di supervisor_reason_node: {e}")

        if intent in ("CHAT", "BRAINSTORMING", "SAVE_NOTE") and chat_response:
            add_to_history(user_id, "user", user_prompt)
            add_to_history(user_id, "assistant", chat_response)

        return {
            "intent": intent,
            "chat_response": chat_response,
            "claude_instruction": claude_instruction
        }
    except Exception as err:
        logger.error(f"Kendala Supervisor Reason Node: {err}")
        fallback_intent = fallback_intent_classification(user_prompt)
        fallback_chat = ""
        if fallback_intent == "CHAT":
            fallback_chat = f"Berdasarkan rujukan catatan Obsidian:\n\n{retrieved_context}"
            add_to_history(user_id, "user", user_prompt)
            add_to_history(user_id, "assistant", fallback_chat)

        return {
            "intent": fallback_intent,
            "chat_response": fallback_chat,
            "claude_instruction": user_prompt
        }

async def supervisor_evaluate_node(user_prompt: str, worker_output: str, retry_count: int) -> Dict[str, Any]:
    """
    ReAct Evaluation Node: Evaluates worker execution results.
    """
    client = get_openai_client()
    if not client or retry_count >= 2:
        return {"status": "SUCCESS", "feedback": "", "improved_instruction": ""}

    system_prompt = (
        "Anda adalah Serena, Supervisor Agent Master yang mengevaluasi hasil eksekusi anak buah Anda (Claude Code).\n"
        "PERATURAN MUTLAK: DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
        "Tugas Anda:\n"
        "1. Periksa apakah eksekusi tugas berhasil tanpa kendala error parah.\n"
        "2. Kembalikan JSON:\n"
        "{\n"
        '  "status": "SUCCESS" atau "RETRY",\n'
        '  "feedback": "Catatan evaluasi singkat",\n'
        '  "improved_instruction": "Instruksi perbaikan jika RETRY"\n'
        "}"
    )

    user_content = f"Tugas Pengguna: {user_prompt}\n\nHasil Eksekusi Worker:\n{worker_output}"

    try:
        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return {
            "status": data.get("status", "SUCCESS"),
            "feedback": data.get("feedback", ""),
            "improved_instruction": data.get("improved_instruction", "")
        }
    except Exception as err:
        logger.error(f"Kendala Supervisor Evaluate Node: {err}")
        return {"status": "SUCCESS", "feedback": "", "improved_instruction": ""}
