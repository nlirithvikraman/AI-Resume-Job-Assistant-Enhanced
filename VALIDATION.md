# Validation report

Validated on 12 October 2026 using Python 3.12 in the build environment.

- `python -m pytest -q`: **30 passed**.
- `git diff --check`: passed.
- Python source compilation: passed.
- Streamlit AppTest: account creation, login/logout, demo loading, all eight workspace screens, saving a resume version, moving a saved job to applications, editing its status and dashboard rendering.
- Storage tests: account isolation, immutable resume versions, password hashing/change, login lockout, backup restore and rollback on invalid content.
- Import/matching tests: CSV validation, unsafe-link rejection, duplicate detection, saved-job ranking, skill aliases and empty/stopword input.
- Output tests: CSV formula neutralization, document text roundtrips, unsupported PDF scripts, file-type and size validation.
- A sample PDF and DOCX were rendered and visually inspected; both were one page with readable typography and no clipping. Preview files are not part of the source package.
- Google Gemini request construction and missing-configuration paths tested with mocks. No live paid AI request made; output quality and real-account model access are not certified.
- Windows launcher, macOS launcher and Docker config are provided but were not executed on those platforms. Optional embeddings/spaCy downloads were not tested.

The ZIP contains source, setup files and tests. It excludes API keys, local databases, virtual environments, Git history and test caches.

## Gemini migration validation

All six AI entry points verified with mocked Gemini SDK responses, including environment and explicit key/model configuration, system instructions, timeout configuration, client cleanup, empty/blocked/truncated output and sanitized 403/404/429/500 provider errors. The existing Streamlit UI tests also pass. No live Gemini request was sent because no user API key was provided.
