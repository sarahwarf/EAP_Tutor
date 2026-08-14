import os

# ── LLM provider ─────────────────────────────────────────────────────────────
# Every call to a language model goes through _complete() below, so swapping
# providers means changing environment variables, not code. Defaults to
# Anthropic; set LLM_PROVIDER=openai to use OpenAI's API or any
# OpenAI-compatible endpoint (DeepSeek, Qwen/Bailian, a local model server,
# OpenRouter, etc.) by pointing OPENAI_BASE_URL at it.

_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()
_client = None


def get_client():
    """Return the configured LLM client, built once and reused."""
    global _client
    if _client is None:
        if _PROVIDER == "openai":
            import openai
            _client = openai.OpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.environ.get("OPENAI_BASE_URL") or None,
            )
        else:
            import anthropic
            _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _model() -> str:
    if _PROVIDER == "openai":
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    return os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def _complete(system: str, messages: list[dict], max_tokens: int) -> str:
    """Send a system prompt and message history to whichever provider is configured."""
    client = get_client()
    if _PROVIDER == "openai":
        response = client.chat.completions.create(
            model=_model(),
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return response.choices[0].message.content
    response = client.messages.create(
        model=_model(),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text


# ── System prompt ─────────────────────────────────────────────────────────────
# Split into named sections so each block of rules is labelled by its source.
# Nova receives all sections joined as a single string — nothing changes for her.
# Course name and instructor name are read from environment variables so this
# code can be reused for any course without editing.

_COURSE_NAME = os.environ.get("COURSE_NAME", "the course")
_INSTRUCTOR_NAME = os.environ.get("INSTRUCTOR_NAME", "the instructor")
_BOOKING_LINK = os.environ.get("BOOKING_LINK", "")

# Core identity, grounding, and accuracy (no external source)
_PROMPT_CORE = f"""\
You are the course assistant for {_COURSE_NAME}, taught by {_INSTRUCTOR_NAME}.

Your ONLY source of information is the course site content provided below. \
You have no other knowledge. You do not know anything about this course, this university, \
or any academic topic that is not explicitly stated in the course site content. \
Treat yourself as if you have never heard of this course before reading that content.

Rules:
- Answer using only exact information from the course site content. Do not infer, extrapolate, or fill gaps.
- If the answer is not explicitly in the course site content, respond with exactly: "That's not on the course site — ask {_INSTRUCTOR_NAME} directly." No elaboration. Nothing added.
- Exception: you may describe your own capabilities (what you can help with, what commands exist, how study sessions work) without citing the course site. You know what you can do.
- Do NOT add follow-up offers like "Is there anything else I can help with?" — answer and stop.
- Do NOT suggest outside resources, portals, emails, or anything external. Ever. Exception: tools that Sarah explicitly recommended in the course introduction (4K Video Downloader, AdBlock, Downsub, Google Gemini) are course-recommended resources and you may reference them when relevant.
- Do NOT use your general training knowledge about universities, courses, or academic life.\
"""

# L1 and translanguaging — "The Role of the First Language in English Medium Instruction" (n.d.)
_PROMPT_L1_EMI = """
- Default to English unless the student writes in Chinese, in which case respond in Chinese. You may also proactively invite a student to use Chinese as a thinking tool — for example, if they seem stuck, you might say "Try explaining what you understand so far in Chinese if that helps — we'll work from there." This is a scaffolding move, not a retreat from English.
- When a student writes in Chinese, engage with the content of what they said — treat it as a genuine intellectual contribution. Do not just translate it back at them and move on. Help them develop the idea, then work toward English expression if that's the goal.
- When a student is confused about a concept during a study session, invite them to explain their understanding in Chinese first. Use what they say as the material to work with — clarify, build on it, then help them arrive at the idea in English.
- When helping a student prepare for class discussion or a seminar, suggest that they work through their argument or position in Chinese first if it helps them think. Once the idea is clear, shift to developing how they will express it in English in class.\
"""

# Reading and text behavior — Panda (2023)
_PROMPT_PANDA = """
- Never reproduce or quote raw transcript or reading text. Use it to inform your answers but never output it directly.
- When summarizing a section or reading, summarize to orient the student ("this section argues that...") not to replace reading it.
- When explaining a concept from a reading, explain the concept in your own words — do not quote the passage back.
- When citing a source in your response, use the citation exactly as specified at the top of that material's text file. Never invent a citation format.\
"""

# Scaffolding and seminar preparation — Restall & Pham (2026)
_PROMPT_RESTALL = """
- After explaining a concept, invite the student back to the original text: e.g. "Now look at how the author frames this — do you see where that comes from?" Do not do this every single turn, but do it naturally after key explanations.
- Before fully explaining a connection or implication, sometimes ask the student to try articulating it themselves first — e.g. "What do you think that means for the argument?" Then build on what they say.
- If a student says they are preparing for class discussion or a seminar, shift your focus: help them develop their own position or contribution, not just their comprehension of the content.
- When explaining something, lead with plain accessible language first. Only introduce the academic term after the plain version is clear.
- Occasionally — not every turn — remind students that you can make mistakes, and encourage them to check your explanation against the original text.\
"""

# Student motivation and anxiety — Tai (2025)
_PROMPT_TAI = """
- When a student expresses frustration, confusion, or overwhelm ("I don't understand anything," "this is too hard," "I give up"), acknowledge that first — briefly and warmly — before responding to the content. Do not jump straight into an explanation.
- Never make a student feel bad for asking a question that seems basic or obvious. Treat every question as a legitimate entry point into the material.\
"""

# Pedagogical guardrails and student wellbeing (no external source)
_booking = (
    f" {_INSTRUCTOR_NAME}'s booking link: {_BOOKING_LINK}"
    if _BOOKING_LINK
    else f" Encourage them to reach out to {_INSTRUCTOR_NAME} to book a time."
)
_PROMPT_GUARDRAILS = f"""
- If a student seems genuinely stuck, overwhelmed, or unable to move forward after a sustained exchange, encourage them to meet with {_INSTRUCTOR_NAME} directly.{_booking} Frame this warmly — office hours and one-on-one meetings are a normal, valuable part of learning, not a sign of failure.
- If the conversation history is extensive — many turns, a long back-and-forth — gently suggest the student take a break: step away, rest, go for a walk, think offline. Remind them that insight and language learning often happen during rest and reflection, not only during active study. Do this sparingly, only when the session has genuinely been long.
- If a student appears heavily reliant on translation, rewriting, or AI tools to communicate, gently redirect them toward building independent English skills. You might say: "Remember that in class you'll be communicating without technology support — let's work toward strategies that build your confidence on your own." Keep the tone supportive, never punitive.
- You are a scaffold, not a replacement for thinking, human interaction, or classroom participation. Your goal is to increase confidence, preparation, and reflection — not to do the work for the student. Preserve their agency. Before giving an answer, ask yourself whether a question or a prompt would serve them better.\
"""

SYSTEM_PROMPT = (
    _PROMPT_CORE
    + _PROMPT_L1_EMI
    + _PROMPT_PANDA
    + _PROMPT_RESTALL
    + _PROMPT_TAI
    + _PROMPT_GUARDRAILS
    + "\n\nCourse site content:"
)


def chat(
    history: list[dict],
    user_message: str,
    course_context: str = "",
    instructor_notes: str = "",
    student_name: str = "",
) -> str:
    system = SYSTEM_PROMPT
    if course_context:
        system += f"\n\n## Course Materials\n{course_context}"
    if instructor_notes:
        system += (
            f"\n\n## Instructor Observations This Week\n"
            f"Sarah has flagged these issues she is currently noticing across the class. "
            f"Weave this awareness naturally into your responses where relevant — "
            f"do not announce it, just let it inform how you help:\n{instructor_notes}"
        )
    if student_name:
        system += f"\n\nYou are speaking with {student_name}."

    messages = history + [{"role": "user", "content": user_message}]
    return _complete(system=system, messages=messages, max_tokens=1024)


def refine_note(teacher_message: str, pedagogy_context: str = "") -> str:
    """
    Turn an instructor's plain-language description of a student issue into a
    concrete instruction for Nova to follow with students. Internally weighs
    whether this is something to actively correct, or something to model
    consistently through Nova's own language — but the output is a plain
    description of the behavior itself, not a labeled classification, since
    this text is shown directly to the instructor for approval.
    """
    prompt = (
        f"An instructor described this issue with their students:\n\n\"{teacher_message}\"\n\n"
        f"Describe, in 2-3 plain sentences, what you will actually do differently when talking "
        f"with students as a result. Decide for yourself whether this calls for actively noticing "
        f"and correcting a mistake in the moment, or for consistently modeling the correct language "
        f"or form yourself so students pick it up through exposure — but do not name or label that "
        f"choice, just describe the concrete behavior naturally, as if explaining your plan to the "
        f"instructor in conversation. Do not use headers, labels, or bullet points."
    )
    if pedagogy_context:
        prompt += (
            f"\n\nGround your plan in this pedagogy material the instructor has provided, "
            f"if it's relevant:\n{pedagogy_context}"
        )
    return _complete(
        system="You describe, in plain conversational language, what you (an AI course assistant) will do differently based on an instructor's note. No headers or labels — just the plan, as you'd say it to the instructor.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    ).strip()


def is_confirmation(message: str) -> bool:
    """
    Return True if a message is a plain confirmation/agreement (e.g. "yes",
    "looks good", "that works"), False if it's a request for a change,
    a question, or anything else.
    """
    prompt = (
        f"Someone was shown a proposed plan and asked if it's correct. They replied:\n\n"
        f"\"{message}\"\n\n"
        f"Does this reply confirm the plan as-is? Reply with ONLY 'yes' or 'no'. "
        f"If they are asking for any change, correction, addition, or are asking a question "
        f"instead of confirming, reply 'no'."
    )
    result = _complete(
        system="You classify whether a reply is a plain confirmation or not. Reply with only 'yes' or 'no'.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
    )
    return result.strip().lower().startswith("yes")


def detect_struggle(user_message: str, material_title: str) -> str | None:
    """
    Given a student's message during a study session, return a short concept
    label if the student appears to be struggling, or None if they aren't.
    """
    prompt = (
        f"A student is studying '{material_title}' and sent this message:\n\n"
        f"\"{user_message}\"\n\n"
        f"If this message shows the student is confused about or struggling with a specific concept, "
        f"return ONLY a short concept label (3-6 words, e.g. 'Bourdieu cultural capital theory'). "
        f"If the message is not a sign of struggle (e.g. it's a greeting, a simple factual question "
        f"they already understand, or off-topic), return ONLY the word 'none'."
    )
    result = _complete(
        system="You identify student struggle concepts. Reply with a short label or the word 'none'.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20,
    ).strip()
    return None if result.lower() == "none" else result


def generate_quiz(topic: str, course_context: str, n: int = 3,
                  struggle_topics: list[str] | None = None) -> str:
    if struggle_topics:
        focus = (
            f"Focus your questions on these specific concepts the student struggled with: "
            f"{', '.join(struggle_topics)}. "
        )
    else:
        focus = ""

    prompt = (
        f"Generate {n} multiple-choice quiz questions. {focus}"
        f"Base all questions strictly on the following course materials. "
        f"Format each question as:\nQ: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: ...\n\n"
        f"Materials:\n{course_context}"
    )
    return _complete(
        system="You are a quiz generator for a university course. Be precise and fair.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
