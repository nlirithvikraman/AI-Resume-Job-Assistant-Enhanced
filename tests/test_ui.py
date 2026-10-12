from pathlib import Path
from streamlit.testing.v1 import AppTest
from src import store

APP = Path(__file__).resolve().parents[1] / 'app.py'


def click_label(at, label):
    next(button for button in at.button if button.label == label).click().run()
    assert not at.exception


def test_account_flow_and_all_screens(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'ui.db')
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not at.exception
    at.text_input[2].set_value('tester')
    at.text_input[3].set_value('sample-password')
    at.text_input[4].set_value('sample-password')
    click_label(at, 'Create account')
    at.text_input[0].set_value('tester')
    at.text_input[1].set_value('sample-password')
    click_label(at, 'Sign in')
    click_label(at, 'Use demo resume')
    for page in ['Resume workspace','Job match','Job library','AI studio','Applications','Recruiter','Settings','Dashboard']:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page
    at.sidebar.radio[0].set_value('Resume workspace').run()
    click_label(at, 'Save new version')
    assert len(store.list_records(at.session_state['user']['id'], 'resume')) == 1
    click_label(at, 'Sign out')
    assert not at.exception
    assert 'user' not in at.session_state


def test_job_and_application_editing(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'ui.db')
    uid = store.register('tester', 'sample-password')
    store.save(uid, 'job', {'company':'Example','role':'Python Dev','description':'Python SQL','location':'Remote','url':'','deadline':'','salary':''})
    at = AppTest.from_file(str(APP), default_timeout=20)
    at.session_state['user'] = {'id':uid, 'username':'tester'}
    at.session_state['resume_text'] = 'Sample Person\nSkills\nPython SQL'
    at.run()
    at.sidebar.radio[0].set_value('Job library').run()
    assert not at.exception
    click_label(at, 'Add to applications')
    assert len(store.list_records(uid, 'application')) == 1
    at.sidebar.radio[0].set_value('Applications').run()
    assert not at.exception
    next(x for x in at.selectbox if x.label == 'Application status').set_value('Interview')
    click_label(at, 'Save changes')
    assert store.list_records(uid, 'application')[0]['data']['status'] == 'Interview'
    at.sidebar.radio[0].set_value('Dashboard').run()
    assert not at.exception
