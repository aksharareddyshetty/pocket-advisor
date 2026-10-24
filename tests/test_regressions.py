"""Behavioral regressions. No accounts, network, or state in the real HOME."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import enrollment_rules
import plan_schedule
import visa_check
import watch


def cli(script, *args):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts' / script), *args],
                          capture_output=True, text=True, cwd=ROOT)


def output(fn, **args):
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        fn(SimpleNamespace(**args))
    return text.getvalue()


def section(code, **extra):
    result = dict(course=code, credits=3, mode='in_person', satisfies=['core'],
                  days='M', start=f'{8 + sum(map(ord, code)) % 12:02d}:00',
                  end=f'{9 + sum(map(ord, code)) % 12:02d}:00')
    result.update(extra)
    return result


class FilingTests(unittest.TestCase):
    def opt(self, today, *args):
        result = cli('visa_check.py', 'opt-window', '--program-end', '2027-05-08', '--today', today, '--json', *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_school_open_does_not_open_uscis(self):
        r = self.opt('2027-02-01')
        self.assertEqual(r['school_request_status'], 'open')
        self.assertEqual(r['uscis_filing_status'], 'too_early')
        self.assertEqual(r['status'], 'too_early')

    def test_first_uscis_day(self):
        self.assertEqual(self.opt('2027-02-07')['status'], 'open')

    def test_missing_recommendation_has_no_personal_deadline(self):
        r = self.opt('2027-02-20')
        self.assertIsNone(r['uscis_last_day'])
        self.assertFalse(r['deadline_complete'])

    def test_recommendation_makes_deadline_earlier(self):
        r = self.opt('2027-03-01', '--opt-i20-date', '2027-02-07')
        self.assertEqual(r['uscis_last_day'], '2027-03-09')
        self.assertEqual(r['general_uscis_last_day'], '2027-07-07')

    def test_recommendation_deadline_inclusive(self):
        self.assertEqual(self.opt('2027-03-09', '--opt-i20-date', '2027-02-07')['status'], 'open')
        self.assertEqual(self.opt('2027-03-10', '--opt-i20-date', '2027-02-07')['status'], 'closed')

    def test_outer_deadline_wins(self):
        r = self.opt('2027-07-01', '--opt-i20-date', '2027-06-30')
        self.assertEqual(r['uscis_last_day'], '2027-07-07')

    def test_future_recommendation_rejected(self):
        r = cli('visa_check.py', 'opt-window', '--program-end', '2027-05-08', '--today', '2027-02-20', '--opt-i20-date', '2027-03-01')
        self.assertEqual(r.returncode, 2)

    def test_stem_school_open_is_not_filing_open(self):
        r = cli('visa_check.py', 'stem-window', '--opt-end', '2028-06-30', '--today', '2028-03-25', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'too_early')
        self.assertEqual(data['school_request_status'], 'open')
        self.assertIsNone(data['uscis_last_day'])

    def test_stem_recommendation_deadline(self):
        r = cli('visa_check.py', 'stem-window', '--opt-end', '2028-06-30', '--today', '2028-04-10', '--stem-i20-date', '2028-04-01', '--json')
        self.assertEqual(json.loads(r.stdout)['uscis_last_day'], '2028-05-31')

    def test_stem_school_status_independent_of_old_recommendation(self):
        r = cli('visa_check.py', 'stem-window', '--opt-end', '2028-06-30', '--today', '2028-06-10', '--stem-i20-date', '2028-04-01', '--json')
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'closed')
        self.assertEqual(data['school_request_status'], 'open')


class EnrollmentTests(unittest.TestCase):
    def check(self, courses, **extra):
        return enrollment_rules.assess(courses, 12, 9, 3, **extra)

    def test_unknown_mode_is_not_in_person(self):
        r = self.check([{'course': 'A', 'credits': 12}])
        self.assertIsNone(r['full_time'])
        self.assertEqual(r['in_person'], 0)

    def test_missing_session_dates_is_provisional(self):
        r = self.check([section('A', start_date='2027-01-01', end_date='2027-05-01'), section('B'), section('C'), section('D')])
        self.assertIsNone(r['full_time'])

    def test_full_term_confirmed(self):
        courses = [section(c, start_date='2027-01-01', end_date='2027-05-01') for c in 'ABCD']
        r = self.check(courses, term_start='2027-01-01', term_end='2027-05-01')
        self.assertTrue(r['full_time'])

    def test_short_session_is_not_certified_from_totals(self):
        courses = [section(c, start_date='2027-01-01', end_date='2027-03-01') for c in 'ABCD']
        r = self.check(courses, term_start='2027-01-01', term_end='2027-05-01')
        self.assertIsNone(r['full_time'])
        self.assertIn('short-session', ' '.join(r['needs_information']))

    def test_below_minimum_remains_a_failure(self):
        self.assertFalse(self.check([section('A')])['full_time'])

    def test_online_extra_does_not_replace_in_person(self):
        courses = [section('A'), {'course': 'B', 'credits': 12, 'mode': 'online'}]
        self.assertFalse(self.check(courses)['full_time'])

    def test_invalid_term_dates_rejected(self):
        with self.assertRaises(ValueError):
            self.check([section('A')], term_start='2027-05-01', term_end='2027-01-01')

    def test_drop_unknown_data_is_provisional(self):
        with patch.object(visa_check, 'load_json', return_value=[{'course': 'A', 'credits': 12}, {'course': 'B', 'credits': 3}]):
            r = json.loads(output(visa_check.enrollment, sample=False, courses='unused', level='undergrad', min_credits=None,
                                 min_in_person=9, max_online_credits=3, drop='B', term_start=None, term_end=None, json=True))
        self.assertIsNone(r['after_drop']['full_time'])


class HoursTests(unittest.TestCase):
    def hours(self, shifts):
        with patch.object(visa_check, 'load_json', return_value=shifts):
            return json.loads(output(visa_check.hours, sample=False, shifts='unused', breaks=None, limit=20, break_limit=40, json=True))

    def test_overnight_shift_split_across_weeks(self):
        r = self.hours([dict(job='desk', start='2026-10-25T23:00', end='2026-10-26T03:00')])
        self.assertEqual([x['hours'] for x in r['weeks']], [1, 3])

    def test_cross_week_hours_can_reveal_overage(self):
        r = self.hours([dict(job='desk', start='2026-10-25T23:00', end='2026-10-26T03:00'),
                        dict(job='lab', start='2026-10-27T00:00', end='2026-10-27T18:00')])
        self.assertTrue(r['any_over'])
        self.assertEqual(r['weeks'][1]['over_by'], 1)

    def test_exact_boundary_no_empty_week(self):
        r = self.hours([dict(start='2026-10-25T23:00', end='2026-10-26T00:00')])
        self.assertEqual(len(r['weeks']), 1)
        self.assertEqual(r['weeks'][0]['hours'], 1)

    def test_mixed_timezone_input_rejected_cleanly(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.hours([dict(start='2026-10-25T23:00', end='2026-10-26T03:00+00:00')])
        self.assertEqual(caught.exception.code, 2)


class PlannerTests(unittest.TestCase):
    def plan(self, sections, **extra):
        return plan_schedule.plan(dict(credit_cap=6, requirements=[dict(id='core', courses_needed=2)], sections=sections, **extra), 3)

    def test_missing_required_course_fails(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.plan([section('OPTIONAL')], must_take=['REQUIRED'])
        self.assertEqual(caught.exception.code, 3)

    def test_required_conflict_fails(self):
        sections = [section(c, days='MW', start='09:00', end='10:00') for c in ['A', 'B']]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.plan(sections, must_take=['A', 'B'])
        self.assertEqual(caught.exception.code, 3)

    def test_every_plan_includes_required_course(self):
        result = self.plan([section('A'), section('B'), section('C')], must_take=['A'])
        self.assertTrue(result['plans'])
        for plan in result['plans']:
            self.assertIn('A', [c['course'] for c in plan['classes']])

    def test_visa_plan_missing_dates_is_provisional(self):
        r = self.plan([section('A'), section('B')], min_credits=6, min_in_person=6, max_online_credits=3)
        self.assertIsNone(r['plans'][0]['enrollment_check']['full_time'])

    def test_visa_plan_missing_mode_requests_information(self):
        course = section('A')
        del course['mode']
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.plan([course], min_credits=3, min_in_person=3, max_online_credits=3)
        self.assertEqual(caught.exception.code, 2)

    def test_known_full_term_plan_verified(self):
        sections = [section(c, start_date='2027-01-01', end_date='2027-05-01') for c in 'AB']
        r = self.plan(sections, min_credits=6, min_in_person=6, max_online_credits=3, term_start='2027-01-01', term_end='2027-05-01')
        self.assertTrue(r['plans'][0]['enrollment_check']['full_time'])

    def test_sample_still_plans_classes(self):
        r = cli('plan_schedule.py', '--sample', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)['plans'])


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.patcher = patch.object(watch, 'STATE', self.state)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temp.cleanup)
        self.url = 'https://example.edu/policy'
        self.snapshots = self.state / 'snapshots'

    def compare(self, text):
        return watch.compare(self.snapshots, 'Policy', self.url, text)

    def test_change_not_lost_on_failed_review(self):
        self.compare('<p>Old policy text</p>')
        first = self.compare('<p>New policy text</p>')
        retry = self.compare('<p>New policy text</p>')
        self.assertEqual(first['status'], 'changed')
        self.assertEqual(first, retry)

    def test_full_diff_includes_late_important_change(self):
        self.compare('<p>Old policy text</p>')
        text = ''.join(f'<p>New policy item {i}</p>' for i in range(30)) + '<p>Important filing deadline changed</p>'
        r = self.compare(text)
        self.assertIn('Important filing deadline changed', r['added'])
        self.assertEqual(len(r['added']), 31)

    def test_ack_advances_baseline(self):
        self.compare('<p>Old policy text</p>')
        r = self.compare('<p>New policy text</p>')
        output(watch.ack, url=self.url, revision=r['revision'])
        self.assertEqual(self.compare('<p>New policy text</p>')['status'], 'unchanged')

    def test_stale_ack_is_rejected(self):
        self.compare('<p>Old policy text</p>')
        first = self.compare('<p>New policy text</p>')
        self.compare('<p>Newer policy text</p>')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            output(watch.ack, url=self.url, revision=first['revision'])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.compare('<p>Newer policy text</p>')['status'], 'changed')

    def test_empty_page_does_not_replace_baseline(self):
        self.compare('<p>Old policy text</p>')
        with self.assertRaises(ValueError):
            self.compare('<script>empty</script>')
        self.assertEqual(self.compare('<p>Old policy text</p>')['status'], 'unchanged')

    def test_reverted_page_cannot_ack_obsolete_change(self):
        self.compare('<p>Old policy text</p>')
        changed = self.compare('<p>New policy text</p>')
        self.compare('<p>Old policy text</p>')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            output(watch.ack, url=self.url, revision=changed['revision'])
        self.assertEqual(caught.exception.code, 2)

    def test_short_numeric_policy_cells_are_not_discarded(self):
        self.compare('<p>Weekly limit</p><table><tr><td>20</td></tr></table>')
        r = self.compare('<p>Weekly limit</p><table><tr><td>40</td></tr></table>')
        self.assertIn('40', r['added'])
        self.assertIn('20', r['removed'])

    def test_policy_update_dates_are_not_discarded(self):
        self.compare('<p>Updated: January 1, 2026</p>')
        self.assertEqual(self.compare('<p>Updated: February 1, 2026</p>')['status'], 'changed')

    def test_failed_fetch_keeps_unreviewed_change_pending(self):
        self.compare('<p>Old policy text</p>')
        self.compare('<p>New policy text</p>')
        with patch.object(watch, 'load_watchlist', return_value=[{'url': self.url}]), patch.object(watch, 'fetch', side_effect=OSError('unavailable')):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
                watch.rules(SimpleNamespace(sample=False, watchlist='unused', json=True))
        self.assertEqual(caught.exception.code, 4)
        self.assertEqual(self.compare('<p>New policy text</p>')['status'], 'changed')

    def test_seen_check_does_not_mark_handled(self):
        output(watch.seen, kind='email', id='offer', mark=False)
        output(watch.seen, kind='email', id='offer', mark=False)
        self.assertEqual(json.loads(output(watch.pending_items, kind='email')), ['offer'])
        self.assertFalse((self.state / 'seen.json').exists())

    def test_mark_handled_removes_pending_and_skips_next_check(self):
        output(watch.seen, kind='email', id='offer', mark=False)
        output(watch.seen, kind='email', id='offer', mark=True)
        self.assertEqual(json.loads(output(watch.pending_items, kind='email')), [])
        with self.assertRaises(SystemExit) as caught:
            output(watch.seen, kind='email', id='offer', mark=False)
        self.assertEqual(caught.exception.code, 1)

    def test_pending_items_survive_between_runs(self):
        output(watch.seen, kind='email', id='old-offer', mark=False)
        self.assertEqual(json.loads((self.state / 'pending-items.json').read_text())['email'].keys(), {'old-offer'})


class SampleTests(unittest.TestCase):
    def test_visa_samples(self):
        for command in ['opt-window', 'stem-window', 'unemployment', 'hours', 'enrollment', 'travel']:
            with self.subTest(command=command):
                r = cli('visa_check.py', command, '--sample', '--json')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIsInstance(json.loads(r.stdout), dict)

    def test_watch_sample(self):
        r = cli('watch.py', 'rules', '--sample', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['pages'][0]['status'], 'changed')

    def test_clips_sample(self):
        r = cli('clips.py', '--sample', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)['moments'])


if __name__ == '__main__':
    unittest.main()
