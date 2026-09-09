"""Exercise real shared-connection writes while a checkpoint is suspended."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import unittest
from unittest.mock import patch

from orchestration import continuity
from orchestration.store import Store


class StoreSerializationTests(unittest.TestCase):
    def test_mutation_cannot_join_and_commit_checkpoint_transaction(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.create_mission("a", "Fixture", "workspace")
        store.transition("a", "PAUSED")
        source = store.context_source_digest("a")
        context = dict(constraints=[], decisions=[], open_questions=[], next_action="Check results")
        encoding_entered = threading.Event()
        release_encoding = threading.Event()
        mutation_started = threading.Event()
        original = continuity.envelope

        def suspended_encoding(*args, **kwargs):
            encoding_entered.set()
            if not release_encoding.wait(5):
                raise AssertionError("test did not release checkpoint")
            return original(*args, **kwargs)

        def mutate():
            mutation_started.set()
            store.set_iteration("a", 1)

        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(continuity, "envelope", suspended_encoding):
            writer = pool.submit(store.save_context_checkpoint, "cp", "a", context, expected_source_digest=source)
            try:
                self.assertTrue(encoding_entered.wait(3))
                mutation = pool.submit(mutate)
                self.assertTrue(mutation_started.wait(3))
                with self.assertRaises(TimeoutError, msg="another Store write committed inside checkpoint transaction"):
                    mutation.result(timeout=0.2)
            finally:
                release_encoding.set()
            writer.result(timeout=3)
            mutation.result(timeout=3)
        self.assertEqual(store.get_mission("a")["iteration"], 1)
        self.assertFalse(store.load_context_checkpoint("cp", "a")["source_current"])


if __name__ == "__main__":
    unittest.main()
