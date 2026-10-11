import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import syllabus_prompter as sp
import prompt_helper as ph


class HelperStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "progress.json")
        self.points = sp.select_points(sp.load_syllabus("cardiovascular"), "13,14")
        self.prompts = sp.load_prompts()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def state(self):
        return ph.HelperState("cardiovascular", self.points, self.prompts, sp.Progress(self.path))

    def test_walks_through_points_and_questions(self):
        s = self.state()
        self.assertTrue(s.starting_new_chat)
        self.assertTrue(s.prompt.startswith("Mitral stenosis – Definition"))
        for _ in range(5):
            self.assertFalse(s.next())
        self.assertTrue(s.prompt.startswith("Mitral stenosis – Management and treatment"))
        self.assertTrue(s.next())  # 6th answered -> new point, new chat
        self.assertTrue(s.starting_new_chat)
        self.assertTrue(s.prompt.startswith("Mitral regurgitation – Definition"))
        self.assertEqual(s.remaining_points(), 1)
        for _ in range(6):
            s.next()
        self.assertTrue(s.finished)
        self.assertIsNone(s.prompt)

    def test_progress_survives_restart(self):
        s = self.state()
        s.next(); s.next()
        s2 = self.state()
        self.assertEqual(s2.question_index, 2)
        self.assertFalse(s2.starting_new_chat)
        self.assertTrue(s2.prompt.startswith("Mitral stenosis – Pathogenesis"))

    def test_back_and_skip(self):
        s = self.state()
        s.back()  # nothing to go back to
        self.assertEqual(s.question_index, 0)
        s.next(); s.back()
        self.assertEqual(s.question_index, 0)
        s.skip_point()
        self.assertTrue(s.prompt.startswith("Mitral regurgitation – Definition"))
        s.back()  # back into the skipped point's last question
        self.assertTrue(s.prompt.startswith("Mitral stenosis – Management and treatment"))

    def test_back_after_finishing(self):
        s = self.state()
        for _ in range(12):
            s.next()
        self.assertTrue(s.finished)
        s.back()
        self.assertTrue(s.prompt.startswith("Mitral regurgitation – Management and treatment"))

    def test_skips_points_finished_earlier(self):
        sp.Progress(self.path).update("cardiovascular", 13, done=6)
        self.assertEqual(self.state().point["number"], 14)


try:
    import tkinter
    tkinter.Tk().destroy()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "no tkinter / display")
class WindowTests(unittest.TestCase):
    def test_window_copies_prompts_and_advances(self):
        tmp = tempfile.mkdtemp()
        opened, seen = [], {}
        ph.webbrowser.open = lambda url: opened.append(url)
        state = ph.HelperState("cardiovascular", sp.select_points(sp.load_syllabus("cardiovascular"), "13,14"),
                               sp.load_prompts(), sp.Progress(os.path.join(tmp, "progress.json")))

        def hook(root, ui):
            seen["first"] = root.clipboard_get()
            for _ in range(6):
                ui["next"]()
            seen["after6"] = root.clipboard_get()
            seen["point"] = ui["vars"]["point"].get()
            ui["skip"]()
            seen["done_text"] = ui["vars"]["point"].get()
            root.destroy()

        try:
            ph.run_window(state, "https://chatgpt.com/g/g-p-x/project", "Cardiovascular", test_hook=hook)
        finally:
            shutil.rmtree(tmp)
        self.assertTrue(seen["first"].startswith("Mitral stenosis – Definition"))
        self.assertTrue(seen["after6"].startswith("Mitral regurgitation – Definition"))
        self.assertEqual(seen["point"], "14. Mitral regurgitation")
        self.assertEqual(seen["done_text"], "All done for this selection!")
        self.assertEqual(opened, ["https://chatgpt.com/g/g-p-x/project"] * 2)


if __name__ == "__main__":
    unittest.main()
