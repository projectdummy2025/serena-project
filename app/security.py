import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from app import config

logger = logging.getLogger(__name__)

UNAUTHORIZED_MESSAGE = (
    "Mohon maaf, akses tidak diberikan. "
    "Bot ini dikonfigurasi secara khusus dan hanya melayani pemilik akun yang terverifikasi."
)

def is_authorized(user_id: int) -> bool:
    """Check if the given user ID matches the allowed configuration."""
    if not config.ALLOWED_USER_ID:
        return False
    return user_id == config.ALLOWED_USER_ID

def restricted(func):
    """Decorator to restrict bot handler access exclusively to ALLOWED_USER_ID."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        user_id = user.id if user else None
        
        if not user_id or not is_authorized(user_id):
            user_name = user.username if user else "Unknown"
            logger.warning(f"Akses ditolak untuk User ID: {user_id} (@{user_name})")
            if update.message:
                await update.message.reply_text(UNAUTHORIZED_MESSAGE)
            elif update.callback_query:
                await update.callback_query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapped
