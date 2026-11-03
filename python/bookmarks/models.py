from db import connect, transaction


class NotFoundError(Exception):
    """A requested resource (or part of a membership route) is missing or soft deleted."""


class ConflictError(Exception):
    """The request clashes with an active row, such as a duplicate name or membership."""


BOOKMARK_COLUMNS = "id, url, title, description, created_at"
COLLECTION_COLUMNS = "id, name, created_at"


# ---------------------------------------------------------------- bookmarks


def list_bookmarks():
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {BOOKMARK_COLUMNS} FROM bookmarks WHERE is_deleted = 0 ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_bookmark(bookmark_id):
    with connect() as conn:
        row = conn.execute(
            f"SELECT {BOOKMARK_COLUMNS} FROM bookmarks WHERE id = ? AND is_deleted = 0",
            (bookmark_id,),
        ).fetchone()
    return dict(row) if row else None


def create_bookmark(url, title, description=""):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO bookmarks (url, title, description) VALUES (?, ?, ?)",
            (url, title, description),
        )
        bookmark_id = cur.lastrowid
    return get_bookmark(bookmark_id)


def update_bookmark(bookmark_id, url, title, description):
    with connect() as conn:
        cur = conn.execute(
            "UPDATE bookmarks SET url = ?, title = ?, description = ? "
            "WHERE id = ? AND is_deleted = 0",
            (url, title, description, bookmark_id),
        )
        if cur.rowcount == 0:
            return None
    return get_bookmark(bookmark_id)


def delete_bookmark(bookmark_id):
    """Soft delete the bookmark and its active memberships. Returns False if not active."""
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE bookmarks SET is_deleted = 1 WHERE id = ? AND is_deleted = 0",
            (bookmark_id,),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "UPDATE collection_bookmarks SET is_deleted = 1 "
            "WHERE bookmark_id = ? AND is_deleted = 0",
            (bookmark_id,),
        )
    return True


# -------------------------------------------------------------- collections


def _name_taken(conn, name, exclude_id=None):
    row = conn.execute(
        "SELECT id FROM collections WHERE name = ? COLLATE NOCASE AND is_deleted = 0 AND id != ?",
        (name, exclude_id if exclude_id is not None else -1),
    ).fetchone()
    return row is not None


def list_collections():
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {COLLECTION_COLUMNS} FROM collections WHERE is_deleted = 0 ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_collection(collection_id):
    with connect() as conn:
        row = conn.execute(
            f"SELECT {COLLECTION_COLUMNS} FROM collections WHERE id = ? AND is_deleted = 0",
            (collection_id,),
        ).fetchone()
    return dict(row) if row else None


def create_collection(name):
    with transaction() as conn:
        if _name_taken(conn, name):
            raise ConflictError("a collection with this name already exists")
        cur = conn.execute("INSERT INTO collections (name) VALUES (?)", (name,))
        collection_id = cur.lastrowid
    return get_collection(collection_id)


def rename_collection(collection_id, name):
    with transaction() as conn:
        exists = conn.execute(
            "SELECT id FROM collections WHERE id = ? AND is_deleted = 0", (collection_id,)
        ).fetchone()
        if exists is None:
            raise NotFoundError("collection not found")
        if _name_taken(conn, name, exclude_id=collection_id):
            raise ConflictError("a collection with this name already exists")
        conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))
    return get_collection(collection_id)


def delete_collection(collection_id):
    """Soft delete the collection and its active memberships. Bookmarks are untouched."""
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE collections SET is_deleted = 1 WHERE id = ? AND is_deleted = 0",
            (collection_id,),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "UPDATE collection_bookmarks SET is_deleted = 1 "
            "WHERE collection_id = ? AND is_deleted = 0",
            (collection_id,),
        )
    return True


# -------------------------------------------------------------- memberships


def _require_collection_and_bookmark(conn, collection_id, bookmark_id):
    """Raise NotFoundError naming the missing part. Both must be active."""
    if conn.execute(
        "SELECT 1 FROM collections WHERE id = ? AND is_deleted = 0", (collection_id,)
    ).fetchone() is None:
        raise NotFoundError("collection not found")
    if conn.execute(
        "SELECT 1 FROM bookmarks WHERE id = ? AND is_deleted = 0", (bookmark_id,)
    ).fetchone() is None:
        raise NotFoundError("bookmark not found")


def _membership(conn, collection_id, bookmark_id):
    row = conn.execute(
        "SELECT collection_id, bookmark_id, position, added_at FROM collection_bookmarks "
        "WHERE collection_id = ? AND bookmark_id = ? AND is_deleted = 0",
        (collection_id, bookmark_id),
    ).fetchone()
    return dict(row) if row else None


def add_bookmark_to_collection(collection_id, bookmark_id):
    with transaction() as conn:
        _require_collection_and_bookmark(conn, collection_id, bookmark_id)
        existing = conn.execute(
            "SELECT is_deleted FROM collection_bookmarks "
            "WHERE collection_id = ? AND bookmark_id = ?",
            (collection_id, bookmark_id),
        ).fetchone()
        if existing is not None and existing["is_deleted"] == 0:
            raise ConflictError("bookmark is already in this collection")

        next_position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM collection_bookmarks "
            "WHERE collection_id = ? AND is_deleted = 0",
            (collection_id,),
        ).fetchone()[0]

        if existing is None:
            conn.execute(
                "INSERT INTO collection_bookmarks (collection_id, bookmark_id, position) "
                "VALUES (?, ?, ?)",
                (collection_id, bookmark_id, next_position),
            )
        else:
            # Re-add: reuse the removed row and give it a new position at the end.
            conn.execute(
                "UPDATE collection_bookmarks SET is_deleted = 0, position = ?, "
                "added_at = CURRENT_TIMESTAMP WHERE collection_id = ? AND bookmark_id = ?",
                (next_position, collection_id, bookmark_id),
            )
        return _membership(conn, collection_id, bookmark_id)


def remove_bookmark_from_collection(collection_id, bookmark_id):
    with transaction() as conn:
        _require_collection_and_bookmark(conn, collection_id, bookmark_id)
        cur = conn.execute(
            "UPDATE collection_bookmarks SET is_deleted = 1 "
            "WHERE collection_id = ? AND bookmark_id = ? AND is_deleted = 0",
            (collection_id, bookmark_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError("bookmark is not in this collection")


def list_collection_bookmarks(collection_id):
    with connect() as conn:
        if conn.execute(
            "SELECT 1 FROM collections WHERE id = ? AND is_deleted = 0", (collection_id,)
        ).fetchone() is None:
            raise NotFoundError("collection not found")
        rows = conn.execute(
            "SELECT b.id, b.url, b.title, b.description, b.created_at, cb.position "
            "FROM collection_bookmarks cb "
            "JOIN bookmarks b ON b.id = cb.bookmark_id "
            "WHERE cb.collection_id = ? AND cb.is_deleted = 0 AND b.is_deleted = 0 "
            "ORDER BY cb.position, cb.bookmark_id",
            (collection_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_position(collection_id, bookmark_id, position):
    with transaction() as conn:
        _require_collection_and_bookmark(conn, collection_id, bookmark_id)
        cur = conn.execute(
            "UPDATE collection_bookmarks SET position = ? "
            "WHERE collection_id = ? AND bookmark_id = ? AND is_deleted = 0",
            (position, collection_id, bookmark_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError("bookmark is not in this collection")
        return _membership(conn, collection_id, bookmark_id)
