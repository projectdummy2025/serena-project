"""
Utility module for text formatting, chunking long messages, and system error formatting.
"""

def format_start_message() -> str:
    """Fallback static welcome message if AI API is completely offline."""
    return (
        "Selamat datang. Saya Serena.\n\n"
        "Ada yang bisa saya bantu hari ini, atau ada topik menarik yang ingin kita bahas?"
    )

def format_completion_message(summary_or_output: str) -> str:
    """Format the final completion message smoothly without rigid headers."""
    return summary_or_output.strip()

def format_error_message(error_text: str) -> str:
    """Format error notification message."""
    return (
        "Mohon maaf, terjadi kendala saat saya melaksanakan tugas pekerjaan tersebut.\n\n"
        "Rincian kendala:\n"
        f"{error_text}\n\n"
        "Silakan periksa kembali instruksi Anda atau konfigurasi sistem."
    )

import re

def fix_colon_spacing(text: str) -> str:
    """
    Ensure every label colon has a mandatory space BEFORE it.
    Example: 'Manajemen Tugas: Prioritas' -> 'Manajemen Tugas : Prioritas'
    Excludes URLs (http://, https://) and time formats (21:22:00).
    Also strips unrendered Markdown '>' blockquote chars.
    """
    if not text:
        return ""
    lines = text.split("\n")
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("> "):
            line = line.replace("> ", "", 1)
        elif stripped == ">":
            continue

        if stripped.startswith(("http://", "https://", "```", "<pre>")):
            new_lines.append(line)
            continue
        
        def replacer(m):
            before = m.group(1)
            after = m.group(2)
            if before.lower() in ("http", "https") or (before.isdigit() and after.isdigit()):
                return m.group(0)
            return f"{before} : {after}"

        fixed_line = re.sub(r"([^\s:]+)\s*:\s+([^\s])", replacer, line)
        new_lines.append(fixed_line)
    return "\n".join(new_lines)

def split_long_message(text: str, max_length: int = 3900) -> list[str]:
    """
    Split a long text string into clean chunks matching Telegram's character limits.
    """
    if not text:
        return []
    
    text = fix_colon_spacing(text)
    
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    lines = text.split("\n")
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
                current_chunk = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
            
    if current_chunk.strip():
        chunks.append(current_chunk.rstrip())
        
    return chunks

async def send_formatted_telegram_message(update, text: str):
    """
    Send formatted Markdown text chunks to Telegram.
    Falls back gracefully to plain text if Telegram Markdown parsing fails.
    """
    if not text:
        return
        
    from telegram.constants import ParseMode
    import logging
    logger = logging.getLogger(__name__)

    formatted_text = fix_colon_spacing(text)
    chunks = split_long_message(formatted_text)
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception as err:
            logger.debug(f"Percobaan Markdown gagal ({err}), mengabaikan format dan mengirim teks polos.")
            try:
                await update.message.reply_text(chunk)
            except Exception as final_err:
                logger.error(f"Gagal mengirim pesan ke Telegram: {final_err}")


