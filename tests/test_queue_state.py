import unittest
from app.models import MediaItem
from app.queue_state import queue_action, ready_to_shutdown


class QueueStateTests(unittest.TestCase):
    def item(self, status, busy=False):
        return MediaItem('https://youtu.be/demo', status=status, busy=busy)

    def test_action_hidden_before_download(self):
        self.assertEqual(queue_action([self.item('Ready')]), (None, False))

    def test_stop_transitions_to_resume(self):
        self.assertEqual(queue_action([self.item('Downloading', True)]), ('Stop all', True))
        self.assertEqual(queue_action([self.item('Stopping...', True)]), ('Stop all', False))
        self.assertEqual(queue_action([self.item('Stopped')]), ('Resume all', True))
        self.assertEqual(queue_action([self.item('Completed')]), (None, False))

    def test_mixed_queue(self):
        self.assertEqual(queue_action([self.item('Stopped'), self.item('Queued', True)]), ('Stop all', True))

    def test_shutdown_only_on_success(self):
        for status in ['Failed', 'Cancelled', 'Stopped', 'Not started']:
            self.assertFalse(ready_to_shutdown([], {'a': 'Completed', 'b': status}))
        self.assertFalse(ready_to_shutdown([], {}))
        self.assertTrue(ready_to_shutdown([self.item('Completed')], {'a': 'Completed'}))

    def test_shutdown_waits_for_pending_or_stopped(self):
        results = {'a': 'Completed'}
        self.assertFalse(ready_to_shutdown([], results, pending=1))
        self.assertFalse(ready_to_shutdown([], results, dispatches=1))
        self.assertFalse(ready_to_shutdown([self.item('Queued', True)], results))
        self.assertFalse(ready_to_shutdown([self.item('Stopped')], results))

    def test_shutdown_after_resume(self):
        results = {'a': 'Completed', 'b': 'Stopped'}
        self.assertFalse(ready_to_shutdown([], results))
        results['b'] = 'Completed'
        self.assertTrue(ready_to_shutdown([], results))
