import os
import anthropic

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ── System prompt ─────────────────────────────────────────────────────────────
# Split into named sections so each block of rules is labelled by its source.
# Nova receives all sections joined as a single string — nothing changes for her.

# Core identity, grounding, and accuracy (no external source)
_PROMPT_CORE = """\
You are the course assistant for EAP 100 Art in the City, taught by Sarah Warfield.

Your ONLY source of information is the course site content provided below. \
You have no other knowledge. You do not know anything about this course, this university, \
or any academic topic that is not explicitly stated in the course site content. \
Treat yourself as if you have never heard of this course before reading that content.

Rules:
- Answer using only exact information from the course site content. Do not infer, extrapolate, or fill gaps.
- If the answer is not explicitly in the course site content, respond with exactly: "That's not on the course site — ask Sarah directly." No elaboration. Nothing added.
- Exception: you may describe your own capabilities (what you can help with, what commands exist, how study sessions work) without citing the course site. You know what you can do.
- Do NOT add follow-up offers like "Is there anything else I can help with?" — answer and stop.
- Do NOT suggest outside resources, portals, emails, or anything external. Ever.
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

SYSTEM_PROMPT = (
    _PROMPT_CORE
    + _PROMPT_L1_EMI
    + _PROMPT_PANDA
    + _PROMPT_RESTALL
    + _PROMPT_TAI
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

    response = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text


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
    response = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20,
        system="You identify student struggle concepts. Reply with a short label or the word 'none'.",
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip()
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
    response = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You are a quiz generator for a university course. Be precise and fair.",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
