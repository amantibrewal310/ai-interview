"""API tests for bookmarks and collections.

Run from python/bookmarks with:  python -m unittest test_api -v
Uses only the standard library, so no new dependency is needed.
"""

import os
import tempfile
import unittest

# Point the app at a throwaway database before importing it,
# so importing app.py (which calls init_db()) never touches bookmarks.db.
_fd, _tmp_db = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DB_PATH"] = _tmp_db

import db  # noqa: E402
from app import app  # noqa: E402


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        # Fresh database for every test.
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)
        db.DB_PATH = path
        db.init_db()
        self.client = app.test_client()

    def make_bookmark(self, title="Example"):
        res = self.client.post(
            "/bookmarks", json={"url": "https://example.com", "title": title}
        )
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]

    def make_collection(self, name="Reading list"):
        res = self.client.post("/collections", json={"name": name})
        self.assertEqual(res.status_code, 201)
        return res.get_json()["id"]


class BookmarkRegressionTests(ApiTestCase):
    def test_bookmark_crud_still_works(self):
        bid = self.make_bookmark("First")

        self.assertEqual(self.client.get(f"/bookmarks/{bid}").status_code, 200)
        res = self.client.put(
            f"/bookmarks/{bid}", json={"url": "https://a.dev", "title": "Renamed"}
        )
        self.assertEqual(res.get_json()["title"], "Renamed")
        self.assertEqual(len(self.client.get("/bookmarks").get_json()), 1)

        self.assertEqual(self.client.delete(f"/bookmarks/{bid}").status_code, 204)
        self.assertEqual(self.client.get(f"/bookmarks/{bid}").status_code, 404)
        self.assertEqual(self.client.get("/bookmarks").get_json(), [])


class CollectionTests(ApiTestCase):
    def test_create_trims_name(self):
        res = self.client.post("/collections", json={"name": "  Recipes  "})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["name"], "Recipes")

    def test_name_shorter_than_three_characters_is_rejected(self):
        res = self.client.post("/collections", json={"name": "  ab "})
        self.assertEqual(res.status_code, 400)

    def test_duplicate_active_name_is_case_insensitive_conflict(self):
        self.make_collection("Reading list")
        res = self.client.post("/collections", json={"name": "READING LIST"})
        self.assertEqual(res.status_code, 409)

    def test_name_is_reusable_after_soft_delete(self):
        cid = self.make_collection("Reading list")
        self.assertEqual(self.client.delete(f"/collections/{cid}").status_code, 204)

        self.assertEqual(self.client.get(f"/collections/{cid}").status_code, 404)
        res = self.client.post("/collections", json={"name": "Reading list"})
        self.assertEqual(res.status_code, 201)


class MembershipTests(ApiTestCase):
    def test_add_twice_is_conflict(self):
        cid, bid = self.make_collection(), self.make_bookmark()
        url = f"/collections/{cid}/bookmarks"
        self.assertEqual(self.client.post(url, json={"bookmark_id": bid}).status_code, 201)
        self.assertEqual(self.client.post(url, json={"bookmark_id": bid}).status_code, 409)

    def test_list_is_ordered_by_position_then_bookmark_id(self):
        cid = self.make_collection()
        first, second, third = (self.make_bookmark(t) for t in ("A", "B", "C"))
        for bid in (first, second, third):
            self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": bid})

        # Move the last one to position 1, which is already taken by `first`.
        # Ties are broken by bookmark_id, so `first` (lower id) stays ahead of it.
        self.client.put(
            f"/collections/{cid}/bookmarks/{third}/position", json={"position": 1}
        )
        ids = [b["id"] for b in self.client.get(f"/collections/{cid}/bookmarks").get_json()]
        self.assertEqual(ids, [first, third, second])

    def test_invalid_position_is_rejected(self):
        cid, bid = self.make_collection(), self.make_bookmark()
        self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": bid})
        url = f"/collections/{cid}/bookmarks/{bid}/position"

        for bad in (0, -1, "2", 1.5, None):
            with self.subTest(position=bad):
                self.assertEqual(
                    self.client.put(url, json={"position": bad}).status_code, 400
                )

    def test_remove_then_readd_goes_to_end(self):
        cid = self.make_collection()
        a, b = self.make_bookmark("A"), self.make_bookmark("B")
        self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": a})
        self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": b})

        url = f"/collections/{cid}/bookmarks/{a}"
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 404)  # no longer a member

        self.assertEqual(
            self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": a}).status_code,
            201,
        )
        ids = [x["id"] for x in self.client.get(f"/collections/{cid}/bookmarks").get_json()]
        self.assertEqual(ids, [b, a])

    def test_membership_routes_reject_deleted_parents(self):
        cid, bid = self.make_collection(), self.make_bookmark()
        self.client.delete(f"/bookmarks/{bid}")
        self.assertEqual(
            self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": bid}).status_code,
            404,
        )

        cid2, bid2 = self.make_collection("Recipes"), self.make_bookmark("Other")
        self.client.delete(f"/collections/{cid2}")
        self.assertEqual(
            self.client.post(f"/collections/{cid2}/bookmarks", json={"bookmark_id": bid2}).status_code,
            404,
        )


class SoftDeleteCascadeTests(ApiTestCase):
    def test_deleting_bookmark_removes_it_from_all_collections_only(self):
        c1, c2 = self.make_collection("Reading list"), self.make_collection("Recipes")
        gone, kept = self.make_bookmark("Gone"), self.make_bookmark("Kept")
        for cid in (c1, c2):
            self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": gone})
            self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": kept})

        self.assertEqual(self.client.delete(f"/bookmarks/{gone}").status_code, 204)

        for cid in (c1, c2):
            ids = [x["id"] for x in self.client.get(f"/collections/{cid}/bookmarks").get_json()]
            self.assertEqual(ids, [kept])

    def test_deleting_collection_keeps_its_bookmarks(self):
        cid, bid = self.make_collection(), self.make_bookmark()
        self.client.post(f"/collections/{cid}/bookmarks", json={"bookmark_id": bid})

        self.assertEqual(self.client.delete(f"/collections/{cid}").status_code, 204)

        self.assertEqual(self.client.get(f"/bookmarks/{bid}").status_code, 200)
        self.assertEqual(self.client.get(f"/collections/{cid}/bookmarks").status_code, 404)


if __name__ == "__main__":
    unittest.main()
