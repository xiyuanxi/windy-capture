"""Block ad/analytics/tracking requests to speed up page load and save bandwidth.

We apply this at the BrowserContext level so all pages created from the
context inherit the routing rules.
"""

import logging
import re

from playwright.async_api import BrowserContext

logger = logging.getLogger("windy-capture.routing")

# Block requests whose URL matches any of these substrings.
# Conservative list — only well-known ad/analytics/tracking hosts.
# Map tiles, weather data, windy.com itself all pass through untouched.
_BLOCKED_RE = re.compile(
    r"""(
        google-analytics\.com
      | googletagmanager\.com
      | googlesyndication\.com
      | doubleclick\.net
      | adservice\.google\.
      | facebook\.net
      | facebook\.com/tr
      | connect\.facebook
      | twitter\.com/i/
      | platform\.twitter
      | criteo\.
      | hotjar\.
      | sentry\.io
      | bugsnag\.
      | mixpanel\.
      | segment\.
      | amplitude\.
      | clarity\.ms
      | onesignal\.
      | cookiebot\.
      | taboola\.
      | outbrain\.
      | scorecardresearch\.
      | quantserve\.
      | adnxs\.
      | pubmatic\.
      | rubiconproject\.
      | /gtag/js
      | /ga\.js
      | /gtm\.js
    )""",
    re.VERBOSE | re.IGNORECASE,
)


async def install_request_blocker(context: BrowserContext) -> None:
    """Install a catch-all route handler that aborts ad/analytics requests."""

    async def handler(route, request):
        if _BLOCKED_RE.search(request.url):
            await route.abort()
        else:
            await route.continue_()

    await context.route("**/*", handler)
    logger.info("Request blocker installed")
