import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import syllabus_prompter as sp
import chatgpt_page as cp

FAKE_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_chatgpt.html")


class SyllabusTests(unittest.TestCase):
    def test_cardiovascular(self):
        pts = sp.load_syllabus("cardiovascular")
        self.assertEqual([p["number"] for p in pts], list(range(13, 39)))
        self.assertEqual(pts[0]["topic"], "Mitral stenosis")
        self.assertEqual(pts[0]["full"], "Diseases of the mitral valve: mitral stenosis")
        p21 = [p for p in pts if p["number"] == 21][0]
        self.assertIn("cardiogenic shock", p21["full"])
        self.assertEqual(p21["topic"], "Acute heart failure")

    def test_all_sections_cover_whole_syllabus(self):
        nums = []
        for f in os.listdir(sp.SYLLABUS_DIR):
            nums += [p["number"] for p in sp.load_syllabus(f[:-4])]
        self.assertEqual(sorted(nums), list(range(1, 171)))

    def test_parse_formats(self):
        pts = sp.parse_syllabus("# comment\n\n5. Long point that\n   continues here\n6) Gout\n7. A => B\n")
        self.assertEqual(pts, [
            {"number": 5, "full": "Long point that continues here", "topic": "Long point that continues here"},
            {"number": 6, "full": "Gout", "topic": "Gout"},
            {"number": 7, "full": "A", "topic": "B"},
        ])

    def test_select_points(self):
        pts = sp.load_syllabus("cardiovascular")
        self.assertEqual([p["number"] for p in sp.select_points(pts, "17")], [17])
        self.assertEqual([p["number"] for p in sp.select_points(pts, "13-15, 30")], [13, 14, 15, 30])
        self.assertEqual(len(sp.select_points(pts, None)), 26)

    def test_prompts(self):
        prompts = sp.load_prompts()
        self.assertEqual(len(prompts), 6)
        p = {"number": 17, "full": "Endocarditis", "topic": "Endocarditis"}
        self.assertTrue(sp.build_prompt(prompts[0], p).startswith("Endocarditis – Definition."))
        self.assertIn('"Endocarditis – Management and treatment"', sp.build_prompt(prompts[5], p))


class ProgressTests(unittest.TestCase):
    def test_update_reset_reload(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "progress.json")
            pr = sp.Progress(path)
            pr.update("cardio", 17, done=3, chat_url="u")
            self.assertFalse(pr.is_complete("cardio", 17, 6))
            pr.update("cardio", 17, done=6)
            self.assertTrue(sp.Progress(path).is_complete("cardio", 17, 6))
            pr.reset("cardio", [17])
            self.assertEqual(sp.Progress(path).get("cardio", 17)["done"], 0)
        finally:
            shutil.rmtree(d)


class PageHelperTests(unittest.TestCase):
    def test_stop_phrases(self):
        self.assertEqual(cp.find_stop_phrase("You’ve reached your limit"), "you've reached")
        self.assertIsNone(cp.find_stop_phrase("Endocarditis is an inflammation of the endocardium."))

    def test_html_to_markdown(self):
        html = ("<h3>Endocarditis – Definition</h3><p><strong>Endocarditis</strong> is <em>inflammation</em>.</p>"
                "<ul><li>Valves<ul><li>Mitral</li></ul></li><li>Devices</li></ul>"
                "<ol><li>One</li><li>Two</li></ol>"
                "<table><thead><tr><th>Organism</th><th>Setting</th></tr></thead>"
                "<tbody><tr><td>S. aureus</td><td>IVDU</td></tr></tbody></table><button>Copy</button>")
        md = cp.html_to_markdown(html)
        self.assertEqual(md, "### Endocarditis – Definition\n\n**Endocarditis** is *inflammation*.\n\n"
                             "- Valves\n  - Mitral\n- Devices\n\n1. One\n2. Two\n\n"
                             "| Organism | Setting |\n| --- | --- |\n| S. aureus | IVDU |")


def _browser_path():
    for p in (os.environ.get("PROMPTER_BROWSER_PATH"), "/opt/pw-browsers/chromium"):
        if p and os.path.exists(p):
            return p
    return None


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # every path serves the fake ChatGPT page (project and /c/ chat URLs)
        with open(FAKE_PAGE, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@unittest.skipUnless(sync_playwright and _browser_path(), "playwright/chromium not available")
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_port
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=_browser_path())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.progress = sp.Progress(os.path.join(self.tmp, "progress.json"))
        self.points = sp.select_points(sp.load_syllabus("cardiovascular"), "17,19")
        self.prompts = sp.load_prompts()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, project_url, max_points=5):
        ctx = self.browser.new_context()
        page = ctx.new_page()
        n = sp.run("cardiovascular", self.points, self.prompts, project_url,
                   lambda: cp.ChatGPTPage(page, reply_timeout=20, stable_secs=0.6), self.progress, max_points,
                   save_replies=True, replies_dir=self.tmp, delays=((0, 0), (0, 0)), sleep=lambda s: None)
        sent = json.loads(page.evaluate("localStorage.getItem('sent') || '[]'"))
        ctx.close()
        return n, sent

    def test_one_chat_per_point_with_six_prompts(self):
        n, sent = self._run(self.base + "/g/g-p-test/project")
        self.assertEqual(n, 2)
        self.assertEqual(len(sent), 12)
        # each chat starts on the project page, the rest go into that chat
        self.assertEqual([s["url"] for s in sent[:6]], ["/g/g-p-test/project"] + ["/c/chat-1"] * 5)
        self.assertEqual(sent[6]["url"], "/g/g-p-test/project")
        self.assertTrue(sent[0]["prompt"].startswith("Endocarditis – Definition"))
        self.assertTrue(sent[11]["prompt"].startswith("Myocarditis – Management and treatment"))
        self.assertTrue(self.progress.is_complete("cardiovascular", 17, 6))
        with open(os.path.join(self.tmp, "017 Endocarditis.md"), encoding="utf-8") as f:
            saved = f.read()
        self.assertEqual(saved.count("**Endocarditis – "), 6)
        self.assertIn("- First point", saved)
        self.assertIn("| A | B |", saved)

    def test_limit_stops_and_resume_continues_same_chat(self):
        n, sent = self._run(self.base + "/g/g-p-test/project?limit=4")
        self.assertEqual(n, 0)
        self.assertEqual(len(sent), 4)
        st = self.progress.get("cardiovascular", 17)
        self.assertEqual(st["done"], 3)
        self.assertTrue(st["chat_url"].endswith("/c/chat-1"))
        # next run (limit gone) resumes in the same chat at question 4
        n, sent = self._run(self.base + "/g/g-p-test/project", max_points=1)
        self.assertEqual(n, 1)
        self.assertEqual(sent[0]["url"], "/c/chat-1")
        self.assertTrue(sent[0]["prompt"].startswith("Endocarditis – Physical examination"))
        self.assertEqual(len(sent), 3)
        self.assertFalse(self.progress.is_complete("cardiovascular", 19, 6))

    def test_max_points(self):
        n, sent = self._run(self.base + "/g/g-p-test/project", max_points=1)
        self.assertEqual((n, len(sent)), (1, 6))


if __name__ == "__main__":
    unittest.main()
