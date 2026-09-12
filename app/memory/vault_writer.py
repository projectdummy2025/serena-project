import os
from datetime import datetime
import logging
import frontmatter

from app import config

logger = logging.getLogger(__name__)

def append_to_daily_log(title: str, content: str) -> str:
    """
    Append an entry to today's Daily Log in the Obsidian Vault (02-Daily-Logs/YYYY-MM-DD.md).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M:%S")
    daily_log_dir = os.path.join(config.OBSIDIAN_VAULT_DIR, "02-Daily-Logs")
    os.makedirs(daily_log_dir, exist_ok=True)
    
    file_path = os.path.join(daily_log_dir, f"{today_str}.md")
    
    entry_header = f"\n\n### [{now_time_str}] {title}\n\n"
    full_entry = entry_header + content.strip() + "\n"
    
    if os.path.exists(file_path):
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(full_entry)
    else:
        post = frontmatter.Post(
            content=f"# Daily Log - {today_str}\n" + full_entry,
            tags=["daily-log", "second-brain"],
            date=today_str
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
            
    logger.info(f"Menulis entri log harian ke Obsidian: {file_path}")
    return file_path

def create_note(folder: str, filename: str, content: str, tags: list = None) -> str:
    """
    Create a markdown note inside specified Obsidian folder with frontmatter.
    """
    target_dir = os.path.join(config.OBSIDIAN_VAULT_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    if not filename.endswith(".md"):
        filename += ".md"
        
    file_path = os.path.join(target_dir, filename)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    post = frontmatter.Post(
        content=content.strip(),
        tags=tags or ["note"],
        date=today_str
    )
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
        
    logger.info(f"Membuat catatan Obsidian di: {file_path}")
    return file_path

def read_note(folder: str, filename: str) -> str:
    """Read contents of an Obsidian markdown note."""
    if not filename.endswith(".md"):
        filename += ".md"
    file_path = os.path.join(config.OBSIDIAN_VAULT_DIR, folder, filename)
    if not os.path.exists(file_path):
        return f"Berkas catatan tidak ditemukan: {file_path}"
        
    with open(file_path, "r", encoding="utf-8") as f:
        post = frontmatter.load(f)
        return post.content

def get_user_profile() -> str:
    """
    Retrieve user personalization profile and explicit preferences from Obsidian (03-Decisions/User_Profile.md).
    """
    file_path = os.path.join(config.OBSIDIAN_VAULT_DIR, "03-Decisions", "User_Profile.md")
    if not os.path.exists(file_path):
        initial_profile = (
            "# Profil & Preferensi Pengguna\n\n"
            "## Aturan Pemformatan :\n"
            "- DILARANG MENGGUNAKAN EMOJI SAMA SEKALI.\n"
            "- Wajib spasi sebelum titik dua (contoh: `Label : Isi`).\n\n"
            "## Preferensi Kerja & Kebiasaan :\n"
            "- Pendampingan aktif untuk sesi brainstorming dan penataan rutinitas/kebiasaan.\n"
            "- Kurasi memori proaktif ke folder 00-Inbox Obsidian Second Brain.\n"
        )
        create_note("03-Decisions", "User_Profile.md", initial_profile, tags=["user-profile", "preferences"])
        return initial_profile
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            return post.content
    except Exception:
        return ""

