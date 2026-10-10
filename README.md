# Autocreate GPT project chats

Creates **one ChatGPT chat per syllabus point** inside your ChatGPT Project and asks the same six questions
in each chat:

```
Cardiology project
 ├─ chat "Mitral stenosis"   → Definition · Aetiology and classification · Pathogenesis ·
 ├─ chat "Mitral regurgitation"     Physical examination and signs and symptoms · Diagnosis ·
 ├─ chat "Endocarditis"             Management and treatment
 └─ … one per syllabus point (Cardiology = points 13–38)
```

It types into ChatGPT in your own Chrome, the same way you would. It waits for each reply to finish,
pauses, and then asks the next question. It also saves its progress after every reply.

> **Read this first.** OpenAI's terms don't allow automated use of the ChatGPT website, so using this tool
> could get your account flagged or limited. To keep the risk down, the tool goes slowly: it waits 8–20 s
> between questions and 30–60 s between chats, and it makes at most 5 new chats per run by default. It
> stops immediately if ChatGPT shows a usage limit, an error, or a "verify you're human" check. Keep the
> runs small, and don't run it all day.

## One-time setup (Windows)

1. **Python 3**: install it from https://www.python.org/downloads/ and tick **"Add Python to PATH"**.
2. **Google Chrome** must be installed. The tool uses your Chrome, so nothing else is downloaded.
3. Download this repo (green **Code** button → **Download ZIP**) and unzip it.
4. Double-click **`Setup.bat`**.
5. Double-click **`Log in to ChatGPT.bat`**, log in to ChatGPT in the window that opens, then **close that
   window**. The tool uses its own Chrome profile (the `chrome-profile` folder), so you log in only once.
6. Open your **Cardiology** project in ChatGPT and copy the address bar (it looks like
   `https://chatgpt.com/g/g-p-…/project`). Right-click **`Run Cardiology.bat`** → *Edit*, paste the address
   into the `PROJECT_URL=` line, and save.

## Running it

Double-click **`Run Cardiology.bat`**. A Chrome window opens and you can watch it work. The black window
shows its progress:

```
This run: 5 chat(s): 13 Mitral stenosis, 14 Mitral regurgitation, 15 Aortic stenosis, ...
[13] Mitral stenosis
  > Mitral stenosis – Definition. Begin your reply with the bold title "Mitral stenosis – Definition".
    reply received (1834 characters)
  ...
```

- **Run it again** later to do the next 5 points. Finished points are always skipped.
- **If it stops** (usage limit, error, closed window, or Ctrl-C), just run it again later. A half-finished
  chat continues in the **same chat** from the next question.
- **Points you've already done by hand** (e.g. Endocarditis): skip them with
  `--points 13-16,18-38`, or delete those lines from `syllabus/cardiovascular.txt`.

Options go on the `OPTIONS=` line in the .bat file, or after the command:

| Option | What it does |
| --- | --- |
| `--points 17` / `--points 13-20` / `--points 13,15,30` | Only these syllabus points |
| `--max-points 10` | How many new chats per run (default 5) |
| `--dry-run` | List every chat and question; opens nothing |
| `--status` | Show which points are done, half done or not started |
| `--reset 17` | Forget progress for a point, so it gets a new chat next run |
| `--save-replies` | Also save each chat's replies to `replies/017 Endocarditis.md` (on by default in the .bat) |

## Other projects

Copy `Run Cardiology.bat`, rename it (e.g. `Run Pulmonology.bat`), and change two lines:

- `SECTION=`: one of the files in the `syllabus` folder: `pulmonary`, `cardiovascular`, `rheumatic`,
  `hematologic`, `endocrine_metabolic`, `gastrointestinal`, `renal`, `toxicology_allergy`, `oncologic`,
  `treatment_principles`
- `PROJECT_URL=`: that ChatGPT project's address

## Editing what it asks

- **`syllabus/*.txt`**: one line per chat, taken from the state exam synopsis. Text after `=>` is the short
  name used in the questions (e.g. `13. Diseases of the mitral valve: mitral stenosis => Mitral stenosis`).
  Cardiology already has short names that match your Anki subdecks. For the other sections, add `=> Name`
  wherever the syllabus wording is too long for a question.
- **`prompts.txt`**: the six questions, one per line. `{topic}` is the short name, `{full}` the full
  syllabus wording, `{number}` the point number. Add, remove or reword lines as you like.

## Straight into Anki

The replies start with titles like **"Endocarditis – Definition"**, which is the format
[GPT-to-Anki](https://github.com/aaron94861/GPT-to-Anki) reads. You can make the cards in either of two ways:

- Keep GPT-to-Anki's `Watch Cardiology.bat` running and click **Copy** under each reply, as before.
- Or turn a whole saved chat into six cards in one go:
  ```bat
  py ..\GPT-to-Anki\gpt_to_anki.py "replies\017 Endocarditis.md" --parent "Internal Medicine::Cardiology"
  ```

## If something goes wrong

| Message | What to do |
| --- | --- |
| `Couldn't find the ChatGPT message box` | Check that you're logged in (run `Log in to ChatGPT.bat`) and that the project address is right |
| `ChatGPT shows a message containing 'usage limit'` | You've hit ChatGPT's limit. Try again in a few hours |
| `Couldn't start chrome` | Install Google Chrome, or set `BROWSER_CHANNEL = "msedge"` in `syllabus_prompter.py` to use Edge |
| It keeps stopping at the same place | ChatGPT may have changed its page. The selectors are in one block at the top of `chatgpt_page.py` |
| Chrome says the profile is in use | Close the Chrome window opened by `Log in to ChatGPT.bat` first |

## Tests

```bash
pip install playwright
python -m unittest discover -s tests
```

The end-to-end tests drive a local fake ChatGPT page (`tests/fake_chatgpt.html`) with Chromium. If no
Chromium is found, they are skipped.
