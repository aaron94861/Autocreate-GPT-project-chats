"""
prompt_helper.py - a small always-on-top window that walks you through the syllabus.

For each syllabus point it opens a new chat in your ChatGPT Project (in your normal
browser) and puts each question on the clipboard, one at a time:

    1. The helper copies "Endocarditis – Definition ..." to the clipboard.
    2. In ChatGPT: Ctrl+V, Enter.
    3. When the reply is done, click "Next" - the next question is copied.

Nothing is automated inside ChatGPT - you paste and send every message yourself,
so ChatGPT sees a normal user. Progress is saved, so you can stop and carry on later.

    python prompt_helper.py --section cardiovascular --project-url https://chatgpt.com/g/g-p-.../project
"""

import argparse
import os
import sys
import webbrowser

from syllabus_prompter import PROGRESS_FILE, PROJECT_URLS, Progress, build_prompt, load_prompts, \
    load_syllabus, select_points


class HelperState:
    """Which point/question is current. Progress uses the same progress.json as the old tool."""

    def __init__(self, section, points, prompts, progress):
        self.section, self.points, self.prompts, self.progress = section, points, prompts, progress
        self.total = len(prompts)
        self.pos = 0
        self._seek()

    def _seek(self):
        """Move to the first point that isn't finished."""
        while self.pos < len(self.points) and self.done_count() >= self.total:
            self.pos += 1

    # -- reading --------------------------------------------------------------
    @property
    def finished(self):
        return self.pos >= len(self.points)

    @property
    def point(self):
        return None if self.finished else self.points[self.pos]

    def done_count(self, point=None):
        point = point or self.points[self.pos]
        return self.progress.get(self.section, point["number"])["done"]

    @property
    def question_index(self):
        return min(self.done_count(), self.total - 1)

    @property
    def prompt(self):
        return None if self.finished else build_prompt(self.prompts[self.question_index], self.point)

    @property
    def starting_new_chat(self):
        return not self.finished and self.done_count() == 0

    def remaining_points(self):
        return sum(1 for p in self.points if self.done_count(p) < self.total)

    # -- changing -------------------------------------------------------------
    def _set_done(self, n):
        p = self.point
        self.progress.update(self.section, p["number"], done=n, total=self.total, topic=p["topic"])

    def next(self):
        """The current question has been sent; move on. Returns True if a new point (new chat) starts."""
        if self.finished:
            return False
        self._set_done(self.done_count() + 1)
        if self.done_count() >= self.total:
            self._seek()
            return not self.finished
        return False

    def back(self):
        """Go back one question (e.g. you clicked Next too early)."""
        if self.finished or self.done_count() == 0:
            if self.pos > 0:  # back into the previous point's last question
                self.pos -= 1
                self._set_done(self.total - 1)
            return
        self._set_done(self.done_count() - 1)

    def skip_point(self):
        if not self.finished:
            self._set_done(self.total)
            self.progress.update(self.section, self.point["number"], skipped=True)
            self._seek()


# ===========================================================================
# Window
# ===========================================================================
def run_window(state, project_url, section_title, auto_open=True, test_hook=None):
    import tkinter as tk
    from tkinter import font as tkfont

    root = tk.Tk()
    root.title("ChatGPT prompt helper - %s" % section_title)
    root.attributes("-topmost", True)
    root.geometry("600x330")
    root.minsize(460, 300)

    big = tkfont.Font(size=14, weight="bold")
    vars_ = {k: tk.StringVar() for k in ("header", "point", "question", "status")}
    on_top = tk.BooleanVar(value=True)
    open_chat = tk.BooleanVar(value=auto_open)

    tk.Label(root, textvariable=vars_["header"], fg="#666").pack(anchor="w", padx=12, pady=(10, 0))
    tk.Label(root, textvariable=vars_["point"], font=big, wraplength=570, justify="left").pack(anchor="w", padx=12)
    tk.Label(root, textvariable=vars_["question"]).pack(anchor="w", padx=12, pady=(4, 2))
    text = tk.Text(root, height=4, wrap="word", relief="solid", borderwidth=1)
    text.pack(fill="x", padx=12)
    tk.Label(root, textvariable=vars_["status"], fg="#0a7d20", wraplength=570, justify="left").pack(
        anchor="w", padx=12, pady=6)

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=12)
    options = tk.Frame(root)
    options.pack(fill="x", padx=12, pady=(8, 10))

    def copy(prompt):
        root.clipboard_clear()
        root.clipboard_append(prompt)
        root.update()  # keep the clipboard after the window loses focus

    def open_new_chat():
        if project_url:
            webbrowser.open(project_url)

    def refresh(new_chat=False):
        text.config(state="normal")
        text.delete("1.0", "end")
        if state.finished:
            vars_["header"].set(section_title)
            vars_["point"].set("All done for this selection!")
            vars_["question"].set("")
            vars_["status"].set("Every selected syllabus point has all its questions. You can close this window.")
            text.config(state="disabled")
            for b in (next_btn, copy_btn, skip_btn, chat_btn):
                b.config(state="disabled")
            return
        p = state.point
        vars_["header"].set("%s  -  %d point(s) left" % (section_title, state.remaining_points()))
        vars_["point"].set("%d. %s" % (p["number"], p["topic"]))
        vars_["question"].set("Question %d of %d" % (state.question_index + 1, state.total))
        text.insert("1.0", state.prompt)
        text.config(state="disabled")
        copy(state.prompt)
        if new_chat or state.starting_new_chat:
            if open_chat.get() and project_url:
                open_new_chat()
                vars_["status"].set("New chat opened in your project. Copied - click the message box, "
                                    "press Ctrl+V then Enter. Click Next when the reply is done.")
            else:
                vars_["status"].set("Start a NEW chat in your project for this point. Copied - "
                                    "Ctrl+V, Enter, then click Next when the reply is done.")
        else:
            vars_["status"].set("Copied - in the same chat press Ctrl+V then Enter. "
                                "Click Next when the reply is done.")

    def on_next():
        refresh(new_chat=state.next())

    def on_back():
        state.back()
        refresh()
        vars_["status"].set("Went back. Copied again - Ctrl+V, Enter.")

    def on_skip():
        state.skip_point()
        refresh(new_chat=True)

    def on_copy():
        copy(state.prompt)
        vars_["status"].set("Copied again.")

    tk.Button(buttons, text="< Back", command=on_back).pack(side="left")
    copy_btn = tk.Button(buttons, text="Copy again", command=on_copy)
    copy_btn.pack(side="left", padx=6)
    chat_btn = tk.Button(buttons, text="Open new chat", command=open_new_chat,
                         state="normal" if project_url else "disabled")
    chat_btn.pack(side="left")
    next_btn = tk.Button(buttons, text="Next >", width=12, command=on_next, bg="#10a37f", fg="white",
                         activebackground="#0d8a6c", font=tkfont.Font(weight="bold"))
    next_btn.pack(side="right")

    tk.Checkbutton(options, text="Always on top", variable=on_top,
                   command=lambda: root.attributes("-topmost", on_top.get())).pack(side="left")
    tk.Checkbutton(options, text="Open a new project chat for each point", variable=open_chat).pack(
        side="left", padx=12)
    skip_btn = tk.Button(options, text="Skip this point", command=on_skip)
    skip_btn.pack(side="right")

    root.bind("<Control-Return>", lambda e: on_next())
    refresh()
    if test_hook:
        root.after(100, lambda: test_hook(root, {"next": on_next, "back": on_back, "skip": on_skip,
                                                 "vars": vars_, "text": text}))
    root.mainloop()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk through the syllabus: copies each ChatGPT question for you.")
    ap.add_argument("-s", "--section", required=True, help="syllabus file in syllabus/, e.g. cardiovascular")
    ap.add_argument("-u", "--project-url", help="ChatGPT Project address (opened for each new point)")
    ap.add_argument("-p", "--points", help="which points, e.g. 17 or 13-20 (default: all)")
    ap.add_argument("--no-open", action="store_true", help="don't open a new chat automatically")
    ap.add_argument("--reset", metavar="POINTS", help="forget progress for these points, e.g. 17 or 13-20")
    args = ap.parse_args(argv)

    section = os.path.splitext(os.path.basename(args.section))[0]
    points = load_syllabus(args.section)
    progress = Progress(PROGRESS_FILE)
    if args.reset:
        nums = [p["number"] for p in select_points(points, args.reset)]
        progress.reset(section, nums)
        print("Progress cleared for: %s" % ", ".join(map(str, nums)))
        return 0
    selected = select_points(points, args.points)
    if not selected:
        sys.exit("No syllabus points match %r." % args.points)
    url = (args.project_url or PROJECT_URLS.get(section, "")).strip()
    if not url.startswith("http"):
        url = ""
        print("No project address given - the helper won't open chats for you; start each one yourself.")
    state = HelperState(section, selected, load_prompts(), progress)
    title = section.replace("_", " ").title()
    try:
        run_window(state, url, title, auto_open=not args.no_open)
    except ImportError:
        sys.exit("This Python has no tkinter. Reinstall Python from python.org (tick 'tcl/tk and IDLE').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
