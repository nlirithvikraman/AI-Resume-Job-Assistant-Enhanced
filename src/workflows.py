"""Local recommendations, CSV imports, reminders and comparison helpers."""
import csv
import io
from datetime import date, timedelta
from difflib import unified_diff
from urllib.parse import urlsplit, urlunsplit
from .matcher import match


def normalized_url(url):
    p = urlsplit(url.strip())
    # Keep query parameters: many job boards identify jobs in the query string.
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def duplicate_job(jobs, candidate):
    for record in jobs:
        job = record['data']
        url = candidate.get('url', '').strip()
        if url and job.get('url') and normalized_url(url) == normalized_url(job['url']):
            return True
        fields = ('company', 'role', 'location')
        if all(str(job.get(k, '')).strip().casefold() == str(candidate.get(k, '')).strip().casefold() for k in fields):
            return True
    return False


def read_jobs_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if not {'company', 'role', 'description'} <= set(reader.fieldnames or []):
        raise ValueError('CSV needs company, role and description columns.')
    rows = []
    for i, row in enumerate(reader, 2):
        if len(rows) >= 200:
            raise ValueError('Import at most 200 jobs at a time.')
        job = {k: (row.get(k) or '').strip() for k in ('company', 'role', 'description', 'location', 'url', 'deadline', 'salary')}
        from .store import _validate
        try:
            _validate('job', job)
        except ValueError as exc:
            raise ValueError(f'CSV row {i}: {exc}') from exc
        rows.append(job)
    return rows


def rank_jobs(resume, jobs):
    result = []
    for record in jobs:
        job = record['data']
        m = match(resume, job['description'])
        result.append({'id': record['id'], **job, 'match': m.score,
                       'matched': ', '.join(m.matched_skills), 'gaps': ', '.join(m.missing_skills)})
    return sorted(result, key=lambda x: (-x['match'], x['company'].lower()))


def reminders(records, today=None):
    today = today or date.today()
    items = []
    for record in records:
        data = record['data']
        if data.get('status') in {'Rejected', 'Withdrawn', 'Offer'}:
            continue
        for field, label in [('deadline', 'Application deadline'), ('follow_up', 'Follow up')]:
            value = data.get(field)
            if not value:
                continue
            due = date.fromisoformat(value)
            if due <= today + timedelta(days=7):
                items.append({'company': data['company'], 'role': data['role'], 'action': label,
                              'due': value, 'timing': 'Overdue' if due < today else 'Today' if due == today else 'This week'})
    return sorted(items, key=lambda x: x['due'])


def compare_text(before, after):
    return '\n'.join(unified_diff(before.splitlines(), after.splitlines(), fromfile='Original', tofile='Revised', lineterm=''))


def safe_csv(rows):
    """Neutralize spreadsheet formulas without changing stored values."""
    if not rows:
        return ''
    stream = io.StringIO(newline='')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: "'" + str(v) if str(v).lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
    return stream.getvalue()
