import os
import sys
import logging
import asyncio
import warnings

# Suppress unclosed transport ResourceWarning from async HTTP socket cleanup
warnings.filterwarnings("ignore", category=ResourceWarning)

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import time
from app import config
from app import security
from app import formatter
from app.services import claude_service
from app.services import orchestrator
from app.core.graph import agent_app

# Configure logging format to match AGENTS.md standard: (date-timestamp) message
logging.basicConfig(
    format="(%(asctime)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle background network errors and exception logging gracefully."""
    logger.warning(f"Terjadi kendala jaringan/sistem: {context.error}")

async def keep_typing(chat_id: int, context: ContextTypes.DEFAULT_TYPE, stop_event: asyncio.Event):
    """Send Telegram typing action continuously every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.debug(f"Gagal mengirim indikator mengetik: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass

@security.restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with dynamic AI welcome narrative."""
    user = update.effective_user
    user_name = user.first_name if user else "Pengguna"
    user_id = user.id if user else 0
    chat_id = update.effective_chat.id

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(chat_id, context, stop_typing))
    
    try:
        welcome_text = await orchestrator.generate_welcome_message(user_name, user_id)
        await formatter.send_formatted_telegram_message(update, welcome_text)
    finally:
        stop_typing.set()
        await typing_task

@security.restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command providing guidance with Markdown formatting."""
    help_text = (
        "*Panduan Penggunaan Bot Telegram Serena*\n"
        "_(LangGraph Multi-Agent System & Second Brain)_\n\n"
        "*1. Percakapan & Sapaan*\n"
        "   Kirimkan pesan sapaan atau pertanyaan umum. Serena akan merespon secara langsung, manusiawi, dan mengingat konteks percakapan serta dokumen Obsidian.\n\n"
        "*2. Instruksi Pemrograman & Tugas Teknis*\n"
        "   Kirimkan perintah koding atau manipulasi berkas. Serena mendelegasikan ke Claude Code, mengevaluasi hasil, dan mencatatnya ke Obsidian.\n"
        "   _Contoh:_ `Buatkan script_analisis.py untuk membaca berkas CSV`\n\n"
        "*3. Tugas Riset Web*\n"
        "   Kirimkan instruksi pencarian informasi web atau berita. Serena mendelegasikan ke Sub-Agent Riset.\n"
        "   _Contoh:_ `Tolong risetkan tren AI Agentic terbaru 2026`\n\n"
        "*4. Perintah Navigasi System*\n"
        "- `/start` : Ucapan selamat datang & status awal.\n"
        "- `/status` : Memeriksa kesiapan AI model, Claude CLI, & direktori.\n"
        "- `/reset` : Mengosongkan memori riwayat percakapan.\n"
        "- `/cwd` : Menampilkan atau mengubah lokasi direktori kerja.\n"
        "- `/help` : Menampilkan panduan bantuan ini."
    )
    await formatter.send_formatted_telegram_message(update, help_text)

@security.restricted
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reset command to clear conversation memory."""
    user_id = update.effective_user.id
    orchestrator.clear_history(user_id)
    await formatter.send_formatted_telegram_message(
        update,
        "*Ingatan Riwayat Percakapan*\n\n"
        "Riwayat percakapan telah berhasil dikosongkan. Saya siap memulai topik baru bersama Anda."
    )

@security.restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command to check system readiness."""
    cli_path = claude_service.find_claude_cli()
    cli_status = f"Tersedia (`{cli_path}`)" if cli_path else "Tidak ditemukan di PATH"
    
    ai_status = f"Tersedia Model (`{config.OPENAI_MODEL}`)" if config.OPENAI_API_KEY and config.OPENAI_API_KEY != "your_openai_api_key_here" else "Menggunakan Aturan Lokal"

    from datetime import datetime
    now_str = datetime.now().strftime("%A, %d %B %Y - %H:%M:%S WIB")

    status_text = (
        "*Laporan Status Kesiapan Sistem*\n\n"
        f"- *Waktu Sistem* : {now_str}\n"
        f"- *Orchestrator AI Model* : {ai_status}\n"
        f"- *Status Claude Code CLI* : {cli_status}\n"
        f"- *Direktori Kerja Aktif* : `{config.WORKSPACE_DIR}`\n"
        f"- *Obsidian Vault Path* : `{config.OBSIDIAN_VAULT_DIR}`\n"
        f"- *Akun Terverifikasi ID* : `{config.ALLOWED_USER_ID}`\n"
        f"- *Versi Python* : `{sys.version.split()[0]}`\n\n"
        "Sistem Hierarchical Multi-Agent & Second Brain siap beroperasi."
    )
    await formatter.send_formatted_telegram_message(update, status_text)

@security.restricted
async def cwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cwd command to view or update current working directory."""
    if context.args:
        new_dir = " ".join(context.args).strip()
        expanded_dir = os.path.expanduser(new_dir)
        if os.path.isabs(expanded_dir) and os.path.isdir(expanded_dir):
            config.WORKSPACE_DIR = expanded_dir
            await formatter.send_formatted_telegram_message(
                update,
                f"Direktori kerja telah berhasil diperbarui ke:\n`{config.WORKSPACE_DIR}`"
            )
        else:
            await formatter.send_formatted_telegram_message(
                update,
                "Mohon maaf, direktori yang Anda masukkan tidak valid atau tidak ditemukan.\n"
                "Harap masukkan jalur direktori absolut atau relative home yang valid."
            )
    else:
        await formatter.send_formatted_telegram_message(
            update,
            f"Direktori kerja aktif saat ini adalah:\n`{config.WORKSPACE_DIR}`\n\n"
            "Untuk mengubahnya, gunakan perintah:\n`/cwd /jalur/ke/direktori` atau `/cwd ~/nama_folder`"
        )

@security.restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle user message through LangGraph Multi-Agent StateGraph workflow with continuous typing indicator
    and human-like real-time live status updates without emojis.
    """
    prompt = update.message.text
    if not prompt:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(f"Message diterima dari User {user_id}")

    # Kirim balon status dinamis awal ke Telegram
    initial_status_text = (
        "*Sedang Diproses* (0 detik)\n"
        "Menelaah instruksi dan menyiapkan lingkungan kerja..."
    )
    status_message = None
    try:
        status_message = await update.message.reply_text(
            text=initial_status_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.debug(f"Gagal mengirim pesan status awal: {e}")

    start_time = time.time()
    last_edit_time = 0.0
    current_activity = "Menelaah instruksi dan menyiapkan lingkungan kerja..."
    pending_edit_task: Optional[asyncio.Task] = None

    async def apply_status_edit(text: str):
        nonlocal last_edit_time
        try:
            await status_message.edit_text(text=text, parse_mode="Markdown")
            last_edit_time = time.time()
        except Exception:
            pass

    async def live_progress_callback(activity_text: str, elapsed_seconds: int):
        nonlocal last_edit_time, current_activity, pending_edit_task
        if not status_message:
            return

        current_activity = activity_text
        updated_text = f"*Sedang Diproses* ({elapsed_seconds} detik)\n{activity_text}"
        now = time.time()

        # Hindari rate limit Telegram (minimal jeda 2.5 detik antar edit)
        if now - last_edit_time >= 2.5:
            if pending_edit_task and not pending_edit_task.done():
                pending_edit_task.cancel()
            await apply_status_edit(updated_text)
        else:
            if pending_edit_task is None or pending_edit_task.done():
                wait_seconds = 2.5 - (now - last_edit_time)
                async def delayed_update():
                    await asyncio.sleep(wait_seconds)
                    cur_elapsed = int(time.time() - start_time)
                    msg = f"*Sedang Diproses* ({cur_elapsed} detik)\n{current_activity}"
                    await apply_status_edit(msg)
                pending_edit_task = asyncio.create_task(delayed_update())

    # Start background task for continuous typing action
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(chat_id, context, stop_typing))

    initial_state = {
        "user_id": user_id,
        "user_prompt": prompt,
        "retrieved_context": "",
        "intent": "TASK",
        "chat_response": "",
        "claude_instruction": "",
        "worker_output": "",
        "evaluation_status": "SUCCESS",
        "eval_feedback": "",
        "retry_count": 0,
        "final_report": "",
        "progress_callback": live_progress_callback
    }

    try:
        result_state = await agent_app.ainvoke(initial_state)
        
        # Hapus balon status dinamis agar ruang obrolan tetap bersih
        if status_message:
            try:
                await status_message.delete()
            except Exception:
                pass

        intent = result_state.get("intent", "CHAT")
        chat_response = result_state.get("chat_response", "")
        final_report = result_state.get("final_report", "")

        if intent in ("CHAT", "BRAINSTORMING", "SAVE_NOTE") and chat_response:
            await formatter.send_formatted_telegram_message(update, chat_response)
        elif final_report:
            await formatter.send_formatted_telegram_message(update, final_report)
        elif chat_response:
            await formatter.send_formatted_telegram_message(update, chat_response)
        else:
            fallback = result_state.get("worker_output") or "Pekerjaan telah selesai diproses."
            await formatter.send_formatted_telegram_message(update, fallback)

    except Exception as err:
        logger.error(f"Kendala pada alur LangGraph Workflow: {err}")
        if status_message:
            try:
                await status_message.delete()
            except Exception:
                pass
        error_text = formatter.format_error_message(str(err))
        await formatter.send_formatted_telegram_message(update, error_text)
    finally:
        # Cancel pending status edit task if running
        if pending_edit_task and not pending_edit_task.done():
            pending_edit_task.cancel()
        # Stop background typing indicator
        stop_typing.set()
        await typing_task

def main():
    """Main application entrypoint."""
    validation_errors = config.validate_config()
    if validation_errors:
        print("PERINGATAN KONFIGURASI SISTEM:")
        for err in validation_errors:
            print(f"- {err}")
        print("\nHarap lengkapi berkas .env sebelum menjalankan bot.")

    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN belum dikonfigurasi pada .env. Aplikasi dihentikan.")
        sys.exit(1)

    print("Memulai Telegram Bot Claude Code (LangGraph Multi-Agent & Second Brain)...")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("cwd", cwd_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot berhasil berjalan dalam mode polling. Siap menerima instruksi.")
    app.run_polling()

if __name__ == "__main__":
    main()
