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
import study
import extractor

INSTRUCTOR_ID = int(os.environ.get("INSTRUCTOR_TELEGRAM_ID", "0"))
COURSE_NAME = os.environ.get("COURSE_NAME", "the course")
INSTRUCTOR_NAME = os.environ.get("INSTRUCTOR_NAME", "the instructor")
logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _student_name(update: Update) -> str:
    return update.effective_user.first_name or "there"


async def _ensure_student(update: Update):
    u = update.effective_user
    db.upsert_student(u.id, u.username or "", u.first_name or "")


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    existing = db.get_student(update.effective_user.id)
    await _ensure_student(update)
    name = _student_name(update)

    if existing:
        # Returning student
        await update.message.reply_text(
            f"Hi {name}! How can I help you today? "
            f"(Type /help if you want a reminder of everything I can do.)"
        )
    else:
        # First time
        await update.message.reply_text(
            f"Hi {name}! My name is Nova, and I'm the course assistant for {COURSE_NAME}.\n\n"
            "You can ask me anything about the course — how it's set up, what's expected, "
            "assignment requirements, grading, important dates, or course policies. "
            "If you want to review course material or work on a specific skill, I can help with that too. "
            "And if you're stuck on something, I can help you figure out what's going on and what to do next.\n\n"
            "Use /quiz to generate practice questions on any topic, "
            "or /help if you want a reminder of what I can do.\n\n"
            "Just type your question to get started."
        )


NORTH_STAR = (
    "Here's what I can do:\n\n"
    "📋 *Course questions* — Ask me anything about the course: how it's set up, "
    "what assignments require, how grading works, important dates, or policies. "
    f"I answer strictly from the course site, so if something isn't there, I'll tell you to ask {INSTRUCTOR_NAME}.\n\n"
    "📖 *Study sessions* — Type /study to pick a unit and a reading. "
    "Once you're in a session, ask me to explain concepts, summarize sections, or "
    "talk through what you're finding confusing. I'll help you understand the material "
    "without just reading it back to you.\n\n"
    "🧠 *Practice quizzes* — Type /quiz at any time. "
    "If you're in a study session, the quiz will focus on the concepts you've returned to most. "
    "If you're not, just add a topic: /quiz Bourdieu or /quiz citation formats.\n\n"
    "📌 *Your struggle topics* — Type /struggles to see which concepts have come up most "
    "across your study sessions. Useful before a quiz or class discussion.\n\n"
    "⚙️ *Preferences* — Type /settings to choose your language (English or Chinese) "
    "and how often you want reminders.\n\n"
    "I only know what's on the course site. I don't have access to Brightspace, "
    "your grades, or anything outside this course."
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(NORTH_STAR, parse_mode="Markdown")


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


async def cmd_study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    units = study.get_unit_list()
    if not units:
        await update.message.reply_text("No units are available yet.")
        return
    keyboard = [
        [InlineKeyboardButton(u["name"], callback_data=f"study_unit_{u['id']}")]
        for u in units
    ]
    await update.message.reply_text(
        "Which unit are you working on?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def study_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("study_unit_"):
        unit_id = data.replace("study_unit_", "")
        materials = study.get_materials_for_unit(unit_id)
        if not materials:
            await query.edit_message_text("No materials available for that unit yet.")
            return
        # Store unit context now so it's available throughout the session
        context.user_data["unit_context"] = study.get_unit_context(unit_id)
        keyboard = [
            [InlineKeyboardButton(m["title"], callback_data=f"study_mat_{unit_id}_{m['id']}")]
            for m in materials
        ]
        await query.edit_message_text(
            "Which material are you working on?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("study_mat_"):
        _, _, unit_id, mat_id = data.split("_", 3)
        materials = study.get_materials_for_unit(unit_id)
        material = next((m for m in materials if m["id"] == mat_id), None)
        if not material:
            await query.edit_message_text("Material not found.")
            return
        content = study.load_material_text(material["file"])
        if not content:
            await query.edit_message_text(
                f"The content for {material['title']} hasn't been added yet."
            )
            return
        # Store material; ask for reading purpose before opening the session
        context.user_data["study_material"] = content
        context.user_data["study_title"] = material["title"]
        context.user_data["awaiting_study_purpose"] = True
        await query.edit_message_text(
            f"Before we start — why are you reading *{material['title']}* today?\n\n"
            "For example: getting ready for class discussion, working on an assignment, "
            "reviewing before a quiz, or just trying to understand it.",
            parse_mode="Markdown",
        )


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    tid = update.effective_user.id

    study_material = context.user_data.get("study_material")
    study_title = context.user_data.get("study_title")

    if study_material:
        # In a study session — use the material and the student's logged struggles
        struggles = db.get_top_struggles(tid, n=5)
        struggle_topics = [s["topic"] for s in struggles] if struggles else None
        if struggle_topics:
            await update.message.reply_text(
                f"Generating a quiz based on what you struggled with in *{study_title}*...",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"Generating a quiz on *{study_title}*...",
                parse_mode="Markdown",
            )
        quiz_text = llm.generate_quiz(study_title, study_material, struggle_topics=struggle_topics)
    else:
        # Outside a study session — general quiz
        topic = " ".join(context.args) if context.args else "the course material"
        await update.message.reply_text(f"Generating a quiz on '{topic}'...")
        materials = await scraper.fetch_course_materials()
        quiz_text = llm.generate_quiz(topic, materials)

    await update.message.reply_text(quiz_text)


# ── Instructor commands ───────────────────────────────────────────────────────

def _is_instructor(update: Update) -> bool:
    return update.effective_user.id == INSTRUCTOR_ID


async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_instructor(update):
        return
    note = " ".join(context.args)
    if not note:
        await update.message.reply_text("Usage: /note Your observation here")
        return
    db.save_instructor_note(note)
    await update.message.reply_text("Note saved.")


async def cmd_clearnotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_instructor(update):
        return
    db.clear_instructor_notes()
    await update.message.reply_text("All instructor notes cleared.")


async def cmd_materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all uploaded materials."""
    if not _is_instructor(update):
        return
    all_materials = db.get_all_materials()
    if not all_materials:
        await update.message.reply_text("No materials uploaded yet.")
        return
    lines = "\n".join(f"[{m['id']}] {m['tag']} ({m['file_type']}) — {m['uploaded_at'][:10]}" for m in all_materials)
    await update.message.reply_text(f"*Uploaded materials:*\n{lines}", parse_mode="Markdown")


async def cmd_deletematerial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a material by ID."""
    if not _is_instructor(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /deletematerial <id>")
        return
    try:
        material_id = int(context.args[0])
        db.delete_material(material_id)
        await update.message.reply_text(f"Material {material_id} deleted.")
    except ValueError:
        await update.message.reply_text("Please provide a valid numeric ID.")


async def handle_instructor_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a file sent by the instructor with a caption as the tag."""
    if not _is_instructor(update):
        return

    doc = update.message.document
    caption = (update.message.caption or "").strip()

    if not caption:
        await update.message.reply_text(
            "Please include a caption describing what this is, e.g. 'unit1 reading2' or 'midterm rubric'."
        )
        return

    await update.message.reply_text(f"Processing '{caption}'...")

    # Download file
    file = await context.bot.get_file(doc.file_id)
    file_bytes = bytes(await file.download_as_bytearray())

    # Extract text
    try:
        text, file_type = extractor.extract(file_bytes, doc.file_name or "file.txt")
    except Exception as e:
        await update.message.reply_text(f"Could not read file: {e}")
        return

    if not text.strip():
        await update.message.reply_text("The file appears to be empty or unreadable.")
        return

    db.save_material(caption, text, file_type)
    await update.message.reply_text(
        f"Saved as '{caption}' ({file_type}, {len(text):,} chars)."
    )


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

    # Capture reading purpose before starting the session proper
    if context.user_data.get("awaiting_study_purpose"):
        context.user_data["study_purpose"] = user_text
        context.user_data.pop("awaiting_study_purpose")
        title = context.user_data.get("study_title", "this material")
        await update.message.reply_text(
            f"Got it. Ask me anything about *{title}*.",
            parse_mode="Markdown",
        )
        return

    db.save_message(tid, "user", user_text)
    history = db.get_history(tid, limit=10)

    # If a study session is active, use that material as context
    # Otherwise fall back to the course site
    study_material = context.user_data.get("study_material")
    study_title = context.user_data.get("study_title")
    if study_material:
        study_purpose = context.user_data.get("study_purpose", "")
        unit_ctx = context.user_data.get("unit_context", {})

        # Build unit-level framing for Nova
        unit_parts = []
        if unit_ctx.get("guiding_question"):
            unit_parts.append(f"Unit guiding question: {unit_ctx['guiding_question']}")
        if unit_ctx.get("skill_focus"):
            skill = unit_ctx["skill_focus"]
            unit_parts.append(
                f"Speaking & listening skill focus for this unit: {skill}. "
                f"There is a dedicated lesson on this in the course skills module."
            )
        if unit_ctx.get("artwork"):
            unit_parts.append(f"Featured artwork for this unit: {unit_ctx['artwork']}")
        unit_header = "\n".join(unit_parts)

        purpose_note = f"\nThe student is reading this because: {study_purpose}" if study_purpose else ""
        course_context = (
            f"{unit_header}\n\n" if unit_header else ""
        ) + f"The student is studying: {study_title}{purpose_note}\n\n{study_material}"

        # Detect and log what the student is struggling with
        concept = llm.detect_struggle(user_text, study_title)
        if concept:
            db.log_struggle(tid, concept)
    else:
        course_context = await scraper.fetch_course_materials()

    # Pull this week's instructor notes and include them in every conversation
    instructor_notes = db.get_recent_instructor_notes(days=7)
    notes_context = "\n".join(f"- {n['note']}" for n in instructor_notes) if instructor_notes else ""

    reply = llm.chat(
        history=history[:-1],
        user_message=user_text,
        course_context=course_context,
        instructor_notes=notes_context,
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
    app.add_handler(CommandHandler("study", cmd_study))
    app.add_handler(CommandHandler("struggles", cmd_struggles))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("clearnotes", cmd_clearnotes))
    app.add_handler(CommandHandler("materials", cmd_materials))
    app.add_handler(CommandHandler("deletematerial", cmd_deletematerial))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^set_"))
    app.add_handler(CallbackQueryHandler(study_callback, pattern="^study_"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_instructor_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
