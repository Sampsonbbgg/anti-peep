import os
import tempfile
import unittest

import numpy as np

from moyu.core.owner_store import OwnerStore


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


class OwnerStoreTests(unittest.TestCase):
    def test_match_owner_and_stranger(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "owner_faces.json")
            store = OwnerStore(path, threshold=0.363)
            a = _unit([1, 0, 0, 0])
            store.add(a)
            store.save()

            store2 = OwnerStore(path, threshold=0.363)
            store2.load()
            self.assertEqual(1, store2.count)

            near = _unit([0.99, 0.01, 0, 0])
            far = _unit([0, 1, 0, 0])
            is_owner, sim = store2.match(near)
            self.assertTrue(is_owner)
            self.assertGreater(sim, 0.36)
            self.assertFalse(store2.match(far)[0])

    def test_empty_store_never_matches(self):
        with tempfile.TemporaryDirectory() as d:
            store = OwnerStore(os.path.join(d, "o.json"))
            self.assertTrue(store.is_empty)
            self.assertEqual((False, 0.0), store.match(_unit([1, 0])))


if __name__ == "__main__":
    unittest.main()
