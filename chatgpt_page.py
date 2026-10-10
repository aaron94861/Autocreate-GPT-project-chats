"""
Everything that touches the ChatGPT web page lives here.

ChatGPT changes its page from time to time. If the script stops with
"Couldn't find ..." the fix is almost always one of the SELECTORS below:
open ChatGPT in Chrome, right-click the element > Inspect, and update the selector.
"""

import re
import time
from html.parser import HTMLParser

SELECTORS = {
    # the message box (ChatGPT uses a contenteditable div with this id)
    "composer": "#prompt-textarea, div[contenteditable='true']",
    "send": "[data-testid='send-button'], button[aria-label='Send prompt']",
    "stop": "[data-testid='stop-button'], button[aria-label='Stop streaming']",
    "assistant": "[data-message-author-role='assistant']",
    # the formatted body inside an assistant message
    "assistant_body": ".markdown",
    "login": "[data-testid='login-button'], a[href*='auth/login'], button:has-text('Log in')",
}

# Text that means "stop now, don't keep sending" (checked case-insensitively).
STOP_PHRASES = [
    "you've reached", "you have reached", "usage limit", "usage cap", "limit for gpt",
    "too many requests", "something went wrong", "unusual activity", "verify you are human",
    "are you a robot", "network error", "there was an error generating",
]


class StopRun(Exception):
    """Something needs a human: a limit, an error, a login page, or a changed page layout."""


def find_stop_phrase(text):
    low = text.lower().replace("’", "'")
    for p in STOP_PHRASES:
        if p in low:
            return p
    return None


# ---------------------------------------------------------------------------
# Reply HTML -> Markdown, so saved replies keep headings/bold/bullets/tables
# (and GPT-to-Anki can read the "**Disease – Section**" titles).
# ---------------------------------------------------------------------------
class _MD(HTMLParser):
    BLOCK = {"p", "div", "section", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.lists = []       # stack of ["ul"/"ol", counter]
        self.row = None       # current table row cells
        self.cell = None
        self.rows = []
        self.skip = 0

    def _nl(self, n=1):
        text = "".join(self.out)
        have = len(text) - len(text.rstrip("\n"))
        if text.strip():
            self.out.append("\n" * max(0, n - have))

    def handle_starttag(self, tag, attrs):
        if tag in ("button", "svg", "style", "script"):
            self.skip += 1
        if self.skip:
            return
        if re.match(r"h[1-6]$", tag):
            self._nl(2)
            self.out.append("#" * int(tag[1]) + " ")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag in ("ul", "ol"):
            self._nl(1 if self.lists else 2)
            self.lists.append([tag, 0])
        elif tag == "li":
            self._nl(1)
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            indent = "  " * (len(self.lists) - 1)
            self.out.append(indent + ("%d. " % kind[1] if kind[0] == "ol" else "- "))
        elif tag == "br":
            self.out.append("\n")
        elif tag == "hr":
            self._nl(2)
            self.out.append("---")
            self._nl(2)
        elif tag == "table":
            self.rows = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in self.BLOCK:
            self._nl(1 if self.lists else 2)

    def handle_endtag(self, tag):
        if tag in ("button", "svg", "style", "script"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if re.match(r"h[1-6]$", tag):
            self._nl(2)
        elif tag in ("strong", "b"):
            self._close_inline("**")
        elif tag in ("em", "i"):
            self._close_inline("*")
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._nl(1 if self.lists else 2)
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            self._nl(2)
            for i, r in enumerate(self.rows):
                self.out.append("| " + " | ".join(r) + " |\n")
                if i == 0:
                    self.out.append("|" + " --- |" * len(r) + "\n")
            self._nl(2)
        elif tag in self.BLOCK:
            self._nl(1 if self.lists else 2)

    def _close_inline(self, mark):
        target = self.cell if self.cell is not None else self.out
        target.append(mark)

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        if not "".join(self.out).endswith(("\n", " ", "*", "#", "- ")) and not data.strip():
            self.out.append(" ")
            return
        self.out.append(re.sub(r"\s+", " ", data) if data.strip() else "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def result(self):
        text = "".join(self.out)
        text = re.sub(r"\*\*\s*\*\*", "", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html):
    p = _MD()
    p.feed(html)
    p.close()
    return p.result()


# ---------------------------------------------------------------------------
# Driving the page
# ---------------------------------------------------------------------------
class ChatGPTPage:
    def __init__(self, page, reply_timeout=240, stable_secs=2.0, log=print):
        self.page = page
        self.reply_timeout = reply_timeout
        self.stable_secs = stable_secs  # reply must stop changing for this long
        self.log = log

    # -- helpers ----------------------------------------------------------
    def _visible(self, key, timeout=0):
        loc = self.page.locator(SELECTORS[key]).first
        try:
            loc.wait_for(state="visible", timeout=timeout * 1000 if timeout else 1)
            return loc
        except Exception:
            return None

    def check_for_problems(self):
        """Raise StopRun if the page shows a limit/error message."""
        try:
            body = self.page.locator("body").inner_text(timeout=5000)
        except Exception:
            return
        # only look at the end of the page (latest messages, banners) to avoid
        # matching words inside medical answers
        phrase = find_stop_phrase(body[-1500:])
        if phrase:
            raise StopRun("ChatGPT shows a message containing %r. Stopping so you can check." % phrase)

    def last_reply_text_contains_problem(self):
        msgs = self.page.locator(SELECTORS["assistant"])
        if msgs.count() == 0:
            return None
        text = msgs.last.inner_text()
        return find_stop_phrase(text) if len(text) < 400 else None

    # -- navigation -------------------------------------------------------
    def open(self, url, wait_for_login=None):
        """Open a project or chat URL and wait until the message box is ready."""
        self.page.goto(url, wait_until="domcontentloaded")
        if self._visible("composer", timeout=25):
            return
        if wait_for_login and self._visible("login", timeout=1):
            wait_for_login()
            self.page.goto(url, wait_until="domcontentloaded")
            if self._visible("composer", timeout=25):
                return
        self.check_for_problems()
        raise StopRun("Couldn't find the ChatGPT message box on %s.\n"
                      "  Are you logged in, and is the project URL right? (selector: %s)"
                      % (url, SELECTORS["composer"]))

    # -- sending ------------------------------------------------------------
    def send(self, prompt):
        """Send one prompt and wait for the full reply. Returns the reply as Markdown."""
        before = self.page.locator(SELECTORS["assistant"]).count()
        box = self._visible("composer", timeout=20)
        if not box:
            raise StopRun("Couldn't find the message box (selector: %s)" % SELECTORS["composer"])
        box.click()
        self.page.keyboard.insert_text(prompt)
        time.sleep(0.5)
        send = self._visible("send", timeout=10)
        if send and send.is_enabled():
            send.click()
        else:
            self.page.keyboard.press("Enter")

        # wait for the reply to appear ...
        deadline = time.time() + self.reply_timeout
        while self.page.locator(SELECTORS["assistant"]).count() <= before:
            if time.time() > deadline:
                self.check_for_problems()
                raise StopRun("No reply appeared within %ds." % self.reply_timeout)
            time.sleep(0.5)
        # ... and to finish (stop button gone, text no longer changing)
        last_text, stable_since = None, time.time()
        while True:
            if time.time() > deadline:
                raise StopRun("The reply didn't finish within %ds." % self.reply_timeout)
            generating = self.page.locator(SELECTORS["stop"]).count() > 0
            text = self.page.locator(SELECTORS["assistant"]).last.inner_text()
            if text != last_text:
                last_text, stable_since = text, time.time()
            if not generating and text.strip() and time.time() - stable_since >= self.stable_secs:
                break
            time.sleep(0.5)

        problem = self.last_reply_text_contains_problem()
        if problem:
            raise StopRun("ChatGPT replied with an error/limit message (%r). Stopping." % problem)
        self.check_for_problems()
        return self.last_reply_markdown()

    def last_reply_markdown(self):
        msg = self.page.locator(SELECTORS["assistant"]).last
        body = msg.locator(SELECTORS["assistant_body"])
        html = body.first.inner_html() if body.count() else msg.inner_html()
        return html_to_markdown(html)

    def current_url(self):
        return self.page.url
