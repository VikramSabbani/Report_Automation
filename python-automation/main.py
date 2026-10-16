import os
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

REPORTS_URL = "https://website-assesment-1.onrender.com/reports"
USERNAME = os.getenv("REPORT_USERNAME", "admin")
PASSWORD = os.getenv("REPORT_PASSWORD", "1234")

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"

HEADLESS = True
TIMEOUT_MS = 20_000


def log(message):
    print(message, flush=True)


def find_visible(page, selectors, timeout=1500):
    """Return the first visible element matching the supplied selectors."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


def get_report_date():
    """Read the date passed by Node.js, or prompt when run manually."""
    if len(sys.argv) > 1:
        report_date = sys.argv[1].strip()
    else:
        report_date = input(
            "Enter report date (YYYY-MM-DD), "
            "or press Enter for today: "
        ).strip()

        if not report_date:
            report_date = date.today().isoformat()

    try:
        datetime.strptime(report_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            "Invalid date. Use the YYYY-MM-DD format."
        ) from exc

    return report_date





def login_and_open_reports(page):
    """Log in if needed, navigate from dashboard to Reports, and verify."""

    log("[1/4] Opening website...")

    response = page.goto(
        REPORTS_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    if response and response.status >= 500:
        raise RuntimeError(
            f"Source website returned HTTP {response.status}"
        )

    username_selector = 'input[name="username"]'
    password_selector = 'input[name="password"]'

    date_selector = (
        'input[type="date"], '
        'input[name*="date" i], '
        'input[id*="date" i]'
    )

    # If redirected to login, submit the credentials.
    username = page.locator(username_selector).first
    password = page.locator(password_selector).first

    if username.is_visible() and password.is_visible():
        log("Login form detected.")

        username.fill(os.getenv("REPORT_USERNAME", "admin"))
        password.fill(os.getenv("REPORT_PASSWORD", "1234"))

        page.locator('button[type="submit"]').first.click(timeout=5000)

        # Wait until login finishes and the dashboard appears.
        try:
            page.get_by_text(
                "Welcome to X Company", exact=False
            ).wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                f"Login did not reach the dashboard. "
                f"URL={page.url}; title={page.title()}; "
                f"text={page.locator('body').inner_text()[:1000]}"
            ) from exc

    log(f"Current page after login: {page.url}")

    # If the report date field is not already visible, open Reports.
    date_field = page.locator(date_selector).first

    if not date_field.is_visible():
        reports_link = page.locator(
            'a[href*="reports" i], button:has-text("Reports")'
        ).first

        if reports_link.count() == 0:
            reports_link = page.get_by_text(
                "Reports", exact=True
            ).first

        if reports_link.count() == 0:
            raise RuntimeError(
                f"Could not find the Reports navigation item. "
                f"URL={page.url}; title={page.title()}"
            )

        log("Opening Reports section...")
        reports_link.click(timeout=5000)

    # Verify the actual report interface.
    try:
        date_field.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Reports page did not appear. "
            f"URL={page.url}; title={page.title()}; "
            f"text={page.locator('body').inner_text()[:1500]}"
        ) from exc

    download_selector = (
        'button:has-text("Download"), '
        'a:has-text("Download"), '
        'button:has-text("Export")'
    )

    try:
        page.locator(download_selector).first.wait_for(
            state="visible", timeout=5000
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Date field appeared, but the download button is missing. "
            f"URL={page.url}; title={page.title()}"
        ) from exc

    log(f"Reports page verified: {page.url}")

def select_report_date(page, report_date):
    """Wait for the report date field and fill it."""
    date_selectors = [
        'input[type="date"]',
        'input[name*="date" i]',
        'input[id*="date" i]',
    ]

    date_field = None

    # Allow the reports interface time to render.
    for attempt in range(12):
        date_field = find_visible(
            page,
            date_selectors,
            timeout=2000,
        )

        if date_field:
            break

        time.sleep(2)

    if not date_field:
        # Print the actual page details to diagnose the selector.
        try:
            log(f"DATE DEBUG URL: {page.url}")
            log(f"DATE DEBUG TITLE: {page.title()}")
            log(
                "DATE DEBUG TEXT:\n"
                + page.locator("body").inner_text(timeout=5000)[:2000]
            )

            controls = page.locator(
                "input, button, select"
            ).evaluate_all("""
                elements => elements.map(el => ({
                    tag: el.tagName,
                    type: el.getAttribute('type'),
                    name: el.getAttribute('name'),
                    placeholder: el.getAttribute('placeholder'),
                    text: (el.innerText || '').slice(0, 80),
                    visible: !!(el.offsetWidth || el.offsetHeight ||
                                el.getClientRects().length)
                }))
            """)

            log(f"DATE DEBUG CONTROLS: {json.dumps(controls)}")

        except Exception as debug_error:
            log(f"Date diagnostics failed: {debug_error}")

        raise RuntimeError(
            "Could not find the report date field after waiting."
        )

    date_field.fill(report_date)
    date_field.dispatch_event("input")
    date_field.dispatch_event("change")

    log(f"Selected report date: {report_date}")



def download_csv(page, report_date):
    """Download the source CSV and save it with a timestamped filename."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    select_report_date(page, report_date)

    download_button = find_visible(
        page,
        [
            'button:has-text("Download Report")',
            'button:has-text("Download")',
            'a:has-text("Download Report")',
        ],
        timeout=5000,
    )

    if not download_button:
        raise RuntimeError("Could not find the Download Report button.")

    log("[3/4] Downloading CSV...")

    with page.expect_download(timeout=60_000) as download_info:
        download_button.click()

    download = download_info.value

    original_name = Path(
        download.suggested_filename or "report.csv"
    ).name

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = (
        f"{Path(original_name).stem}_"
        f"{report_date}_{timestamp}.csv"
    )

    destination = DOWNLOAD_DIR / filename
    download.save_as(destination)

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("The downloaded CSV is missing or empty.")

    log(f"Downloaded: {destination.name}")
    return destination


def process_csv(source_path):
    """Add the Actual sale and Transaction Type columns."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        dataframe = pd.read_csv(source_path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        dataframe = pd.read_csv(source_path, encoding="latin-1")

    dataframe.columns = [
        str(column).strip() for column in dataframe.columns
    ]

    sales_column = next(
        (
            column for column in dataframe.columns
            if column.lower() == "sales"
        ),
        None,
    )

    if sales_column is None:
        raise ValueError(
            "The CSV does not contain a Sales column."
        )

    sales = pd.to_numeric(
        dataframe[sales_column],
        errors="coerce",
    )

    if sales.isna().any():
        raise ValueError(
            "The Sales column contains missing or non-numeric values."
        )

    # Apply the stated 5% fee: 1000 becomes 1050.
    dataframe["Actual sale"] = (sales * 1.05).round(2)
    dataframe["Transaction Type"] = "DEP"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = (
        f"{source_path.stem}_processed_{timestamp}.csv"
    )
    output_path = OUTPUT_DIR / output_name

    dataframe.to_csv(output_path, index=False)

    # Read the saved file back to validate the output.
    saved = pd.read_csv(output_path)

    required_columns = ["Actual sale", "Transaction Type"]
    for column in required_columns:
        if column not in saved.columns:
            raise RuntimeError(
                f"Output validation failed: missing {column}."
            )

    if len(saved) != len(dataframe):
        raise RuntimeError(
            "Output validation failed: row count changed."
        )

    if not saved["Transaction Type"].eq("DEP").all():
        raise RuntimeError(
            "Output validation failed: incorrect transaction type."
        )

    log("[4/4] CSV processing and validation complete.")
    log(f"Processed output: {output_path.name}")
    log(f"Rows processed: {len(saved)}")

    return {
        "filename": output_path.name,
        "rowsProcessed": len(saved),
    }



def main():
    try:
        report_date = get_report_date()

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # The context manager handles Playwright cleanup automatically.
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=HEADLESS)

            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(TIMEOUT_MS)

                login_and_open_reports(page)

                source_path = download_csv(page, report_date)
                result = process_csv(source_path)

                log("SUCCESS: automation completed.")

                print(
                    "RESULT_JSON:" + json.dumps({
                        "success": True,
                        "reportDate": report_date,
                        **result,
                    }),
                    flush=True,
                )

            finally:
                # Close resources while Playwright is still running.
                browser.close()

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
