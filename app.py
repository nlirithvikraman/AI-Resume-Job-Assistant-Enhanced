"""Run with python -m streamlit run app.py."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src import llm, store
from src.exports import docx_bytes, pdf_bytes
from src.matcher import match, score_resume
from src.parser import extract_text, parse_resume
from src.workflows import compare_text, duplicate_job, rank_jobs, read_jobs_csv, reminders, safe_csv

st.set_page_config(page_title='Resume Studio', page_icon='📄', layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1400px}
[data-testid="stMetric"] {border:1px solid #d8e2e9;border-radius:12px;padding:15px}
[data-testid="stSidebar"] {border-right:1px solid #d8e2e9}
h1 {letter-spacing:-1px} div.stButton>button {border-radius:8px}
</style>''', unsafe_allow_html=True)


def notify(text):
    st.session_state['notice'] = text
    st.rerun()


def attempt(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        st.error(str(exc))
        return None


if 'user' not in st.session_state:
    st.title('Resume Studio')
    st.write('Your resume, job matches and next steps — in one workspace.')
    st.caption('Local accounts • Private workspaces • AI is optional')
    login, signup = st.tabs(['Sign in', 'Create account'])
    with login:
        with st.form('login'):
            username = st.text_input('Username')
            password = st.text_input('Password', type='password')
            submit = st.form_submit_button('Sign in', type='primary')
        if submit:
            user = store.authenticate(username, password)
            if user:
                st.session_state.clear()
                st.session_state['user'] = user
                st.rerun()
            else:
                st.error('Sign in failed. Check your credentials; after five failures, wait five minutes.')
    with signup:
        with st.form('signup'):
            new_user = st.text_input('Choose username')
            new_pass = st.text_input('Choose password (10+ characters)', type='password')
            confirm = st.text_input('Confirm password', type='password')
            register = st.form_submit_button('Create account')
        if register:
            if new_pass != confirm:
                st.error('Passwords do not match.')
            elif attempt(store.register, new_user, new_pass):
                st.success('Account created. Open Sign in to continue.')
    st.info('First time? Create a local account, then use the demo resume from the sidebar. No API key needed.')
    st.stop()

owner = st.session_state['user']['id']
with st.sidebar:
    st.title('📄 Resume Studio')
    st.caption('Signed in as ' + st.session_state['user']['username'])
    page = st.radio('Workspace', ['Dashboard', 'Resume workspace', 'Job match', 'Job library', 'AI studio', 'Applications', 'Recruiter', 'Settings'])
    st.divider()
    with st.expander('AI connection'):
        api_key = st.text_input('Gemini API key', type='password', key='api_key')
        model = st.text_input('Gemini model ID', value=os.getenv('GEMINI_MODEL', ''), key='model')
        consent = st.checkbox('Allow sending resume and job text to Google Gemini', key='ai_consent')
        st.caption('API key stays in this session. Requests may incur provider charges.')
    if st.button('Use demo resume'):
        st.session_state.pop('resume_editor', None)
        st.session_state['resume_text'] = (Path(__file__).parent / 'sample/resume.txt').read_text()
        st.session_state['jd'] = (Path(__file__).parent / 'sample/job.txt').read_text()
        notify('Demo resume and job description loaded.')
    if st.button('Sign out'):
        st.session_state.clear()
        st.rerun()

if st.session_state.get('notice'):
    st.success(st.session_state.pop('notice'))
text = st.session_state.get('resume_text', '')
jd = st.session_state.get('jd', '')
parsed = parse_resume(text) if text.strip() else None
jobs = store.list_records(owner, 'job')
apps = store.list_records(owner, 'application')
versions = store.list_records(owner, 'resume')


def require_resume():
    if not parsed:
        st.info('Open Resume workspace to upload or paste a resume, or use the demo in the sidebar.')
        return False
    return True


def downloads(content, name, title, key):
    template = st.selectbox('Export style', ['Classic', 'Modern'], key=key + '_template')
    cols = st.columns(3)
    cols[0].download_button('Text', content, name + '.txt', mime='text/plain', key=key + '_txt')
    cols[1].download_button('Word', docx_bytes(content, title, template), name + '.docx',
                            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document', key=key + '_docx')
    try:
        pdf = pdf_bytes(content, title, template)
        cols[2].download_button('PDF', pdf, name + '.pdf', mime='application/pdf', key=key + '_pdf')
    except ValueError as exc:
        cols[2].caption(str(exc))


def ai_call(label, fn, *args, **kwargs):
    if not consent:
        st.error('Enable the Google Gemini consent checkbox in AI connection first.')
        return None
    try:
        with st.spinner(label):
            return fn(*args, **kwargs, api_key=api_key or None, model=model or None)
    except llm.LLMError as exc:
        st.error(str(exc))
    except Exception:
        st.error('AI request failed. Check your key, model access, connection and provider quota. Nothing was submitted to an employer.')
    return None


def job_form(prefix, existing=None):
    existing = existing or {}
    c1, c2 = st.columns(2)
    data = {'company': c1.text_input('Company', existing.get('company', ''), key=prefix+'company'),
            'role': c2.text_input('Role', existing.get('role', ''), key=prefix+'role'),
            'location': c1.text_input('Location', existing.get('location', ''), key=prefix+'location'),
            'salary': c2.text_input('Salary (as advertised)', existing.get('salary', ''), key=prefix+'salary'),
            'url': st.text_input('Job URL', existing.get('url', ''), key=prefix+'url'),
            'description': st.text_area('Job description', existing.get('description', ''), height=160, key=prefix+'description')}
    deadline = st.date_input('Deadline (optional)', date.fromisoformat(existing['deadline']) if existing.get('deadline') else None, key=prefix+'deadline')
    data['deadline'] = deadline.isoformat() if deadline else ''
    return data


if page == 'Dashboard':
    st.title('Your next opportunity')
    st.caption('A clear view of your search and what needs attention.')
    cols = st.columns(4)
    cols[0].metric('Saved jobs', len(jobs))
    cols[1].metric('Applications', len(apps))
    cols[2].metric('Interviews', sum(r['data'].get('status') == 'Interview' for r in apps))
    cols[3].metric('Resume versions', len(versions))
    a, b = st.columns([1.2, 1])
    with a:
        st.subheader('Next actions')
        due = reminders(apps)
        if due:
            st.dataframe(pd.DataFrame(due), hide_index=True, use_container_width=True)
        else:
            st.info('No application deadlines or follow-ups due in the next seven days.')
        if not parsed:
            st.write('1. Add your resume in Resume workspace.\n2. Save target jobs in Job library.\n3. Compare matches and track applications.')
        elif jobs:
            st.subheader('Strongest saved matches')
            ranked = rank_jobs(text, jobs)[:5]
            st.dataframe(pd.DataFrame(ranked)[['company', 'role', 'match', 'gaps']], hide_index=True, use_container_width=True)
            st.caption('Ranks your saved jobs only. Match scores are heuristic, not employer ATS results.')
    with b:
        st.subheader('Application pipeline')
        if apps:
            counts = pd.Series([r['data']['status'] for r in apps]).value_counts().reindex(store.STATUSES, fill_value=0)
            st.bar_chart(counts)
        else:
            st.write('Your pipeline will appear after you save an application.')
        if parsed:
            score, _ = score_resume(parsed)
            st.metric('Resume completeness', f'{score}/100')

elif page == 'Resume workspace':
    st.title('Resume workspace')
    st.caption('Upload, edit, compare and preserve versions of your resume.')
    upload = st.file_uploader('Upload resume • PDF, DOCX or TXT • max 10 MB', type=['pdf', 'docx', 'txt'])
    if upload and st.button('Read uploaded resume'):
        try:
            extracted = extract_text(upload.getvalue(), upload.name)
            if not extracted.strip():
                st.error('No text found. Scanned PDFs need OCR first; upload DOCX/TXT or paste the text.')
            else:
                st.session_state['resume_text'] = extracted
                st.session_state.pop('resume_editor', None)
                notify('Resume loaded. Review the extracted text below.')
        except Exception:
            st.error('Could not read this file. Check its format, size and whether it is password protected.')
    with st.form('resume_edit'):
        edited = st.text_area('Resume text', text, height=350, key='resume_editor')
        label = st.text_input('Version label', placeholder='Backend developer — October')
        apply = st.form_submit_button('Use this text')
        save = st.form_submit_button('Save new version', type='primary')
    if apply or save:
        if not edited.strip():
            st.error('Enter resume text first.')
        elif len(edited) > 60000:
            st.error('Keep resume text under 60,000 characters.')
        else:
            st.session_state['resume_text'] = edited
            if save:
                store.save(owner, 'resume', {'label': label.strip() or 'Untitled resume', 'text': edited})
            notify('Resume version saved.' if save else 'Active resume updated.')
    if parsed:
        detail, history, export = st.tabs(['Analysis', 'Version history', 'Export'])
        with detail:
            score, tips = score_resume(parsed)
            st.metric('Completeness score', f'{score}/100')
            st.caption('Rule-based guidance; do not invent experience or numbers to increase this score.')
            st.write({'Name': parsed.name, 'Email': parsed.email, 'Phone': parsed.phone, 'Skills': ', '.join(parsed.skills)})
            for tip in tips:
                st.write('• ' + tip)
            for title, body in parsed.sections.items():
                with st.expander(title.title()):
                    st.text(body)
        with history:
            if versions:
                selected = st.selectbox('Saved version', versions, format_func=lambda x: f"#{x['id']} · {x['data']['label']} · {x['created']}")
                before, after = st.columns(2)
                before.text_area('Saved text', selected['data']['text'], height=250, disabled=True)
                after.text_area('Active text', text, height=250, disabled=True)
                st.code(compare_text(selected['data']['text'], text) or 'No differences.', language='diff')
                if st.button('Restore as active text'):
                    st.session_state['resume_text'] = selected['data']['text']
                    st.session_state.pop('resume_editor', None)
                    notify('Version restored. Original saved version remains unchanged.')
                if st.checkbox('Confirm removal of selected version') and st.button('Delete selected version'):
                    store.remove(owner, 'resume', selected['id'])
                    notify('Version removed.')
            else:
                st.info('Save a version to keep a persistent copy.')
        with export:
            downloads(text, 'resume', parsed.name or 'Resume', 'resume_export')
            st.download_button('Parsed JSON', json.dumps(parsed.to_dict(), indent=2), 'resume.json', 'application/json')
    elif versions:
        selected = st.selectbox('Load saved resume', versions, format_func=lambda x: x['data']['label'])
        if st.button('Load version'):
            st.session_state['resume_text'] = selected['data']['text']
            st.session_state.pop('resume_editor', None)
            notify('Saved resume loaded.')

elif page == 'Job match':
    st.title('Understand your fit')
    with st.form('job_context'):
        jd_input = st.text_area('Paste a job description', jd, height=230)
        jd_upload = st.file_uploader('Or upload a job description', type=['pdf', 'docx', 'txt'])
        if st.form_submit_button('Analyze match', type='primary'):
            try:
                value = extract_text(jd_upload.getvalue(), jd_upload.name) if jd_upload else jd_input
                if not value.strip():
                    st.error('Add a job description.')
                elif len(value) > 60000:
                    st.error('Job description must be under 60,000 characters.')
                else:
                    st.session_state['jd'] = value
                    st.rerun()
            except Exception:
                st.error('Could not read the job-description file.')
    if require_resume() and jd.strip():
        result = match(text, jd)
        cols = st.columns(3)
        cols[0].metric('Match estimate', f'{result.score}%')
        cols[1].metric('Detected skill coverage', f'{result.skill_coverage:.0%}')
        cols[2].metric('Text similarity', f'{result.similarity:.2f}')
        st.caption('60% detected skill coverage + 40% normalized text similarity. With no recognized JD skills, only similarity is used. This is not a real ATS score or hiring probability.')
        st.success('Matched: ' + (', '.join(result.matched_skills) or 'None detected'))
        st.warning('Skill gaps: ' + (', '.join(result.missing_skills) or 'None detected'))
        st.write('Other keywords to review: ' + ', '.join(result.missing_keywords))
        st.info('Mention a missing skill only if you actually have it. Otherwise use AI studio to plan your learning.')
        st.download_button('Download match report', json.dumps(result.__dict__, indent=2), 'match_report.json', 'application/json')

elif page == 'Job library':
    st.title('Your job shortlist')
    st.caption('Save jobs manually or import a CSV. Recommendations rank this library, not live internet listings.')
    with st.expander('Add a job', expanded=not jobs):
        with st.form('new_job'):
            data = job_form('new_')
            add = st.form_submit_button('Save job', type='primary')
        if add:
            if duplicate_job(jobs, data):
                st.warning('A job with this URL or company, role and location is already saved.')
            elif attempt(store.save, owner, 'job', data):
                notify('Job saved.')
    with st.expander('Import job CSV'):
        st.download_button('CSV template', 'company,role,description,location,url,deadline,salary\nExample Co,Python Developer,"Python Django SQL REST API",Chennai,,,\n', 'job_template.csv')
        csv_file = st.file_uploader('Job CSV', type=['csv'])
        if csv_file and st.button('Import jobs'):
            if csv_file.size > 2 * 1024 * 1024:
                st.error('CSV must be smaller than 2 MB.')
            else:
                imported = attempt(read_jobs_csv, csv_file.getvalue())
                if imported is not None:
                    count = 0
                    for job in imported:
                        if not duplicate_job(jobs, job):
                            rid = store.save(owner, 'job', job)
                            jobs.append({'id': rid, 'data': job})
                            count += 1
                    notify(f'Imported {count} jobs. Skipped {len(imported)-count} duplicates.')
    if jobs:
        c1, c2, c3 = st.columns(3)
        search = c1.text_input('Search company or role')
        location = c2.text_input('Filter location')
        minimum = c3.slider('Minimum match', 0, 100, 0)
        open_only = st.checkbox('Hide jobs with past deadlines')
        rows = rank_jobs(text, jobs) if parsed else [{'id': r['id'], **r['data'], 'match': 0, 'matched': '', 'gaps': ''} for r in jobs]
        rows = [r for r in rows if search.lower() in (r['company'] + ' ' + r['role']).lower()
                and location.lower() in r.get('location', '').lower() and r['match'] >= minimum
                and (not open_only or not r.get('deadline') or r['deadline'] >= date.today().isoformat())]
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df[['company', 'role', 'location', 'match', 'deadline', 'gaps']], hide_index=True, use_container_width=True)
            st.download_button('Export filtered jobs', safe_csv(rows), 'jobs.csv', 'text/csv')
            selected = st.selectbox('Manage job', rows, format_func=lambda r: f"#{r['id']} · {r['company']} — {r['role']}")
            a, b = st.columns(2)
            if a.button('Use this job description'):
                st.session_state['jd'] = selected['description']
                notify('Job description loaded. Open Job match or AI studio.')
            if b.button('Add to applications'):
                candidate = {k: v for k, v in selected.items() if k not in {'id', 'matched', 'gaps'}}
                candidate.update(status='Saved', notes='', applied_on='', follow_up='')
                if duplicate_job(apps, candidate):
                    st.warning('This application already exists.')
                else:
                    store.save(owner, 'application', candidate)
                    notify('Application added.')
            with st.expander('Edit selected job'):
                with st.form(f"edit_job_{selected['id']}"):
                    updated = job_form(f"edit_{selected['id']}_", selected)
                    update = st.form_submit_button('Update job')
                if update:
                    others = [r for r in jobs if r['id'] != selected['id']]
                    if duplicate_job(others, updated):
                        st.warning('Another saved job already matches those details.')
                    elif attempt(store.save, owner, 'job', updated, selected['id']):
                        notify('Job updated.')
                if st.checkbox('Confirm job deletion') and st.button('Delete job'):
                    store.remove(owner, 'job', selected['id'])
                    notify('Job deleted. Existing applications are kept.')
        else:
            st.info('No jobs match these filters.')

elif page == 'AI studio':
    st.title('Prepare a stronger application')
    st.caption('Generated drafts are suggestions. Review every claim before using them.')
    if require_resume():
        if not jd.strip():
            st.info('Add a job description in Job match first.')
        else:
            # Context-specific keys prevent stale results from a previous resume/JD.
            context = hashlib.sha256((text + '\0' + jd).encode()).hexdigest()[:12]
            tool = st.selectbox('Choose tool', ['Tailor resume', 'Cover letter', 'Interview practice', 'Learning roadmap', 'Career coach'])
            result_key = context + tool
            gaps = match(text, jd).missing_skills
            if tool == 'Tailor resume':
                if st.button('Generate tailored draft', type='primary'):
                    out = ai_call('Tailoring resume…', llm.tailor_resume, text, jd, gaps)
                    if out:
                        st.session_state[result_key] = out
            elif tool == 'Cover letter':
                if st.button('Generate cover letter', type='primary'):
                    out = ai_call('Writing cover letter…', llm.cover_letter, text, jd, name=parsed.name)
                    if out:
                        st.session_state[result_key] = out
            elif tool == 'Interview practice':
                if st.button('Generate questions', type='primary'):
                    out = ai_call('Preparing questions…', llm.interview_questions, text, jd)
                    if out:
                        st.session_state[result_key] = out
                question = st.text_area('Question you are answering', key=context+'question')
                answer = st.text_area('Your answer', key=context+'answer')
                if st.button('Evaluate answer', disabled=not (question.strip() and answer.strip())):
                    out = ai_call('Evaluating answer…', llm.evaluate_answer, question, answer, jd)
                    if out:
                        st.session_state[result_key+'feedback'] = out
                if st.session_state.get(result_key+'feedback'):
                    st.markdown(st.session_state[result_key+'feedback'])
            elif tool == 'Learning roadmap':
                weeks = st.slider('Plan duration in weeks', 2, 16, 8)
                if st.button('Build learning plan', type='primary'):
                    out = ai_call('Planning learning…', llm.learning_roadmap, text, jd, gaps, weeks=weeks)
                    if out:
                        st.session_state[result_key] = out
            else:
                question = st.text_area('What would you like help with?', key=context+'coach')
                if st.button('Ask career coach', disabled=not question.strip()):
                    out = ai_call('Thinking through next steps…', llm.career_coach, text, jd, question)
                    if out:
                        st.session_state[result_key] = out
            if st.session_state.get(result_key):
                content = st.session_state[result_key]
                if tool == 'Tailor resume':
                    left, right = st.columns(2)
                    left.text_area('Original resume', text, height=300, disabled=True)
                    right.markdown(content)
                else:
                    st.markdown(content)
                draft = st.text_area('Edit your draft before export', content, height=300, key=result_key+hashlib.sha256(content.encode()).hexdigest()[:8])
                downloads(draft, 'application_draft', tool, result_key)
                if st.button('Save draft to history'):
                    store.save(owner, 'draft', {'tool': tool, 'text': draft, 'context': context, 'job_description': jd})
                    st.success('Draft saved.')
                if tool == 'Tailor resume' and st.button('Save draft as a new resume version'):
                    store.save(owner, 'resume', {'label': 'Tailored draft — review required', 'text': draft})
                    st.success('Version saved. Remove gap notes before sending to an employer.')
    with st.expander('Saved AI drafts'):
        drafts = store.list_records(owner, 'draft')
        if drafts:
            selected = st.selectbox('Draft', drafts, format_func=lambda r: f"{r['data']['tool']} · {r['created']} · #{r['id']}")
            st.text(selected['data']['text'])
            st.download_button('Download saved draft', selected['data']['text'], 'saved_draft.txt')
            if st.checkbox('Confirm draft deletion') and st.button('Delete draft'):
                store.remove(owner, 'draft', selected['id'])
                notify('Draft deleted.')
        else:
            st.write('No saved drafts.')

elif page == 'Applications':
    st.title('Application tracker')
    st.caption('Track progress and plan follow-ups. This app does not submit applications or send messages.')
    with st.expander('Add application manually', expanded=not apps):
        with st.form('new_application'):
            data = job_form('app_new_')
            data['status'] = st.selectbox('Status', store.STATUSES)
            data['notes'] = st.text_area('Notes')
            submitted = st.form_submit_button('Add application', type='primary')
        if submitted:
            data.update(match=match(text, data['description']).score if parsed and data['description'] else 0,
                        applied_on=date.today().isoformat() if data['status'] != 'Saved' else '', follow_up='')
            if duplicate_job(apps, data):
                st.warning('This application already exists.')
            elif attempt(store.save, owner, 'application', data):
                notify('Application added.')
    if apps:
        c1, c2, c3 = st.columns(3)
        query = c1.text_input('Search company / role')
        statuses = c2.multiselect('Filter status', store.STATUSES)
        loc = c3.text_input('Location filter')
        due_only = st.checkbox('Only applications with upcoming or overdue actions')
        rows = [{'id': r['id'], **r['data']} for r in apps if query.lower() in (r['data']['company']+' '+r['data']['role']).lower()
                and (not statuses or r['data']['status'] in statuses) and loc.lower() in r['data'].get('location','').lower()
                and (not due_only or reminders([r]))]
        if rows:
            df = pd.DataFrame(rows).reindex(columns=['id', 'company', 'role', 'location', 'status', 'match', 'applied_on', 'deadline', 'follow_up', 'notes'])
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.download_button('Export applications CSV', safe_csv(rows), 'applications.csv', 'text/csv')
            selected = st.selectbox('Edit application', rows, format_func=lambda r: f"#{r['id']} · {r['company']} — {r['role']}")
            prefix = f"application_{selected['id']}_"
            with st.form(prefix):
                data = job_form(prefix, selected)
                data['status'] = st.selectbox('Application status', store.STATUSES, index=store.STATUSES.index(selected['status']))
                data['notes'] = st.text_area('Application notes', selected.get('notes', ''))
                a, b = st.columns(2)
                applied = a.date_input('Applied on', date.fromisoformat(selected['applied_on']) if selected.get('applied_on') else None)
                follow = b.date_input('Follow-up date', date.fromisoformat(selected['follow_up']) if selected.get('follow_up') else None)
                data.update(applied_on=applied.isoformat() if applied else '', follow_up=follow.isoformat() if follow else '', match=selected.get('match', 0))
                update = st.form_submit_button('Save changes')
            if update:
                if parsed and data.get('description'):
                    data['match'] = match(text, data['description']).score
                if attempt(store.save, owner, 'application', data, selected['id']):
                    notify('Application updated.')
            if st.checkbox('Confirm application deletion') and st.button('Delete application'):
                store.remove(owner, 'application', selected['id'])
                notify('Application deleted.')
        else:
            st.info('No applications match the filters.')

elif page == 'Recruiter':
    st.title('Compare candidates')
    st.caption('Rank up to 20 uploaded resumes against one JD. Use as a review aid; never as an automatic hiring decision.')
    target = st.text_area('Recruiter job description', jd, height=180)
    uploads = st.file_uploader('Candidate resumes', type=['pdf', 'docx', 'txt'], accept_multiple_files=True)
    if st.button('Rank candidates', type='primary'):
        if not target.strip() or not uploads:
            st.error('Add a job description and at least one resume.')
        elif len(uploads) > 20:
            st.error('Upload at most 20 resumes.')
        else:
            rows = []
            for upload in uploads:
                try:
                    candidate = extract_text(upload.getvalue(), upload.name)
                    if not candidate.strip():
                        st.warning(f'{upload.name}: no readable text. Skipped.')
                        continue
                    result = match(candidate, target)
                    rows.append({'file': upload.name, 'score': result.score, 'matched_skills': ', '.join(result.matched_skills), 'gaps': ', '.join(result.missing_skills)})
                except Exception:
                    st.warning(f'{upload.name}: could not read this file. Skipped.')
            st.session_state['ranked_candidates'] = sorted(rows, key=lambda r: -r['score'])
            st.session_state['ranked_context'] = hashlib.sha256((target + str([(u.name, hashlib.sha256(u.getvalue()).hexdigest()) for u in uploads])).encode()).hexdigest()
    current_context = hashlib.sha256((target + str([(u.name, hashlib.sha256(u.getvalue()).hexdigest()) for u in uploads])).encode()).hexdigest()
    rows = st.session_state.get('ranked_candidates')
    if rows and st.session_state.get('ranked_context') == current_context:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.download_button('Export ranking', safe_csv(rows), 'candidate_ranking.csv', 'text/csv')

elif page == 'Settings':
    st.title('Workspace settings')
    st.subheader('Job preferences')
    prefs = store.list_records(owner, 'preferences')
    old = prefs[0]['data'] if prefs else {}
    with st.form('preferences'):
        roles = st.text_input('Target roles', old.get('roles', ''))
        locations = st.text_input('Preferred locations', old.get('locations', ''))
        notes = st.text_area('Search goals', old.get('notes', ''))
        if st.form_submit_button('Save preferences'):
            store.save(owner, 'preferences', {'roles': roles, 'locations': locations, 'notes': notes}, prefs[0]['id'] if prefs else None)
            st.success('Preferences saved for your reference. Use matching filters in Job library.')
    st.subheader('Backup and restore')
    st.download_button('Download account backup', json.dumps(store.export_account(owner), indent=2), 'resume_studio_backup.json', 'application/json')
    backup = st.file_uploader('Restore a backup', type=['json'])
    confirmed = st.checkbox('Import as additional records (existing records are kept; duplicates are possible)')
    if st.button('Import backup', disabled=not (backup and confirmed)):
        if backup.size > 10 * 1024 * 1024:
            st.error('Backup must be smaller than 10 MB.')
        else:
            try:
                count = store.import_account(owner, json.loads(backup.getvalue()))
                notify(f'Imported {count} records.')
            except (ValueError, KeyError, TypeError, AttributeError):
                st.error('Invalid backup. Nothing was imported.')
    st.subheader('Change password')
    with st.form('change_password'):
        old_pass = st.text_input('Current password', type='password')
        new_pass = st.text_input('New password', type='password')
        confirm_pass = st.text_input('Confirm new password', type='password')
        if st.form_submit_button('Update password'):
            if new_pass != confirm_pass:
                st.error('Passwords do not match.')
            else:
                try:
                    store.change_password(owner, old_pass, new_pass)
                    st.success('Password changed.')
                except ValueError as exc:
                    st.error(str(exc))
    st.caption('Data stays in the local SQLite database. Backups include your resume and job data, but never your password or API key. Reminders appear in this app; no background emails are sent.')
