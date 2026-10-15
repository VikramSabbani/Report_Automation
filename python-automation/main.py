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
    """Open the site, log in if required, and open the reports page."""
    log("[1/4] Opening website...")

    page.goto(
        REPORTS_URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    # The site may take some time to wake up on its hosting platform.
    username_field = None
    password_field = None

    for attempt in range(24):
        username_field = find_visible(
            page,
            [
                'input[name="username"]',
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="username" i]',
                'input[placeholder*="email" i]',
                'input[type="text"]',
            ],
        )

        password_field = find_visible(
            page,
            [
                'input[name="password"]',
                'input[type="password"]',
            ],
        )

        if username_field and password_field:
            break

        if "/reports" in page.url.lower():
            break

        if attempt < 23:
            time.sleep(5)
            try:
                page.reload(
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            except PlaywrightTimeoutError:
                pass

    if username_field and password_field:
        log("[2/4] Login page loaded.")

        username_field.fill(USERNAME)
        password_field.fill(PASSWORD)

        login_button = find_visible(
            page,
            [
                'button:has-text("Login")',
                'button:has-text("Log in")',
                'input[type="submit"]',
                'button[type="submit"]',
            ],
        )

        if not login_button:
            raise RuntimeError("Could not find the login button.")

        login_button.click()
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=30_000,
        )

    # Navigate directly to the required page after authentication.
    if "/reports" not in page.url.lower():
        page.goto(
            REPORTS_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

    date_field = find_visible(
        page,
        [
            'input[type="date"]',
            'input[name*="date" i]',
            'input[id*="date" i]',
        ],
        timeout=5000,
    )

    download_button = find_visible(
        page,
        [
            'button:has-text("Download Report")',
            'button:has-text("Download")',
            'a:has-text("Download Report")',
        ],
        timeout=5000,
    )

    if not date_field or not download_button:
      try:
          page_title = page.title()
      except Exception:
          page_title = "(could not read page title)"

      try:
          page_text = page.locator("body").inner_text(timeout=5000)
          page_text = page_text[:1500]
      except Exception:
          page_text = "(could not read page text)"

      log(f"DEBUG URL: {page.url}")
      log(f"DEBUG TITLE: {page_title}")
      log(f"DEBUG PAGE TEXT:\n{page_text}")
      log(f"DEBUG DATE FIELD FOUND: {date_field is not None}")
      log(f"DEBUG DOWNLOAD BUTTON FOUND: {download_button is not None}")

      raise RuntimeError(
          "Could not verify the reports page. "
          "See DEBUG output above for the actual page content."
      )

    log(f"Reports page verified: {page.url}")


def select_report_date(page, report_date):
    """Fill the report date field."""
    date_field = find_visible(
        page,
        [
            'input[type="date"]',
            'input[name*="date" i]',
            'input[id*="date" i]',
        ],
        timeout=5000,
    )

    if not date_field:
        raise RuntimeError("Could not find the report date field.")

    date_field.fill(report_date)
    date_field.dispatch_event("change")
    date_field.dispatch_event("input")

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
