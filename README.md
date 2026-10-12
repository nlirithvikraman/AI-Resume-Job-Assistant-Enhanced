# Resume Studio — AI Resume and Job Application Assistant

An expanded version of the original Python / Streamlit project, designed to run on your own computer. Upload a resume, understand job fit, keep tailored versions, prepare application drafts, and track your next steps.

## Start on Windows

1. Install **Python 3.11 or 3.12** and enable **Add Python to PATH**.
2. Extract the ZIP completely.
3. Open the `resume_ai` folder.
4. Double-click **start_windows.bat**. The first run installs dependencies and needs internet access.
5. Open **http://localhost:8501** if a browser does not open automatically.
6. Create a local account, sign in, and click **Use demo resume** to explore.

The launcher binds to your local computer only. Keep the terminal open while using the app. Press Ctrl+C to stop it.

### Manual commands (Windows)

```powershell
cd resume_ai
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

### macOS / Linux

```bash
cd resume_ai
bash start.sh
```

Or create a virtual environment, install requirements, then run `python -m streamlit run app.py --server.address 127.0.0.1`.

## Features included

| Area | Working features |
| --- | --- |
| Accounts | Local registration, sign in/out, password change, salted PBKDF2 hashes, five-failure temporary lockout, account-scoped data |
| Resume workspace | PDF/DOCX/TXT parsing, editable text, contact and skill extraction, completeness suggestions |
| Versions | Immutable saved snapshots, restore active text, side-by-side comparison, text diff, delete selected version |
| Matching | JD paste/file upload, skill overlap and gaps, keyword gaps, transparent heuristic score, JSON report |
| Job library | Manual job CRUD, CSV import, duplicate detection, company/role/location/match/deadline filters, CSV export |
| Recommendations | Rank saved jobs by resume fit and show the strongest matches on the dashboard |
| AI studio | Resume tailoring, cover letter, interview questions, answer feedback, learning roadmap, career coach, editable outputs, draft history |
| Export | TXT, DOCX and PDF exports; Classic and Modern document styles; parsed JSON |
| Applications | Add/edit/delete, six statuses, notes, salary, URL, applied date, deadline, follow-up date, filters and CSV export |
| Dashboard | Counts, application status chart, top saved matches, due/overdue actions |
| Recruiter | Rank up to 20 uploaded resumes against a JD, show skill matches/gaps, export CSV |
| Settings | Save search preferences for reference, JSON account backup and restore, password change |
| Setup | Windows/Linux launchers, local Docker Compose with persistent data, example environment file, automated tests |

## First-use walkthrough

1. **Resume workspace:** upload a file, click Read uploaded resume, review extracted text, then save a named version. You can also paste text directly.
2. **Job match:** paste or upload a JD and click Analyze match.
3. **Job library:** save target opportunities or download the CSV template and import up to 200 jobs. Load any saved JD into Job match / AI studio.
4. **AI studio:** configure an API key and model ID if you want generated content. Select a tool, generate a draft, edit it, and export or save it.
5. **Applications:** add an opportunity from the library or manually. Update status, dates and notes as your search progresses.
6. **Dashboard:** review your strongest saved matches and reminders due in the next seven days.
7. **Settings:** download a backup regularly.

Demo resume details are fictional test data, not your own experience. Replace them before applying anywhere.

## AI setup — optional

The sidebar's **AI connection** section accepts a **Gemini API key** and a **Gemini model ID available in your Google AI Studio account**. Enable the consent checkbox before generating. API usage may incur charges.

Alternatively copy `.env.example` to `.env` and set:

```dotenv
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=your_available_model_id
```

Restart the app after editing environment settings. Do not commit `.env`. The app does not save sidebar API keys to the database or backups. Resume/JD text is sent to Google Gemini only when you explicitly run an AI action with consent enabled.

Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey). All parsing, matching, saved jobs, recruiter ranking, tracking and document exports work without an AI key.

AI drafts are not verified facts. Prompts instruct the model not to invent experience, metrics or skills, but you must review every output. Tailoring produces a summary, bullets and gap notes; remove notes before using it as a final resume.

## Scoring and matching

The match estimate uses **60% detected skill coverage + 40% normalized text similarity**. TF-IDF similarity is scaled by two and capped at one. If the JD contains no recognized skills, the score uses text similarity only. Empty or punctuation-only input returns zero.

Scores are guidance, not a real employer ATS score or hiring probability. Required and preferred skills are not distinguished. Recruiter ranking is a human review aid and must not automatically determine hiring decisions.

The base setup uses TF-IDF and makes no model downloads. For optional embedding matching, install `requirements-optional.txt` and set `RESUME_AI_EMBEDDINGS=1`. First use downloads the sentence-transformer model; failure falls back to TF-IDF. Optional spaCy name detection also requires `python -m spacy download en_core_web_sm`. These optional modes were not exercised in this delivery.

## Files and persistence

- `data/workspace.db`: local SQLite accounts and account-scoped records; created on first use.
- Active resume/JD text and unsaved AI drafts are session-only. Save versions/drafts before closing the browser.
- Account backups contain resumes, jobs, applications, preferences and saved AI drafts. They exclude passwords and API keys.
- Backup restore validates records first and imports them as additional records in one transaction. Existing data stays intact; repeated imports can duplicate records.
- Local records are not encrypted at rest. Keep the computer and backups private.
- The original `src/tracker.py` remains for compatibility and its original tests. The new app uses `src/store.py`. An old `applications.db` is **not** automatically imported or assigned to a new account; the original file is left unchanged.

## Limits and excluded integrations

This is a local application, not a production SaaS service. This ZIP does **not** include Google OAuth, email/password-reset delivery, a browser extension, live job-board search/scraping, LinkedIn/GitHub profile import, automatic applications, scheduled background searches, outbound email/Telegram alerts, billing, or an admin dashboard. No such external services are silently simulated.

Recommendations use jobs you save/import. Reminders appear while you use the app; nothing runs or sends messages in the background. Search preferences are saved notes, not an automatic search agent.

Uploads are limited to 10 MB. Scanned image PDFs need OCR before upload. PDF export supports Latin text with standard fonts and explicitly directs unsupported scripts to DOCX. DOCX rendering depends on fonts installed on the receiving computer. Classic/Modern are simple single-column styles.

Registration has no email verification or recovery service. Store your password safely. For internet hosting, add HTTPS, managed identity/recovery, operational monitoring, durable storage and an appropriate security review first. Do not expose this local build as a production multi-tenant service without that work.

## Docker (optional)

```bash
docker compose up --build
```

Open http://localhost:8501. Compose binds only to loopback and uses a named volume for `/app/data`. Enter AI credentials in the sidebar. `docker compose down` keeps the volume; `docker compose down -v` deletes stored data. Docker configuration is supplied but was not run in the build environment.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover parsing, empty matching, skill aliases, ownership enforcement, version immutability, password handling/lockout, import validation, backup transactions, duplicates, recommendations, reminders, CSV safety, document content, mocked AI calls, registration/login, screen navigation and tracker edits.

Live paid AI calls were not made. Test results and validation details are in `VALIDATION.md`.

## Project layout

```text
resume_ai/
  app.py                   Streamlit interface
  src/parser.py            File extraction and structured fields
  src/skills.py            Skill vocabulary and aliases
  src/matcher.py           Match estimate and completeness checks
  src/llm.py               Explicit Gemini requests
  src/store.py             Accounts and owned persistent records
  src/workflows.py         Recommendations, imports and reminders
  src/exports.py           Word and PDF generation
  src/tracker.py           Original legacy tracker module
  sample/                  Fictional demo resume and JD
  tests/                   Unit and UI tests
  start_windows.bat        Windows launcher
  start.sh                 macOS/Linux launcher
```

## Source provenance

Based on https://github.com/nlirithvikraman/AI-Resume-Job-Application-Assistant at commit `81403a70e988918c3ea65b48ab2be50050965e18`. Existing Python/Streamlit modules were retained and extended. No changes were pushed to the GitHub repository. Original licensing/ownership is unchanged; no additional license grant is asserted by this package.

## Gemini integration update

All six AI actions now use the official `google-genai` Python SDK: tailoring, cover letters, interview questions, answer feedback, learning roadmaps and career coaching. The old provider dependency has been removed. Existing local accounts, resumes, jobs and backups remain compatible.

For an existing installation, stop the app, replace the source/setup files from this ZIP, preserve your `data` folder, and restart with `start_windows.bat` to install the new dependency. Replace old AI environment settings with `GEMINI_API_KEY` and `GEMINI_MODEL`, or enter both in the sidebar. No environment file is required when using sidebar settings.

Copy a text-generation model ID available to your project from Google AI Studio; the app intentionally does not hardcode a model that may later be retired. AI consent now explicitly identifies Google Gemini. Requests use a 60-second timeout. Missing/blocked responses and exhausted output budgets produce a clear error instead of silently saving an empty or incomplete draft. Quota and model-access errors receive readable messages.

SDK reference: https://googleapis.github.io/python-genai/
API keys: https://aistudio.google.com/apikey
