from anthropic import Anthropic

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


def categorize_entry(client: Anthropic, model: str, entry: dict, pdf_text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=entry["title"],
        type_name=entry["type_name"],
        assignment_date=entry["assignment_date"],
        due_date=entry["due_date"],
        pdf_text=pdf_text[:8000] or "(no text could be extracted from the PDF)",
    )
    response = client.messages.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"summary": response.content[0].text.strip()}
