"""
syllabus_prompter.py - create one ChatGPT chat per syllabus point inside a ChatGPT
Project, and ask the same set of questions in each chat.

For "17. Endocarditis" in the Cardiology project it opens a new chat and sends:
    Endocarditis – Definition
    Endocarditis – Aetiology and classification
    Endocarditis – Pathogenesis
    Endocarditis – Physical examination and signs and symptoms
    Endocarditis – Diagnosis
    Endocarditis – Management and treatment
waiting for each reply to finish before sending the next.

It drives your own Chrome (a separate profile in ./chrome-profile - you log in once).
Progress is saved after every prompt, so a stopped run carries on where it left off.

Examples:
    python syllabus_prompter.py --section cardiovascular --dry-run
    python syllabus_prompter.py --section cardiovascular --points 17
    python syllabus_prompter.py --section cardiovascular --points 13-20 --save-replies
"""

import argparse
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ===========================================================================
# YOUR SETTINGS
# ===========================================================================
# Paste each ChatGPT Project's address here (open the project in ChatGPT and copy
# the address bar, e.g. https://chatgpt.com/g/g-p-1234abcd-cardiology/project).
PROJECT_URLS = {
    "cardiovascular": "",
    "pulmonary": "",
    "rheumatic": "",
    "hematologic": "",
    "endocrine_metabolic": "",
    "gastrointestinal": "",
    "renal": "",
    "toxicology_allergy": "",
    "oncologic": "",
    "treatment_principles": "",
}
MAX_POINTS_PER_RUN = 5          # new chats per run - keep it modest
DELAY_BETWEEN_PROMPTS = (8, 20)  # seconds, random within this range
DELAY_BETWEEN_CHATS = (30, 60)
REPLY_TIMEOUT = 240             # seconds to wait for one reply
BROWSER_CHANNEL = "chrome"      # your installed Google Chrome ("msedge" for Edge)

SYLLABUS_DIR = os.path.join(HERE, "syllabus")
PROMPTS_FILE = os.path.join(HERE, "prompts.txt")
PROGRESS_FILE = os.path.join(HERE, "progress.json")
PROFILE_DIR = os.path.join(HERE, "chrome-profile")
REPLIES_DIR = os.path.join(HERE, "replies")


# ===========================================================================
# Syllabus, prompts, progress
# ===========================================================================
def parse_syllabus(text):
    """Lines like '17. Endocarditis' or '13. Diseases of the mitral valve: mitral stenosis => Mitral stenosis'.
    Returns [{"number": 13, "full": "...", "topic": "Mitral stenosis"}, ...]."""
    points = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)[.)]\s*(.+)$", line)
        if not m:
            if points:  # continuation of a long point
                points[-1]["full"] += " " + line
                if not points[-1]["short"]:
                    points[-1]["topic"] = points[-1]["full"]
            continue
        full, _, short = m.group(2).partition("=>")
        full, short = full.strip(), short.strip()
        points.append({"number": int(m.group(1)), "full": full, "topic": short or full, "short": bool(short)})
    for p in points:
        del p["short"]
    return points


def load_syllabus(section):
    path = section if os.path.isfile(section) else os.path.join(SYLLABUS_DIR, section + ".txt")
    if not os.path.isfile(path):
        names = sorted(f[:-4] for f in os.listdir(SYLLABUS_DIR) if f.endswith(".txt"))
        sys.exit("No syllabus file for %r. Choose one of: %s" % (section, ", ".join(names)))
    with open(path, encoding="utf-8") as f:
        return parse_syllabus(f.read())


def load_prompts(path=PROMPTS_FILE):
    with open(path, encoding="utf-8") as f:
        prompts = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    if not prompts:
        sys.exit("No prompts in %s" % path)
    return prompts


def build_prompt(template, point):
    return template.format(topic=point["topic"], full=point["full"], number=point["number"])


def select_points(points, spec):
    """spec like '13-20', '17,19', '13-15,30' or None for all."""
    if not spec:
        return points
    wanted = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            wanted.update(range(int(a), int(b) + 1))
        else:
            wanted.add(int(part))
    return [p for p in points if p["number"] in wanted]


class Progress:
    """progress.json: {section: {"17": {"done": 6, "total": 6, "chat_url": "..."}}}"""

    def __init__(self, path=PROGRESS_FILE):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def get(self, section, number):
        return self.data.get(section, {}).get(str(number), {"done": 0, "chat_url": None})

    def is_complete(self, section, number, total):
        return self.get(section, number)["done"] >= total

    def update(self, section, number, **fields):
        entry = self.data.setdefault(section, {}).setdefault(str(number), {"done": 0, "chat_url": None})
        entry.update(fields)
        self.save()

    def reset(self, section, numbers):
        for n in numbers:
            self.data.get(section, {}).pop(str(n), None)
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)


def reply_file(point, replies_dir=REPLIES_DIR):
    safe = re.sub(r'[<>:"/\\|?*]+', " ", point["topic"]).strip()
    return os.path.join(replies_dir, "%03d %s.md" % (point["number"], safe))


# ===========================================================================
# Running
# ===========================================================================
def pause(rng, label=None, sleep=time.sleep):
    secs = random.uniform(*rng)
    if label:
        print("  ... waiting %.0fs %s" % (secs, label))
    sleep(secs)


def run(section, points, prompts, project_url, page_factory, progress, max_points,
        save_replies=False, replies_dir=REPLIES_DIR, delays=(DELAY_BETWEEN_PROMPTS, DELAY_BETWEEN_CHATS),
        wait_for_login=None, sleep=time.sleep):
    """Returns the number of chats completed in this run."""
    from chatgpt_page import StopRun

    todo = [p for p in points if not progress.is_complete(section, p["number"], len(prompts))]
    if not todo:
        print("Everything selected is already done.")
        return 0
    todo = todo[:max_points]
    print("This run: %d chat(s): %s" % (len(todo), ", ".join("%d %s" % (p["number"], p["topic"]) for p in todo)))

    chat = page_factory()
    completed = 0
    try:
        for i, point in enumerate(todo):
            state = progress.get(section, point["number"])
            start = state["done"]
            print("\n[%d] %s" % (point["number"], point["topic"]))
            if start and state.get("chat_url"):
                print("  Resuming in the existing chat at question %d/%d" % (start + 1, len(prompts)))
                chat.open(state["chat_url"], wait_for_login)
            else:
                start = 0
                chat.open(project_url, wait_for_login)

            for k in range(start, len(prompts)):
                prompt = build_prompt(prompts[k], point)
                print("  > %s" % prompt.splitlines()[0][:90])
                reply = chat.send(prompt)
                url = chat.current_url()
                if k == 0 and "/c/" not in url:
                    print("  (warning: the chat address doesn't look like a chat yet: %s)" % url)
                progress.update(section, point["number"], done=k + 1, total=len(prompts),
                                chat_url=url, topic=point["topic"])
                print("    reply received (%d characters)" % len(reply))
                if save_replies:
                    os.makedirs(replies_dir, exist_ok=True)
                    with open(reply_file(point, replies_dir), "a" if k else "w", encoding="utf-8") as f:
                        f.write(reply.strip() + "\n\n")
                if k < len(prompts) - 1:
                    pause(delays[0], sleep=sleep)
            completed += 1
            print("  Done: %d/%d questions." % (len(prompts), len(prompts)))
            if i < len(todo) - 1:
                pause(delays[1], "before the next chat", sleep=sleep)
    except StopRun as e:
        print("\nSTOPPED: %s" % e)
        print("Progress is saved - run the same command again later to carry on.")
    return completed


def open_browser(playwright, headless=False):
    kwargs = dict(user_data_dir=PROFILE_DIR, headless=headless, no_viewport=True)
    exe = os.environ.get("PROMPTER_BROWSER_PATH")
    if exe:
        kwargs["executable_path"] = exe
    else:
        kwargs["channel"] = BROWSER_CHANNEL
    try:
        return playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as e:
        sys.exit("Couldn't start %s (%s).\n  Is Google Chrome installed? Or set BROWSER_CHANNEL = \"msedge\" "
                 "in the script to use Edge." % (BROWSER_CHANNEL, str(e).splitlines()[0]))


def ask_login():
    print("\nPlease log in to ChatGPT in the browser window that just opened.")
    input("When you can see your ChatGPT chats, come back here and press Enter... ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Create one ChatGPT chat per syllabus point and ask the prompts in it.")
    ap.add_argument("-s", "--section", required=True,
                    help="syllabus file name in syllabus/ (e.g. cardiovascular) or a path to a .txt file")
    ap.add_argument("-u", "--project-url", help="ChatGPT Project address (default: PROJECT_URLS in the script)")
    ap.add_argument("-p", "--points", help="which points, e.g. 17 or 13-20 or 13,15,30 (default: all)")
    ap.add_argument("-m", "--max-points", type=int, default=MAX_POINTS_PER_RUN,
                    help="most new chats in one run (default: %(default)s)")
    ap.add_argument("-n", "--dry-run", action="store_true", help="list the chats and prompts, open nothing")
    ap.add_argument("--save-replies", action="store_true",
                    help="also save each chat's replies to replies/<number topic>.md (for GPT-to-Anki)")
    ap.add_argument("--reset", metavar="POINTS", help="forget progress for these points, e.g. 17 or 13-20")
    ap.add_argument("--status", action="store_true", help="show which points are done")
    ap.add_argument("--prompts", default=PROMPTS_FILE, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    section = os.path.splitext(os.path.basename(args.section))[0]
    points = load_syllabus(args.section)
    prompts = load_prompts(args.prompts)
    progress = Progress()

    if args.reset:
        nums = [p["number"] for p in select_points(points, args.reset)]
        progress.reset(section, nums)
        print("Progress cleared for: %s" % ", ".join(map(str, nums)))
        return 0

    selected = select_points(points, args.points)
    if not selected:
        sys.exit("No syllabus points match %r." % args.points)

    if args.status:
        for p in selected:
            st = progress.get(section, p["number"])
            mark = "done" if st["done"] >= len(prompts) else ("%d/%d" % (st["done"], len(prompts)) if st["done"] else "-")
            print("%4d  %-6s %s" % (p["number"], mark, p["topic"]))
        return 0

    if args.dry_run:
        for p in selected:
            done = progress.is_complete(section, p["number"], len(prompts))
            print("\nChat for %d. %s%s" % (p["number"], p["topic"], "   (already done)" if done else ""))
            for t in prompts:
                print("   > " + build_prompt(t, p).replace("\n", " "))
        print("\n%d chat(s) x %d prompts. Without --dry-run, at most %d new chats per run."
              % (len(selected), len(prompts), args.max_points))
        return 0

    url = (args.project_url or PROJECT_URLS.get(section, "")).strip()
    if not url.startswith("http"):
        sys.exit("No ChatGPT Project address for %r.\n"
                 "  Open the project in ChatGPT, copy the address bar, and either pass it with --project-url\n"
                 "  or paste it into PROJECT_URLS at the top of syllabus_prompter.py." % section)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        sys.exit("Playwright isn't available to the Python running this script (%s).\n"
                 "  Python used: %s\n"
                 "  Install it for exactly this Python with:\n"
                 "    \"%s\" -m pip install playwright" % (e, sys.executable, sys.executable))
    from chatgpt_page import ChatGPTPage

    with sync_playwright() as pw:
        ctx = open_browser(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            done = run(section, selected, prompts, url, lambda: ChatGPTPage(page, REPLY_TIMEOUT), progress,
                       args.max_points, args.save_replies, wait_for_login=ask_login)
        except KeyboardInterrupt:
            print("\nStopped by you. Progress is saved.")
            done = 0
        finally:
            ctx.close()
    remaining = sum(1 for p in selected if not progress.is_complete(section, p["number"], len(prompts)))
    print("\nFinished %d chat(s) this run. %d left in this selection." % (done, remaining))
    return 0


if __name__ == "__main__":
    sys.exit(main())
