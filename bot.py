import os
import logging
from dotenv import load_dotenv

load_dotenv()  # must be before any local imports that read os.environ
logging.basicConfig(level=logging.INFO)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import db
import llm
import scraper
logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _student_name(update: Update) -> str:
    return update.effective_user.first_name or "there"


async def _ensure_student(update: Update):
    u = update.effective_user
    db.upsert_student(u.id, u.username or "", u.first_name or "")


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    name = _student_name(update)
    await update.message.reply_text(
        f"Hi {name}! I'm your course assistant.\n\n"
        "I can answer questions about course material, generate practice quizzes, "
        "and help you when you're stuck.\n\n"
        "Commands:\n"
        "/help — what I can do\n"
        "/quiz [topic] — generate a practice quiz\n"
        "/settings — configure reminders and language\n"
        "/struggles — see topics you've asked about most\n\n"
        "Or just ask me anything about the course."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*What I can do:*\n\n"
        "• Answer questions grounded in the syllabus and readings\n"
        "• Generate multiple-choice quizzes on any topic\n"
        "• Track concepts you've struggled with over the semester\n"
        "• Send reminders about deadlines and readings (configure via /settings)\n\n"
        "Just type a question to get started.",
        parse_mode="Markdown",
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    keyboard = [
        [
            InlineKeyboardButton("Language: English", callback_data="set_lang_en"),
            InlineKeyboardButton("Language: Chinese", callback_data="set_lang_zh"),
        ],
        [
            InlineKeyboardButton("Reminders: Daily", callback_data="set_freq_daily"),
            InlineKeyboardButton("Reminders: Weekly", callback_data="set_freq_weekly"),
            InlineKeyboardButton("Reminders: Off", callback_data="set_freq_off"),
        ],
    ]
    await update.message.reply_text(
        "Configure your preferences:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = query.from_user.id

    data = query.data
    if data.startswith("set_lang_"):
        lang = data.split("_")[-1]
        db.update_setting(tid, "language", lang)
        label = "English" if lang == "en" else "Chinese"
        await query.edit_message_text(f"Language set to {label}.")
    elif data.startswith("set_freq_"):
        freq = data.split("_")[-1]
        db.update_setting(tid, "reminder_freq", freq)
        await query.edit_message_text(f"Reminder frequency set to: {freq}.")


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    topic = " ".join(context.args) if context.args else "the most recent readings"
    await update.message.reply_text(f"Generating a quiz on '{topic}'...")
    materials = await scraper.fetch_course_materials()
    quiz_text = llm.generate_quiz(topic, materials)
    await update.message.reply_text(quiz_text)


async def cmd_struggles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    tid = update.effective_user.id
    top = db.get_top_struggles(tid)
    if not top:
        await update.message.reply_text(
            "No struggle topics recorded yet — keep asking questions!"
        )
        return
    lines = "\n".join(f"• {s['topic']} (asked {s['count']}×)" for s in top)
    await update.message.reply_text(f"*Topics you've returned to most:*\n{lines}", parse_mode="Markdown")


# ── General message handler ───────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    tid = update.effective_user.id
    user_text = update.message.text

    db.save_message(tid, "user", user_text)
    history = db.get_history(tid, limit=10)
    materials = await scraper.fetch_course_materials()

    reply = llm.chat(
        history=history[:-1],  # exclude the message we just saved
        user_message=user_text,
        course_context=materials,
        student_name=_student_name(update),
    )

    db.save_message(tid, "assistant", reply)
    await update.message.reply_text(reply)


# ── Main ──────────────────────────────────────────────────────────────────────

async def post_init(application):
    """Fetch and cache course materials at startup."""
    logger.info("Fetching course site content...")
    content = await scraper.fetch_course_materials()
    if content:
        logger.info(f"Course site loaded: {len(content)} chars")
    else:
        logger.warning("Could not load course site content.")


def main():
    db.init_db()

    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN not set. Copy .env.example to .env and fill it in.")

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("struggles", cmd_struggles))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^set_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
