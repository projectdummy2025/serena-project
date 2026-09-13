import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file at project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

raw_allowed_id = os.getenv("ALLOWED_USER_ID", "").strip()
ALLOWED_USER_ID = int(raw_allowed_id) if raw_allowed_id.isdigit() else None

raw_workspace = os.getenv("WORKSPACE_DIR", str(Path(__file__).parent.parent.resolve())).strip()
WORKSPACE_DIR = os.path.expanduser(raw_workspace)

raw_vault = os.getenv("OBSIDIAN_VAULT_DIR", "~/obsidian_vault").strip()
OBSIDIAN_VAULT_DIR = os.path.expanduser(raw_vault)

# Ensure Obsidian Vault directories exist
for subfolder in ["Kotak Masuk", "Proyek Aktif", "Catatan Harian", "Profil & Keputusan", "Panduan & SOP"]:
    os.makedirs(os.path.join(OBSIDIAN_VAULT_DIR, subfolder), exist_ok=True)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

def validate_config() -> list[str]:
    """Validate project configuration and return missing items."""
    errors = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        errors.append("TELEGRAM_BOT_TOKEN belum diisi pada berkas .env")
    if not ALLOWED_USER_ID or ALLOWED_USER_ID == 123456789:
        errors.append("ALLOWED_USER_ID belum diisi dengan ID Telegram Anda pada berkas .env")
    return errors
