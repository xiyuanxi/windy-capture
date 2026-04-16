"""One-time script: open a visible browser, let you log in to Windy.com manually,
then save the browser state (cookies + localStorage) to a JSON file.

Usage:
    python scripts/save_auth.py [output_path]

Default output: auth/windy-state.json
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright

DEFAULT_OUTPUT = "auth/windy-state.json"


async def main() -> None:
    output = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    os.makedirs(os.path.dirname(output), exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.windy.com/")

        print()
        print("=" * 60)
        print("  Browser opened at windy.com")
        print("  Please log in manually.")
        print("  When done, come back here and press ENTER.")
        print("=" * 60)
        print()
        input("Press ENTER after login is complete...")

        await context.storage_state(path=output)
        print(f"Saved browser state to: {output}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
