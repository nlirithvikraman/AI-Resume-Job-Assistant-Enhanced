import io
import json
from datetime import date
from types import SimpleNamespace
import pytest
from src import store, llm
from src.exports import docx_bytes, pdf_bytes
from src.matcher import match
from src.parser import extract_text
from src.skills import extract_skills
from src.workflows import duplicate_job, rank_jobs, read_jobs_csv, reminders, safe_csv

@pytest.fixture
def account(tmp_path):
    path = tmp_path / 'private.db'
    return path, store.register('alice', 'correct-password', path), store.register('bob', 'another-password', path)


def test_password_and_lockout(account):
    path, alice, _ = account
    assert store.authenticate(' ALICE ', 'correct-password', path)['id'] == alice
    for _ in range(5):
        assert store.authenticate('alice', 'incorrect', path) is None
    assert store.authenticate('alice', 'correct-password', path) is None
    with store.connection(path) as con:
        assert 'correct-password' not in con.execute('SELECT password FROM users WHERE id=?', (alice,)).fetchone()[0]


def test_password_change(account):
    path, alice, _ = account
    with pytest.raises(ValueError):
        store.change_password(alice, 'wrong', 'updated-password', path)
    store.change_password(alice, 'correct-password', 'updated-password', path)
    assert store.authenticate('alice', 'updated-password', path)


def test_ownership_and_immutable_versions(account):
    path, alice, bob = account
    rid = store.save(alice, 'resume', {'label': 'v1', 'text': 'Python'}, path=path)
    assert not store.list_records(bob, 'resume', path)
    with pytest.raises(ValueError):
        store.save(alice, 'resume', {'label': 'v2', 'text': 'Java'}, rid, path)
    store.remove(bob, 'resume', rid, path)
    assert len(store.list_records(alice, 'resume', path)) == 1
    job = store.save(alice, 'job', {'company': 'A', 'role': 'Dev', 'description': 'Python'}, path=path)
    with pytest.raises(ValueError):
        store.save(bob, 'job', {'company': 'B', 'role': 'Dev', 'description': 'Java'}, job, path)


def test_backup_roundtrip_and_atomic_validation(account):
    path, alice, bob = account
    store.save(alice, 'resume', {'label': 'v1', 'text': 'Python'}, path=path)
    backup = store.export_account(alice, path)
    assert 'password' not in json.dumps(backup)
    assert store.import_account(bob, backup, path) == 1
    backup['records']['application'] = [{'data': {'company': 'A', 'role': 'Dev', 'status': 'INVALID'}}]
    with pytest.raises(ValueError):
        store.import_account(bob, backup, path)
    assert len(store.list_records(bob, 'resume', path)) == 1


@pytest.mark.parametrize('resume,jd', [('', ''), ('Python', ''), ('', 'Python'), ('!!!', '???'), ('the a an', 'the and')])
def test_empty_and_stopword_matching(resume, jd):
    assert match(resume, jd).score == 0


def test_aliases():
    assert {'react', 'node.js', 'rest api', 'postgresql'} <= set(extract_skills('ReactJS NodeJS REST APIs Postgres'))
    assert extract_skills('NLP natural language processing').count('natural language processing') == 1


def test_csv_import_duplicate_and_rank():
    jobs = read_jobs_csv(b'company,role,description,location,url\nA,Dev,Python SQL,Remote,https://example.org/jobs?id=1\nB,Dev,Java Spring Boot,Chennai,\n')
    records = [{'id': i, 'data': j} for i,j in enumerate(jobs)]
    assert duplicate_job(records, jobs[0])
    assert not duplicate_job(records, dict(jobs[0], company='C', role='Other', url='https://example.org/jobs?id=2'))
    assert rank_jobs('Python SQL', records)[0]['company'] == 'A'
    with pytest.raises(ValueError):
        read_jobs_csv(b'company,role\nA,Dev\n')
    with pytest.raises(ValueError):
        read_jobs_csv(b'company,role,description,url\nA,Dev,Python,javascript:alert(1)\n')
    assert "'=1+1" in safe_csv([{'company': '=1+1'}])


def test_reminders():
    records = [{'data': {'company':'A', 'role':'Dev', 'status':'Applied', 'deadline':'2026-10-13', 'follow_up':'2026-10-10'}},
               {'data': {'company':'B', 'role':'Dev', 'status':'Rejected', 'follow_up':'2026-10-11'}}]
    rows = reminders(records, date(2026,10,12))
    assert len(rows) == 2 and rows[0]['timing'] == 'Overdue'


def test_export_roundtrip():
    from docx import Document
    import pdfplumber
    content = '# Summary\nPython & SQL developer\n- Built a <sample> project\n' + 'Long content wraps correctly. ' * 70
    word = docx_bytes(content, 'Sample Candidate')
    assert 'Python & SQL developer' in '\n'.join(p.text for p in Document(io.BytesIO(word)).paragraphs)
    with pdfplumber.open(io.BytesIO(pdf_bytes(content, 'Sample Candidate'))) as document:
        body = '\n'.join(p.extract_text() for p in document.pages)
        assert 'Python & SQL developer' in body and '<sample>' in body
    with pytest.raises(ValueError, match='DOCX'):
        pdf_bytes('தமிழ்')
    assert extract_text(word, 'resume.docx')


def test_parser_rejects_unsupported_and_oversize():
    with pytest.raises(ValueError):
        extract_text(b'hello', 'malware.exe')
    with pytest.raises(ValueError):
        extract_text(b'x' * (10 * 1024 * 1024 + 1), 'resume.txt')


def test_ai_mocked_request_and_errors(monkeypatch):
    from google import genai
    seen = {}
    def generate_content(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text='Fact-preserving draft', candidates=[SimpleNamespace(finish_reason='STOP')])
    def client(**kwargs):
        seen['client'] = kwargs
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content), close=lambda: seen.update(closed=True))
    monkeypatch.setattr(genai, 'Client', client)
    out = llm.tailor_resume('Python project', 'Python Docker', ['docker'], api_key='test-key', model='test-model')
    assert out == 'Fact-preserving draft'
    assert seen['model'] == 'test-model' and 'Never invent' in seen['config'].system_instruction
    assert seen['client']['vertexai'] is False and seen['client']['http_options'].timeout == 60000
    assert seen['closed'] and 'Python project' in seen['contents']
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(llm.LLMError, match='No API key'):
        llm.cover_letter('resume', 'job')
    monkeypatch.setattr(llm, 'MODEL', '')
    with pytest.raises(llm.LLMError, match='model ID'):
        llm.cover_letter('resume', 'job', api_key='x')


@pytest.mark.parametrize('reason,text', [('STOP',''), ('SAFETY',None), ('MAX_TOKENS','partial draft')])
def test_gemini_rejects_incomplete_responses(monkeypatch, reason, text):
    from google import genai
    seen = []
    monkeypatch.setattr(genai, 'Client', lambda **kw: SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)])),
        close=lambda: seen.append(True)))
    with pytest.raises(llm.LLMError):
        llm.cover_letter('resume','job',api_key='test',model='test')
    assert seen == [True]


@pytest.mark.parametrize('code,expected', [(403,'access denied'), (404,'model not found'), (429,'quota'), (500,'request failed')])
def test_gemini_provider_errors_are_sanitized(monkeypatch, code, expected):
    from google import genai
    from google.genai import errors
    seen = []
    def fail(**kw):
        raise errors.APIError(code, {'error': {'message': 'secret-provider-payload', 'code': code}})
    monkeypatch.setattr(genai, 'Client', lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=fail),close=lambda: seen.append(True)))
    with pytest.raises(llm.LLMError, match=expected) as error:
        llm.cover_letter('resume','job',api_key='test',model='test')
    assert 'secret-provider-payload' not in str(error.value)
    assert seen == [True]


def test_gemini_environment_key_and_all_actions(monkeypatch):
    from google import genai
    seen = []
    monkeypatch.setenv('GEMINI_API_KEY', 'env-key')
    monkeypatch.setattr(llm, 'MODEL', 'env-model')
    def client(**kw):
        assert kw['api_key'] == 'env-key'
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate),close=lambda: None)
    def generate(**kw):
        seen.append(kw)
        return SimpleNamespace(text='Draft', candidates=[])
    monkeypatch.setattr(genai, 'Client', client)
    assert llm.tailor_resume('resume','job',[]) == 'Draft'
    assert llm.cover_letter('resume','job') == 'Draft'
    assert llm.interview_questions('resume','job') == 'Draft'
    assert llm.evaluate_answer('question','answer','job') == 'Draft'
    assert llm.learning_roadmap('resume','job',[]) == 'Draft'
    assert llm.career_coach('resume','job','question') == 'Draft'
    assert len(seen) == 6 and all(r['model'] == 'env-model' for r in seen)
