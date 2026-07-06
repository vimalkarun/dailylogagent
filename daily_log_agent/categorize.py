import re

from anthropic import Anthropic

CATEGORIES = ["Homework", "Exam/Test", "Practice/Learning", "Project", "Circular/Notice", "Other"]

PROMPT_TEMPLATE = """You are helping a parent quickly understand a school daily log entry.

Entry metadata:
- Title: {title}
- Subject: {subject}
- Type: {type_name}
- Assignment date: {assignment_date}
- Due date: {due_date}

Full text extracted from the attached PDF:
---
{pdf_text}
---

Classify this entry into exactly one category from: {categories}.
Then write a one or two sentence, parent-friendly summary of what the child needs to do, including any dates that matter.

Respond in exactly this format, nothing else:
Category: <category>
Summary: <summary>
"""


def categorize_entry(client: Anthropic, model: str, entry: dict, pdf_text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=entry["title"],
        subject=entry["subject"],
        type_name=entry["type_name"],
        assignment_date=entry["assignment_date"],
        due_date=entry["due_date"],
        categories=", ".join(CATEGORIES),
        pdf_text=pdf_text[:8000] or "(no text could be extracted from the PDF)",
    )
    response = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    category_match = re.search(r"Category:\s*(.+)", raw)
    summary_match = re.search(r"Summary:\s*(.+)", raw, re.DOTALL)

    return {
        "category": category_match.group(1).strip() if category_match else "Other",
        "summary": summary_match.group(1).strip() if summary_match else raw,
    }
