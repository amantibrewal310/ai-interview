# Implementation Plan: Collections API (Python / Flask)

Scope: the Collections task in [`PROBLEM.md`](../../PROBLEM.md). Schema details are in [`DB_SCHEMA.md`](./DB_SCHEMA.md). This plan covers only the APIs and the steps to build them.

## 1. Endpoints

Existing bookmark endpoints keep their routes. Their queries gain an `is_deleted = 0` filter, and `DELETE` becomes a soft delete.

| Method | Route | Purpose | Success | Errors |
|---|---|---|---|---|
| POST | `/collections` | Create collection | `201` | `400` invalid name, `409` active name exists |
| GET | `/collections` | List active collections | `200` | |
| GET | `/collections/<id>` | Get one | `200` | `404` |
| PUT | `/collections/<id>` | Rename | `200` | `400`, `404`, `409` |
| DELETE | `/collections/<id>` | Soft delete collection and its memberships | `204` | `404` |
| GET | `/collections/<id>/bookmarks` | List bookmarks in position order | `200` | `404` |
| POST | `/collections/<id>/bookmarks` | Add bookmark `{"bookmark_id": n}` | `201` | `400`, `404`, `409` active membership exists |
| DELETE | `/collections/<id>/bookmarks/<bookmark_id>` | Remove bookmark (soft) | `204` | `404` (see rule below) |
| PUT | `/collections/<id>/bookmarks/<bookmark_id>/position` | Set position `{"position": n}` | `200` | `400`, `404` |

**Rules**

- Name: trimmed, at least 3 characters, unique among active collections (case-insensitive).
- `position`: integer greater than 0. No upper bound, no renumbering.
- Add: `position` = max active position in the collection + 1, or 1 if empty.
- List order: `position` ascending, then `bookmark_id` ascending.
- `404` on membership routes distinguishes the missing part: collection missing or deleted, bookmark missing or deleted, or not in the collection.
- Re-adding a removed bookmark reuses its membership row and gets a new position.

## 2. Steps

1. **Resolve open decisions** in `DB_SCHEMA.md` §2.9. Default assumptions: restore is out of scope, and memberships are not restored with their parents.
2. **Database setup** (`db.py`, `schema.sql`):
   - Add `is_deleted` to `bookmarks` through a guarded `ALTER TABLE`, run in `init_db()`.
   - Add the `collections` and `collection_bookmarks` tables, both partial and regular indexes from §2.5.
   - Add a `transaction()` helper using `BEGIN IMMEDIATE`, and close connections.
3. **Bookmark changes** (`models.py`, `routes.py`):
   - Filter `is_deleted = 0` in list, get, and update.
   - Change delete to a transactional soft delete that also marks active memberships deleted.
4. **Collection model functions** (`models.py`): create, list, get, rename, soft delete (with memberships), in that order.
5. **Membership model functions**: add (handles re-add and `409`), remove, list ordered, set position.
6. **Routes** (`routes.py`): one `validate_collection` and one `validate_position` helper, following the existing `validate_bookmark` style. Return `jsonify(error=...)` on failure, as the existing code does.
7. **Tests**: use a temporary `DB_PATH`. Cover the cases below.
8. **Manual check**: run `python app.py` and confirm existing bookmark endpoints behave as before.

## 3. Test cases

- Bookmark in two collections; each collection keeps its own order.
- Move to position 1, to a large value, and to a value already taken (tie ordered by `bookmark_id`).
- `position` of `0`, `-1`, or a non-integer returns `400`.
- Name: `"ab"` returns `400`. `"  Reading  "` is stored as `"Reading"`. `"reading"` when `"Reading"` is active returns `409`.
- Adding an active bookmark twice returns `409`. Remove then re-add succeeds.
- Soft-deleted bookmark: `404` on its routes, absent from collection lists.
- Soft-deleted collection: `404` on its routes, its name can be reused.
- Deleting a bookmark or collection leaves the other side intact.
- Existing bookmark CRUD still passes.

## 4. Out of scope

- Restore endpoints.
- Collection descriptions.
- Purging soft-deleted rows.
- Authentication and pagination.
