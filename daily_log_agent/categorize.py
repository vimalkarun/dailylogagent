PROMPT_TEMPLATE = """You are preparing a Telegram-ready summary of a school Daily Log for a parent.

Entry metadata:
- Title: {title}
- Type: {type_name}
- Assignment date: {assignment_date}
- Due date: {due_date}

Full text extracted from the attached Daily Log PDF (usually a table of
Subject / Topics Covered / Assignments Given / Assignments Collected / Remarks):
---
{pdf_text}
---

Produce a summary with exactly this structure, using only Telegram HTML
formatting (<b>...</b> for bold - no markdown, no other HTML tags):

1. One line per subject covered that day:
<b>Subject Name</b>: brief summary of the topics covered.
Fold rows with no real subject (e.g. an event name like "LIT FEST") into the
nearest relevant subject's line, or give them their own line if they stand alone.

2. A blank line, then a section starting with this exact bold header:
<b>Homework:</b>
Then one line per subject that has homework or an assignment given, in the
form "- Subject: what was assigned, and the due date if stated." If no
homework was given in any subject, write a single line: "No homework
assigned today."

3. A blank line, then a section starting with this exact bold header:
<b>Exam/Test Intimation:</b>
Then one line per exam, test, or periodic assessment mentioned anywhere in
the log (subject, what it covers, and the date if stated). If none are
mentioned, write a single line: "No exam or test announced today."

Notes:
- A short alphanumeric code like "7 F" in the title refers to the class and
  section (e.g. Class 7, Section F), not a grade or mark.
- Do not invent information that isn't in the extracted text.
- If the extracted PDF text is empty, garbled, or too sparse to summarize
  confidently, say so plainly in place of the structure above instead of guessing.
"""

CIRCULAR_PROMPT_TEMPLATE = """You are preparing a Telegram-ready summary of a school Circular for a parent.

Circular metadata:
- Title: {title}
- Type: {type_name}
- Circular date: {circular_date}
- Due date: {due_date}

Circular message text (from the portal page itself, not a PDF):
---
{description}
---

Text extracted from the attached PDF, if any:
---
{pdf_text}
---

Produce a short, plain-language summary (2-5 sentences) of what the circular
is about, using only Telegram HTML formatting (<b>...</b> for bold - no
markdown, no other HTML tags).

- If the circular requires an action from the parent (e.g. sign and return a
  form, pay a fee, register for an event) or states a deadline, add one bold
  sentence: <b>Action required: ...</b> stating what to do and the due date.
  Omit this sentence entirely if nothing is required from the parent.
- Do not invent information that isn't in the text above.
- If both the circular message and the PDF text are empty or too sparse to
  summarize confidently, say so plainly instead of guessing.
"""


def _build_prompt(entry: dict, pdf_text: str) -> str:
    return PROMPT_TEMPLATE.format(
        title=entry["title"],
        type_name=entry["type_name"],
        assignment_date=entry["assignment_date"],
        due_date=entry["due_date"],
        pdf_text=pdf_text[:8000] or "(no text could be extracted from the PDF)",
    )


def _build_circular_prompt(entry: dict, description: str, pdf_text: str) -> str:
    return CIRCULAR_PROMPT_TEMPLATE.format(
        title=entry["title"],
        type_name=entry["type_name"],
        circular_date=entry["circular_date"],
        due_date=entry["due_date"],
        description=description[:4000] or "(no description text on the portal)",
        pdf_text=pdf_text[:8000] or "(no PDF attachment for this circular)",
    )


def _call_anthropic(client, model: str, prompt: str, max_tokens: int = 800) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_gemini(client, model: str, prompt: str) -> str:
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def categorize_with_anthropic(client, model: str, entry: dict, pdf_text: str) -> dict:
    return {"summary": _call_anthropic(client, model, _build_prompt(entry, pdf_text))}


def categorize_with_gemini(client, model: str, entry: dict, pdf_text: str) -> dict:
    return {"summary": _call_gemini(client, model, _build_prompt(entry, pdf_text))}


def summarize_circular_with_anthropic(client, model: str, entry: dict, description: str, pdf_text: str) -> dict:
    prompt = _build_circular_prompt(entry, description, pdf_text)
    return {"summary": _call_anthropic(client, model, prompt, max_tokens=400)}


def summarize_circular_with_gemini(client, model: str, entry: dict, description: str, pdf_text: str) -> dict:
    prompt = _build_circular_prompt(entry, description, pdf_text)
    return {"summary": _call_gemini(client, model, prompt)}
