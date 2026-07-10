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
CIRCULAR_PATH = "/ParentPortal/ParentCircular"

# Column order matches the Syncfusion grid config on ParentAssignment.
CELL_INDEX = {
    "serial": 0,
    "title": 1,
    "assignment_date": 2,
    "due_date": 3,
    "subject": 4,
    "type": 5,
}

# Column order matches the Syncfusion grid config on ParentCircular. The first
# column (ContentID) is hidden but still renders a cell, same as ParentAssignment.
CIRCULAR_CELL_INDEX = {
    "title": 1,
    "circular_date": 2,
    "due_date": 3,
    "type": 4,
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


def _parse_circular_date(text: str) -> Optional[date]:
    # ParentCircular's grid renders CDate/DueDate with a customFormat of
    # "dd/MM/yyyy hh:mm a" (e.g. "07/07/2026 04:35 AM"), unlike the plain
    # "dd/MM/yyyy" used on ParentAssignment.
    text = text.strip()
    if not text:
        return None
    return datetime.strptime(text, "%d/%m/%Y %I:%M %p").date()


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


async def get_todays_circulars(page: Page, target_date: date) -> list[dict]:
    circular_url = urljoin(page.url, CIRCULAR_PATH)
    await page.goto(circular_url, wait_until="networkidle")
    await page.wait_for_selector("#gridCircular .e-gridcontent", timeout=20000)

    # The grid's data load can be slow (observed ~15s+ in practice, sometimes
    # showing "No records to display" before the real rows arrive) - Playwright
    # keeps polling for ".e-row" to attach for the whole timeout window, so a
    # generously long timeout here is what makes this patient rather than any
    # extra retry loop.
    try:
        await page.wait_for_selector("#gridCircular .e-gridcontent .e-row", timeout=60000)
    except PlaywrightTimeoutError:
        return []

    rows = page.locator("#gridCircular .e-gridcontent .e-row")
    count = await rows.count()
    log.info("Circular grid has %d total row(s)", count)

    circulars = []
    seen_dates = []
    for i in range(count):
        row = rows.nth(i)
        cells = row.locator(".e-rowcell")
        circular_date_text = await cells.nth(CIRCULAR_CELL_INDEX["circular_date"]).inner_text()
        seen_dates.append(circular_date_text.strip())
        if _parse_circular_date(circular_date_text) != target_date:
            continue
        circulars.append(
            {
                "row_index": i,
                "title": (await cells.nth(CIRCULAR_CELL_INDEX["title"]).inner_text()).strip(),
                "circular_date": circular_date_text.strip(),
                "due_date": (await cells.nth(CIRCULAR_CELL_INDEX["due_date"]).inner_text()).strip(),
                "type_name": (await cells.nth(CIRCULAR_CELL_INDEX["type"]).inner_text()).strip(),
            }
        )
    if count and not circulars:
        log.info("No circulars matched %s - grid's Circular Date values were: %s", target_date, seen_dates[:20])
    return circulars


async def capture_circular_details(context: BrowserContext, page: Page, row_index: int) -> dict:
    rows = page.locator("#gridCircular .e-gridcontent .e-row")
    row = rows.nth(row_index)
    eye_icon = row.locator(".timetable-blk3")

    # viewClick() (bound to the eye icon) mirrors modalOpen() on the Assignment
    # page: it populates the in-page ".timetable-details" panel rather than
    # opening a real popup.
    await eye_icon.click()
    await page.wait_for_selector(".timetable-details", state="visible", timeout=30000)

    # The panel becomes visible well before its content does - #circularDescription
    # and #caresoul are filled in by a separate async call afterwards (confirmed
    # live: reading them right after visibility gave 0 chars / 0 thumbnails for a
    # circular that does have both). The user's observed ~15s render time is this
    # content-fill, not the panel's own visibility, so wait for actual content.
    try:
        await page.wait_for_function(
            """() => {
                const desc = document.querySelector('#circularDescription');
                const imgs = document.querySelectorAll('#caresoul img');
                return (desc && desc.innerText.trim().length > 0) || imgs.length > 0;
            }""",
            timeout=20000,
        )
    except PlaywrightTimeoutError:
        log.warning(
            "capture_circular_details: description/attachment never populated for row %d", row_index
        )

    description = (await page.locator("#circularDescription").inner_text()).strip()

    pdf_bytes = None
    pdf_url = None
    thumb = page.locator("#caresoul img").first
    if await thumb.count() > 0:
        # Not every circular has an attachment - by analogy with imageClick()
        # on the Assignment page, assume the thumbnail click triggers an AJAX
        # call whose response URL contains "base64" and whose JSON body holds
        # the real signed S3 URL in "classDetails". If no such response shows
        # up, treat it the same as "no attachment" rather than failing.
        try:
            async with page.expect_response(
                lambda r: "base64" in r.url.lower(), timeout=15000
            ) as response_info:
                await thumb.click()
            api_response = await response_info.value
            body_text = await api_response.text()
        except PlaywrightTimeoutError:
            body_text = None
            log.warning("capture_circular_details: no attachment API response observed for row %d", row_index)

        if body_text:
            try:
                data = json.loads(body_text)
            except ValueError:
                data = None
                log.warning("capture_circular_details: attachment API response for row %d was not JSON", row_index)

            pdf_url = data.get("classDetails") if isinstance(data, dict) else None
            if isinstance(pdf_url, str) and pdf_url.startswith(("http://", "https://")):
                response = await context.request.get(pdf_url)
                if response.ok:
                    pdf_bytes = await response.body()
                else:
                    pdf_url = None
                    log.warning(
                        "capture_circular_details: fetching PDF URL failed for row %d: status=%d",
                        row_index,
                        response.status,
                    )
            else:
                pdf_url = None
                if data is not None:
                    log.warning(
                        "capture_circular_details: classDetails was not a usable URL for row %d - keys: %s",
                        row_index,
                        list(data.keys()) if isinstance(data, dict) else type(data),
                    )

    await page.click("#timeTableDetailsClose")
    return {"description": description, "pdf_bytes": pdf_bytes, "pdf_url": pdf_url}


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

    # imageClick() (bound to the thumbnail) also never calls window.open() -
    # it calls getBase64AttachmentsAssignment, an AJAX call whose response
    # (despite the endpoint being named "...Base64") holds the real signed
    # S3 URL directly in its "classDetails" field, not base64-encoded
    # content. Intercept that response rather than looking for a popup.
    try:
        async with page.expect_response(
            lambda r: "base64" in r.url.lower(), timeout=10000
        ) as response_info:
            await thumb.click()
        api_response = await response_info.value
        body_text = await api_response.text()
    except PlaywrightTimeoutError:
        body_text = None
        log.warning("capture_pdf_bytes: no attachment API response observed for row %d", row_index)

    await page.click("#assignmentDetailsClose")

    if not body_text:
        return None

    try:
        data = json.loads(body_text)
    except ValueError:
        log.warning("capture_pdf_bytes: attachment API response for row %d was not JSON", row_index)
        return None

    pdf_url = data.get("classDetails") if isinstance(data, dict) else None
    if not isinstance(pdf_url, str) or not pdf_url.startswith(("http://", "https://")):
        log.warning(
            "capture_pdf_bytes: classDetails was not a usable URL for row %d - keys: %s",
            row_index,
            list(data.keys()) if isinstance(data, dict) else type(data),
        )
        return None

    response = await context.request.get(pdf_url)
    if not response.ok:
        log.warning(
            "capture_pdf_bytes: fetching PDF URL failed for row %d: status=%d", row_index, response.status
        )
        return None
    return await response.body()
