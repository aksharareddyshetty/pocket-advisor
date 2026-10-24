"""Regressions for combined OPT hours, meeting completeness, sessions and travel dates."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan_schedule as planner
import visa_check as visa


class UnemploymentTests(unittest.TestCase):
    def count(self, jobs, stem=False):
        args = SimpleNamespace(sample=False, jobs='memory', ead_start='2027-06-15',
                               today='2027-06-24', stem=stem, prior_days=0, json=True)
        result = io.StringIO()
        with patch.object(visa, 'load_json', return_value=jobs), contextlib.redirect_stdout(result):
            visa.unemployment(args)
        return json.loads(result.getvalue())

    def job(self, hours, start='2027-06-15', end=None, **extra):
        return dict(employer='A', hours_per_week=hours, start=start, end=end, **extra)

    def test_two_ten_hour_concurrent_jobs_count_regular_opt(self):
        r = self.count([self.job(10), self.job(10)])
        self.assertEqual(r['used'], 0)
        self.assertEqual(len(r['jobs_counted']), 2)

    def test_only_overlap_counts_as_employed(self):
        r = self.count([self.job(10), self.job(10, start='2027-06-20')])
        self.assertEqual(r['used'], 5)

    def test_sequential_part_time_jobs_do_not_combine(self):
        r = self.count([self.job(10, end='2027-06-19'), self.job(10, start='2027-06-20')])
        self.assertEqual(r['used'], 10)

    def test_stem_does_not_combine_two_ten_hour_jobs(self):
        self.assertEqual(self.count([self.job(10), self.job(10)], stem=True)['used'], 10)

    def test_stem_qualifying_twenty_hour_job_still_counts(self):
        self.assertEqual(self.count([self.job(20), self.job(10)], stem=True)['used'], 0)

    def test_nonqualifying_role_is_excluded(self):
        self.assertEqual(self.count([self.job(10), self.job(10, qualifying=False)])['used'], 10)

    def test_future_job_does_not_count(self):
        self.assertEqual(self.count([self.job(20, start='2027-07-01')])['used'], 10)

    def test_reversed_job_dates_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            self.count([self.job(20, start='2027-06-20', end='2027-06-19')])
        self.assertEqual(exc.exception.code, 2)


class MeetingTests(unittest.TestCase):
    def section(self, code, **extra):
        s = dict(course=code, credits=3, mode='in_person', days='M', start='09:00', end='10:00')
        s.update(extra)
        return s

    def plan(self, sections, **extra):
        return planner.plan(dict(credit_cap=12, sections=sections, must_take=[s['course'] for s in sections], **extra), 1)

    def rejected(self, sections, code, **extra):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            self.plan(sections, **extra)
        self.assertEqual(exc.exception.code, code)

    def test_in_person_missing_days_requires_clarification(self):
        self.rejected([self.section('A', days=None)], 2)

    def test_missing_clock_time_requires_clarification(self):
        self.rejected([self.section('A', start=None)], 2)

    def test_sync_without_time_requires_clarification(self):
        self.rejected([self.section('A', mode='sync', days='')], 2)

    def test_online_without_explicit_async_requires_clarification(self):
        self.rejected([self.section('A', mode='icourse', days='', start=None, end=None)], 2)

    def test_explicit_async_accepts_no_meetings(self):
        r = self.plan([self.section('A', mode='icourse', asynchronous=True, days='', start=None, end=None)])
        self.assertIn('confirmed asynchronous', r['plans'][0]['classes'][0]['when'])

    def test_in_person_cannot_claim_async(self):
        self.rejected([self.section('A', asynchronous=True, days=None, start=None, end=None)], 2)

    def multi(self):
        return dict(course='A', credits=4, mode='in_person', meetings=[
            dict(days='M', start='09:00', end='10:00'), dict(days='F', start='14:00', end='16:00')])

    def test_lab_conflict_with_busy_time_rejected(self):
        self.rejected([self.multi()], 3, avoid_times=[dict(days='F', start='15:00', end='17:00')])

    def test_lab_conflict_with_other_course_rejected(self):
        self.rejected([self.multi(), self.section('B', days='F', start='15:00', end='17:00')], 3)

    def test_all_meetings_appear_in_output(self):
        r = self.plan([self.multi()])
        when = r['plans'][0]['classes'][0]['when']
        self.assertIn('M 09:00-10:00', when)
        self.assertIn('F 14:00-16:00', when)

    def test_nonoverlapping_sessions_can_share_weekday_and_time(self):
        r = self.plan([self.section('A', start_date='2027-01-01', end_date='2027-02-28'),
                       self.section('B', start_date='2027-03-01', end_date='2027-05-01')])
        self.assertEqual(len(r['plans'][0]['classes']), 2)

    def test_overlapping_session_weekday_rejected(self):
        self.rejected([self.section('A', start_date='2027-01-01', end_date='2027-03-31'),
                       self.section('B', start_date='2027-03-01', end_date='2027-05-01')], 3)

    def test_adjacent_clock_times_allowed(self):
        self.assertTrue(self.plan([self.section('A'), self.section('B', start='10:00', end='11:00')])['plans'])

    def test_session_overlap_without_shared_weekday_is_allowed(self):
        # Shared date range is Sat-Sun, so the Monday meetings never coincide.
        self.assertTrue(self.plan([self.section('A', start_date='2027-01-01', end_date='2027-01-03'),
                                  self.section('B', start_date='2027-01-02', end_date='2027-02-01')])['plans'])

    def test_missing_session_dates_conservatively_conflict(self):
        self.rejected([self.section('A'), self.section('B')], 3)

    def test_dated_busy_block_outside_session_does_not_conflict(self):
        self.assertTrue(self.plan([self.section('A', start_date='2027-03-01', end_date='2027-05-01')],
            avoid_times=[dict(days='M', start='09:00', end='10:00', start_date='2027-01-01', end_date='2027-02-01')])['plans'])

    def test_mixed_top_level_and_meetings_rejected(self):
        self.rejected([self.section('A', meetings=[dict(days='F', start='10:00', end='11:00')])], 2)

    def test_reversed_session_rejected(self):
        self.rejected([self.section('A', start_date='2027-05-01', end_date='2027-01-01')], 2)


class TravelTests(unittest.TestCase):
    def run_travel(self, signed, ret, today='2026-10-24'):
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'visa_check.py'
        return subprocess.run([sys.executable, '-B', str(path), 'travel', '--signed', signed,
                               '--return-date', ret, '--today', today, '--json'], capture_output=True, text=True)

    def test_future_signature_rejected(self):
        r = self.run_travel('2027-02-01', '2027-03-01')
        self.assertEqual(r.returncode, 2)
        self.assertIn('future', r.stderr)
        self.assertEqual(r.stdout, '')

    def test_signature_after_return_rejected(self):
        r = self.run_travel('2026-10-01', '2026-09-01')
        self.assertEqual(r.returncode, 2)
        self.assertIn('return date', r.stderr)

    def test_same_day_signature_allowed(self):
        r = self.run_travel('2026-10-24', '2026-10-24')
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)['valid_on_return'])

    def test_expired_signature_is_not_valid(self):
        r = self.run_travel('2025-01-01', '2027-01-01')
        self.assertEqual(r.returncode, 0)
        self.assertFalse(json.loads(r.stdout)['valid_on_return'])


if __name__ == '__main__':
    unittest.main()
