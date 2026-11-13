import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from unittest.mock import Mock, patch

import requests
import catalog


def response(status=200, payload=None, retry_after=None):
    result = requests.Response()
    result.status_code = status
    result.url = catalog.API
    result._content = json.dumps(payload if payload is not None else {'query': {}}).encode()
    result._content_consumed = True
    if retry_after is not None:
        result.headers['Retry-After'] = retry_after
    return result


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.0
        self.waits = []
        self.session = Mock()
        self.saved_cooldown = catalog._next_request
        catalog._next_request = 0
        self.monotonic = patch('catalog.time.monotonic', side_effect=lambda: self.clock)
        self.sleep = patch('catalog.time.sleep', side_effect=self.advance)
        self.monotonic.start()
        self.sleep.start()
        self.addCleanup(self.monotonic.stop)
        self.addCleanup(self.sleep.stop)
        self.addCleanup(setattr, catalog, '_next_request', self.saved_cooldown)
        self.previous = getattr(catalog._local, 'session', None)
        catalog._local.session = self.session
        self.addCleanup(self.restore_session)

    def restore_session(self):
        if self.previous is None:
            del catalog._local.session
        else:
            catalog._local.session = self.previous

    def advance(self, seconds):
        self.waits.append(seconds)
        self.clock += seconds

    def test_numeric_retry_after_then_success_retains_maxlag_and_query(self):
        self.session.get.side_effect = [response(429, retry_after='7'), response(payload={'query': {'ok': True}})]
        self.assertTrue(catalog.wiki_query({'action': 'query', 'maxlag': 0})['query']['ok'])
        self.assertEqual(self.waits, [7])
        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(self.session.get.call_args.kwargs['params']['maxlag'], 5)

    def test_http_date_and_invalid_header_use_defined_delays(self):
        with patch('catalog.time.time', return_value=1000):
            self.assertEqual(catalog.retry_delay(formatdate(1012, usegmt=True), 0), 12)
            self.assertEqual(catalog.retry_delay('invalid', 1), 4)
            self.assertEqual(catalog.retry_delay(formatdate(990, usegmt=True), 0), 0)

    def test_long_cooldown_fails_without_early_retry_and_applies_to_next_call(self):
        self.session.get.return_value = response(429, retry_after='3600')
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, 'previous snapshot retained'):
                catalog.wiki_query({'action': 'query'})
        self.assertEqual(self.session.get.call_count, 1)
        self.assertEqual(self.waits, [])

    def test_exhausted_429_raises_instead_of_fabricating_success(self):
        self.session.get.side_effect = [response(429) for _ in range(3)]
        with self.assertRaises(requests.HTTPError):
            catalog.wiki_query({'action': 'query'})
        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(self.waits, [2, 4])

    def test_maxlag_payload_retries_but_permanent_api_error_does_not(self):
        self.session.get.side_effect = [response(payload={'error': {'code': 'maxlag', 'info': 'busy'}}, retry_after='3'), response()]
        self.assertEqual(catalog.wiki_query({}), {'query': {}})
        self.assertEqual(self.waits, [3])
        self.session.get.reset_mock()
        self.session.get.side_effect = None
        self.session.get.return_value = response(payload={'error': {'code': 'badvalue', 'info': 'invalid parameter'}})
        with self.assertRaisesRegex(ValueError, 'invalid parameter'):
            catalog.wiki_query({})
        self.assertEqual(self.session.get.call_count, 1)

    def test_403_is_not_retried(self):
        self.session.get.return_value = response(403)
        with self.assertRaises(requests.HTTPError):
            catalog.wiki_query({})
        self.assertEqual(self.session.get.call_count, 1)

    def test_connection_failures_use_bounded_exponential_retries(self):
        self.session.get.side_effect = [requests.Timeout(), requests.ConnectionError(), response()]
        self.assertEqual(catalog.wiki_query({}), {'query': {}})
        self.assertEqual(self.waits, [2, 4])
        self.assertEqual(self.session.get.call_count, 3)

    def test_total_budget_prevents_late_retry(self):
        def slow_response(*args, **kwargs):
            self.clock += catalog.REQUEST_BUDGET - 1
            return response(429, retry_after='2')
        self.session.get.side_effect = slow_response
        with self.assertRaisesRegex(RuntimeError, 'request budget'):
            catalog.wiki_query({})
        self.assertEqual(self.session.get.call_count, 1)
        self.assertEqual(self.waits, [])

    def test_parallel_workers_never_overlap_actual_http_calls(self):
        active = 0
        maximum = 0
        guard = threading.Lock()
        def get(*args, **kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            threading.Event().wait(0.01)
            with guard:
                active -= 1
            return response()
        def worker(_):
            catalog._local.session = Mock(get=get)
            return catalog.wiki_query({})
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(worker, range(3))), [{'query': {}}] * 3)
        self.assertEqual(maximum, 1)


if __name__ == '__main__':
    unittest.main()
