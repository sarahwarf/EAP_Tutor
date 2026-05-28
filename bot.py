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
SETUP_CODE = os.environ.get("SETUP_CODE", "")
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
        # Store unit ID and context so they're available throughout the session
        context.user_data["current_unit_id"] = unit_id
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
    tid = update.effective_user.id
    # Env var takes priority (legacy / override)
    if INSTRUCTOR_ID and tid == INSTRUCTOR_ID:
        return True
    # DB-registered instructor (set via /setup command)
    stored = db.get_setting("instructor_id")
    return stored is not None and tid == int(stored)


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow an instructor to register themselves by providing the setup code."""
    if not SETUP_CODE:
        await update.message.reply_text("Setup code not configured on this bot.")
        return

    # If someone is already registered, block further attempts
    existing = db.get_setting("instructor_id")
    if existing:
        if update.effective_user.id == int(existing):
            await update.message.reply_text("You are already registered as the instructor.")
        else:
            await update.message.reply_text("An instructor is already registered on this bot.")
        return

    provided = " ".join(context.args) if context.args else ""
    if provided == SETUP_CODE:
        db.set_setting("instructor_id", str(update.effective_user.id))
        await update.message.reply_text(
            "✅ You're registered. Let's set up your course now.\n\n"
            "I'll ask you 10 questions. At the end, Nova will be ready for your students. "
            "Type /skiponboarding at any time to finish early and set things up later.\n\n"
            "─────────────────\n"
            "*Step 1 of 10*\n"
            "What is the name of your course?\n"
            "_e.g. EAP 100 Art in the City_",
            parse_mode="Markdown",
        )
        context.user_data["onboarding"] = {"step": "course_name", "units": {}}
    else:
        await update.message.reply_text("Incorrect setup code. Try again or check your .env.")


# ── Onboarding flow ───────────────────────────────────────────────────────────

async def _onboarding_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle each step of the instructor onboarding flow."""
    ob = context.user_data.get("onboarding", {})
    step = ob.get("step")
    text = update.message.text.strip() if update.message.text else ""

    async def ask(msg):
        await update.message.reply_text(msg, parse_mode="Markdown")

    if step == "course_name":
        db.set_setting("course_name", text)
        ob["step"] = "instructor_name"
        await ask("*Step 2 of 10*\nWhat is your name?\n_e.g. Sarah Warfield_")

    elif step == "instructor_name":
        db.set_setting("instructor_name", text)
        ob["step"] = "booking_link"
        await ask(
            "*Step 3 of 10*\n"
            "What's your booking link so students can schedule time with you?\n"
            "_e.g. https://calendly.com/yourname — or type 'skip'_"
        )

    elif step == "booking_link":
        if text.lower() != "skip":
            db.set_setting("booking_link", text)
        ob["step"] = "site_url"
        await ask(
            "*Step 4 of 10*\n"
            "What is your course website URL? Nova will read it automatically.\n"
            "_e.g. https://sites.google.com/view/yourcourse/home — or type 'skip'_"
        )

    elif step == "site_url":
        if text.lower() != "skip":
            db.set_setting("site_url", text)
        ob["step"] = "course_intro"
        await ask(
            "*Step 5 of 10*\n"
            "Upload your course introduction document — your first-day handout, "
            "syllabus overview, or any document that explains the course to students. "
            "Nova will use it to answer questions about how the course works.\n\n"
            "_Send the file now, or type 'skip'_"
        )

    elif step == "course_intro":
        # Text 'skip' — file upload is handled separately in handle_onboarding_file
        ob["step"] = "unit_name"
        ob["unit_number"] = 1
        await ask(
            "*Step 6 of 10*\n"
            "Now let's set up your units. You can add up to 6.\n\n"
            "*Unit 1 — what is it called?*\n"
            "_e.g. Unit 1: Foundations in Art Theory_"
        )

    elif step == "unit_name":
        n = ob.get("unit_number", 1)
        ob.setdefault("units", {})[f"unit{n}"] = {"name": text, "materials": []}
        ob["step"] = "unit_question"
        await ask(
            f"*Unit {n} — what is the guiding question?*\n"
            "_e.g. How does art theory help us understand art's role in society? — or type 'skip'_"
        )

    elif step == "unit_question":
        n = ob.get("unit_number", 1)
        if text.lower() != "skip":
            ob["units"][f"unit{n}"]["guiding_question"] = text
        ob["step"] = "unit_skill"
        await ask(
            f"*Unit {n} — what academic English skill does this unit focus on?*\n"
            "_e.g. Language for transitions — or type 'skip'_"
        )

    elif step == "unit_skill":
        n = ob.get("unit_number", 1)
        if text.lower() != "skip":
            skill = text
            ob["units"][f"unit{n}"]["skill_focus"] = skill
            ob["units"][f"unit{n}"]["skill_lesson"] = skill.lower().replace(" ", "_")
        ob["step"] = "unit_more"
        count = len(ob["units"])
        if count < 6:
            await ask(
                f"✓ Unit {n} saved.\n\n"
                f"Do you have another unit to add? _(you've added {count} so far, max 6)_\n"
                "Type *yes* to add another or *done* to finish."
            )
        else:
            await _onboarding_complete(update, context)
            return

    elif step == "unit_more":
        if text.lower() in ("yes", "y"):
            n = ob.get("unit_number", 1) + 1
            ob["unit_number"] = n
            ob["step"] = "unit_name"
            await ask(
                f"*Unit {n} — what is it called?*\n"
                "_e.g. Unit 2: Art and Public Space_"
            )
        else:
            await _onboarding_complete(update, context)
            return

    context.user_data["onboarding"] = ob


async def handle_onboarding_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a file uploaded during the course intro step of onboarding."""
    ob = context.user_data.get("onboarding", {})
    if ob.get("step") != "course_intro":
        return False  # Not in the right onboarding step

    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    file_bytes = bytes(await file.download_as_bytearray())
    try:
        text, _ = extractor.extract(file_bytes, doc.file_name or "intro.txt")
    except Exception as e:
        await update.message.reply_text(f"Couldn't read that file: {e}. Type 'skip' to continue.")
        return True

    if text.strip():
        db.set_setting("course_intro", text.strip())
        await update.message.reply_text("✓ Course intro saved.")
    else:
        await update.message.reply_text("File seemed empty. You can upload it later via Telegram.")

    # Advance to next step
    ob["step"] = "course_intro"
    context.user_data["onboarding"] = ob
    await _onboarding_next(update, context)
    return True


async def _onboarding_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save all onboarding data and show the completion message."""
    import json as _json
    ob = context.user_data.get("onboarding", {})
    units = ob.get("units", {})

    # Fill in defaults for any missing fields
    for uid, u in units.items():
        u.setdefault("guiding_question", "")
        u.setdefault("skill_focus", "")
        u.setdefault("skill_lesson", "")
        u.setdefault("artwork", "")

    if units:
        db.set_setting("units_config", _json.dumps(units))

    # Build summary
    course = db.get_setting("course_name") or COURSE_NAME
    instructor = db.get_setting("instructor_name") or INSTRUCTOR_NAME
    booking = db.get_setting("booking_link") or "not set"
    site = db.get_setting("site_url") or "not set"
    intro = "uploaded ✓" if db.get_setting("course_intro") else "not uploaded"
    unit_lines = "\n".join(
        f"  • {u.get('name', f'Unit {i+1}')} — {u.get('skill_focus', 'no skill set')}"
        for i, u in enumerate(units.values())
    ) or "  none added"

    context.user_data.pop("onboarding", None)

    await update.message.reply_text(
        f"🎉 *Nova is set up for your course.*\n\n"
        f"*Course:* {course}\n"
        f"*Instructor:* {instructor}\n"
        f"*Booking link:* {booking}\n"
        f"*Course site:* {site}\n"
        f"*Course intro:* {intro}\n"
        f"*Units:*\n{unit_lines}\n\n"
        "─────────────────\n"
        "From here, use Telegram to upload readings, transcripts, and skill content "
        "as you build the course. Type /help for the full list of instructor commands.\n\n"
        "If you want to change how Nova behaves — her pedagogical approach, the rules "
        "she follows, or how she scaffolds students — you can fork the code and customize it:\n"
        "github.com/sarahwarf/EAP\\_Tutor",
        parse_mode="Markdown",
    )


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

    # During onboarding, the course_intro step accepts a file upload
    if context.user_data.get("onboarding", {}).get("step") == "course_intro":
        handled = await handle_onboarding_file(update, context)
        if handled:
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

async def cmd_skiponboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let the instructor bail out of onboarding early."""
    if not _is_instructor(update):
        return
    context.user_data.pop("onboarding", None)
    await update.message.reply_text(
        "Onboarding skipped. Nova is still usable — you can always add content via Telegram.\n"
        "Type /help for the full list of instructor commands."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_student(update)
    tid = update.effective_user.id
    user_text = update.message.text

    # Route instructor messages to onboarding if that flow is active
    if context.user_data.get("onboarding") and _is_instructor(update):
        await _onboarding_next(update, context)
        return

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

        # Cumulative skills: all skills taught up to this unit, with lesson content
        unit_id = context.user_data.get("current_unit_id", "")
        skill_texts = study.get_cumulative_skill_texts(unit_id) if unit_id else []
        if skill_texts:
            skills_block = "\n\n".join(
                f"### {name}\n{text}" for name, text in skill_texts
            )
            skills_section = (
                "Skills taught so far in this course — reinforce these naturally "
                "in your responses, especially when helping the student speak or write:\n\n"
                + skills_block
            )
        else:
            skills_section = ""

        purpose_note = f"\nThe student is reading this because: {study_purpose}" if study_purpose else ""
        course_context = (
            (f"{skills_section}\n\n" if skills_section else "")
            + (f"{unit_header}\n\n" if unit_header else "")
            + f"The student is studying: {study_title}{purpose_note}\n\n{study_material}"
        )

        # Detect and log what the student is struggling with
        concept = llm.detect_struggle(user_text, study_title)
        if concept:
            db.log_struggle(tid, concept)
    else:
        course_context = await scraper.fetch_course_materials()

    # Prepend course intro to every conversation (foundational, always present)
    course_intro = study.get_course_intro()
    if course_intro:
        course_context = f"## Course Introduction\n{course_intro}\n\n{course_context}"

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
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("study", cmd_study))
    app.add_handler(CommandHandler("struggles", cmd_struggles))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("clearnotes", cmd_clearnotes))
    app.add_handler(CommandHandler("materials", cmd_materials))
    app.add_handler(CommandHandler("deletematerial", cmd_deletematerial))
    app.add_handler(CommandHandler("skiponboarding", cmd_skiponboarding))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^set_"))
    app.add_handler(CallbackQueryHandler(study_callback, pattern="^study_"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_instructor_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
