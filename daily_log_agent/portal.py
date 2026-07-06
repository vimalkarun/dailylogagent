import base64
import json
import logging
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

log = logging.getLogger("daily_log_agent.portal")

DASHBOARD_URL_RE = re.compile(r".*/(ParentPortal|StudentPortal|StaffPortal)/.*Dashboard")
ASSIGNMENT_PATH = "/ParentPortal/ParentAssignment"

# Column order matches the Syncfusion grid config on ParentAssignment.
CELL_INDEX = {
    "serial": 0,
    "title": 1,
    "assignment_date": 2,
    "due_date": 3,
    "subject": 4,
    "type": 5,
}


class LoginError(RuntimeError):
    pass


async def login(context: BrowserContext, base_url: str, user_id: str, password: str) -> Page:
    page = await context.new_page()
    await page.goto(base_url, wait_until="networkidle")

    if await page.locator("#txtUserID").count() == 0:
        await page.goto(urljoin(base_url, "/Logon/Index"), wait_until="networkidle")

    await page.fill("#txtUserID", user_id)
    await page.fill("#userPassword", password)
    if not await page.locator("#termsCheck").is_checked():
        await page.check("#termsCheck")

    await page.click("#btnLogin")

    try:
        await page.wait_for_url(DASHBOARD_URL_RE, timeout=25000)
        return page
    except PlaywrightTimeoutError:
        pass

    if await page.locator("#otpModal").is_visible():
        raise LoginError(
            "Portal requested an OTP/MFA code. This account has login-OTP enabled, "
            "which this unattended agent cannot complete. Disable 'Login OTP Required' "
            "for this account in the portal's Change Password screen, or this agent "
            "cannot log in unattended."
        )

    # Password-expiring-soon interstitial - dismiss it and continue.
    if await page.locator("#btnContinue").is_visible():
        await page.click("#btnContinue")
        await page.wait_for_url(DASHBOARD_URL_RE, timeout=25000)
        return page

    error_text = ""
    if await page.locator("#ErrorMessage").count():
        error_text = (await page.locator("#ErrorMessage").inner_text()).strip()
    raise LoginError(f"Login failed: {error_text or 'unrecognized page state after submitting credentials'}")


def _parse_grid_date(text: str) -> Optional[date]:
    text = text.strip()
    if not text:
        return None
    return datetime.strptime(text, "%d/%m/%Y").date()


async def get_todays_entries(page: Page, target_date: date) -> list[dict]:
    assignment_url = urljoin(page.url, ASSIGNMENT_PATH)
    await page.goto(assignment_url, wait_until="networkidle")
    await page.wait_for_selector("#Grid .e-gridcontent", timeout=20000)

    try:
        await page.wait_for_selector("#Grid .e-gridcontent .e-row", timeout=15000)
    except PlaywrightTimeoutError:
        return []

    rows = page.locator("#Grid .e-gridcontent .e-row")
    count = await rows.count()

    entries = []
    for i in range(count):
        row = rows.nth(i)
        cells = row.locator(".e-rowcell")
        assignment_date_text = await cells.nth(CELL_INDEX["assignment_date"]).inner_text()
        if _parse_grid_date(assignment_date_text) != target_date:
            continue
        entries.append(
            {
                "row_index": i,
                "title": (await cells.nth(CELL_INDEX["title"]).inner_text()).strip(),
                "assignment_date": assignment_date_text.strip(),
                "due_date": (await cells.nth(CELL_INDEX["due_date"]).inner_text()).strip(),
                "subject": (await cells.nth(CELL_INDEX["subject"]).inner_text()).strip(),
                "type_name": (await cells.nth(CELL_INDEX["type"]).inner_text()).strip(),
            }
        )
    return entries


async def capture_pdf_bytes(context: BrowserContext, page: Page, row_index: int) -> Optional[bytes]:
    rows = page.locator("#Grid .e-gridcontent .e-row")
    row = rows.nth(row_index)
    eye_icon = row.locator(".fa-eye")

    # modalOpen() (bound to the eye icon via onclick) was confirmed by dumping
    # its actual source to only populate the in-page ".assignment-details"
    # modal - it never calls window.open(). Any popup that opens around this
    # click is unrelated noise (observed: permanently empty, url stuck at
    # ':', zero console errors) and must not be treated as the PDF source.
    await eye_icon.click()
    await page.wait_for_selector(".assignment-details", state="visible", timeout=10000)

    thumb = page.locator("#caresoulAssignment img").first
    if await thumb.count() == 0:
        await page.click("#assignmentDetailsClose")
        return None

    # imageClick() (bound to the thumbnail) was also confirmed by dumping its
    # source to never call window.open() - it calls getBase64AttachmentsAssignment,
    # an AJAX call that fetches the PDF as base64. The stray empty popup seen
    # around every click on this page (url stuck at ':') is unrelated to both
    # handlers, so intercept the actual API response instead of chasing it.
    try:
        async with page.expect_response(
            lambda r: "base64" in r.url.lower(), timeout=10000
        ) as response_info:
            await thumb.click()
        api_response = await response_info.value
        body_text = await api_response.text()
        log.info(
            "capture_pdf_bytes: base64 API response for row %d - url=%r status=%r body preview=%r",
            row_index,
            api_response.url,
            api_response.status,
            body_text[:500],
        )
    except PlaywrightTimeoutError:
        body_text = None
        log.warning(
            "capture_pdf_bytes: no 'base64' API response observed after clicking the thumbnail for row %d",
            row_index,
        )

    await page.click("#assignmentDetailsClose")

    if not body_text:
        return None

    try:
        data = json.loads(body_text)
    except ValueError:
        log.warning("capture_pdf_bytes: API response for row %d was not JSON", row_index)
        return None

    # The field holding the base64 payload isn't confirmed yet - try the
    # common candidates seen elsewhere in this portal's API responses.
    for field in ("result", "Result", "data", "Data", "fileContent", "base64"):
        value = data.get(field) if isinstance(data, dict) else None
        if isinstance(value, str) and len(value) > 100:
            try:
                return base64.b64decode(value)
            except Exception:
                continue

    log.warning(
        "capture_pdf_bytes: could not find a base64 field in API response for row %d - keys: %s",
        row_index,
        list(data.keys()) if isinstance(data, dict) else type(data),
    )
    return None
