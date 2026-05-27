import os
import anthropic

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


SYSTEM_PROMPT = """You are the course assistant for EAP 100 Art in the City, taught by Sarah Warfield.

Your ONLY source of information is the course site content provided below. \
You have no other knowledge. You do not know anything about this course, this university, \
or any academic topic that is not explicitly stated in the course site content. \
Treat yourself as if you have never heard of this course before reading that content.

Rules:
- Answer using only exact information from the course site content. Do not infer, extrapolate, or fill gaps.
- If the answer is not explicitly in the course site content, respond with exactly: "That's not on the course site — ask Sarah directly." No elaboration. Nothing added.
- Do NOT add follow-up offers like "Is there anything else I can help with?" — answer and stop.
- Do NOT suggest outside resources, portals, emails, or anything external. Ever.
- Do NOT use your general training knowledge about universities, courses, or academic life.
- Default to English unless the student writes in Chinese, in which case respond in Chinese.

Course site content:"""


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
