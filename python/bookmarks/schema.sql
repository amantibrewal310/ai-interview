CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1))
);

CREATE TABLE IF NOT EXISTS collections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL CHECK (length(trim(name)) >= 3),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1))
);

-- Name is unique among active collections, case-insensitive.
CREATE UNIQUE INDEX IF NOT EXISTS idx_collections_name_active
    ON collections (name COLLATE NOCASE)
    WHERE is_deleted = 0;

CREATE TABLE IF NOT EXISTS collection_bookmarks (
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    bookmark_id   INTEGER NOT NULL REFERENCES bookmarks(id),
    position      INTEGER NOT NULL CHECK (position > 0),
    added_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted    INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    PRIMARY KEY (collection_id, bookmark_id)
);

-- Ordered listing of a collection, active rows only
CREATE INDEX IF NOT EXISTS idx_collection_bookmarks_order
    ON collection_bookmarks (collection_id, position)
    WHERE is_deleted = 0;

-- Reverse lookup: which collections contain this bookmark
CREATE INDEX IF NOT EXISTS idx_collection_bookmarks_bookmark
    ON collection_bookmarks (bookmark_id);
