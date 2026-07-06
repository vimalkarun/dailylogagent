import base64
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

    popup = None
    try:
        async with context.expect_page(timeout=4000) as popup_info:
            await eye_icon.click()
        popup = await popup_info.value
        log.info(
            "capture_pdf_bytes: %d page(s) open right after eye-icon click: %s",
            len(context.pages),
            [p.url for p in context.pages],
        )
    except PlaywrightTimeoutError:
        # The eye icon opened the in-page attachment-details modal instead of a
        # popup directly; the PDF popup only appears after clicking its thumbnail.
        await page.wait_for_selector(".assignment-details", state="visible", timeout=10000)
        thumb = page.locator("#caresoulAssignment img").first
        if await thumb.count() == 0:
            await page.click("#assignmentDetailsClose")
            return None
        async with context.expect_page(timeout=10000) as popup_info:
            await thumb.click()
        popup = await popup_info.value
        await page.click("#assignmentDetailsClose")

    # The popup opens as "about:blank" first (a common way to dodge popup
    # blockers) and only navigates to the real signed PDF URL once an async
    # request resolves, so wait for that navigation rather than any load event
    # - which a raw PDF response never fires anyway once it does arrive.
    # It also passes through a fleeting malformed state (observed as the
    # literal string ":") while transitioning, so match on a real scheme
    # rather than merely "not blank", or that transient value gets caught
    # instead of the actual destination URL.
    try:
        await popup.wait_for_url(
            lambda url: url.startswith(("http://", "https://", "blob:")), timeout=8000
        )
    except PlaywrightTimeoutError:
        pass
    pdf_url = popup.url
    log.info("capture_pdf_bytes: popup URL for row %d is %r", row_index, pdf_url)

    if not pdf_url.startswith(("http://", "https://", "blob:")):
        # The popup's URL never resolved to a real scheme. Inspect its DOM
        # directly in case the PDF is rendered inline (e.g. via document.write
        # with an embedded viewer or base64 data) without the popup's own URL
        # ever changing, rather than assuming the URL-based approach applies.
        try:
            html = await popup.content()
        except Exception as exc:
            html = f"<could not read popup content: {exc!r}>"
        log.info("capture_pdf_bytes: popup content preview (row %d): %r", row_index, html[:3000])

        for selector, attr in (
            ("embed[src]", "src"),
            ("iframe[src]", "src"),
            ("object[data]", "data"),
            ("a[href*='.pdf']", "href"),
            ("a[href*='amazonaws']", "href"),
        ):
            loc = popup.locator(selector)
            if await loc.count() > 0:
                found = await loc.first.get_attribute(attr)
                log.info("capture_pdf_bytes: found %s -> %r", selector, found)

    if not pdf_url or pdf_url == "about:blank":
        await popup.close()
        return None

    if pdf_url.startswith("blob:"):
        # A blob: URL only exists inside this tab's JS memory (the portal likely
        # fetched the PDF as base64 and built an object URL for it) - it isn't a
        # network resource, so fetch it via the page's own JS context instead.
        base64_data = await popup.evaluate(
            """async (url) => {
                const buf = await (await fetch(url)).arrayBuffer();
                let binary = "";
                for (const byte of new Uint8Array(buf)) binary += String.fromCharCode(byte);
                return btoa(binary);
            }""",
            pdf_url,
        )
        await popup.close()
        return base64.b64decode(base64_data)

    await popup.close()
    if not pdf_url.startswith(("http://", "https://")):
        log.warning("capture_pdf_bytes: unhandled URL scheme for row %d: %r", row_index, pdf_url)
        return None

    response = await context.request.get(pdf_url)
    if not response.ok:
        return None
    return await response.body()
