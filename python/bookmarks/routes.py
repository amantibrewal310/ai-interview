from flask import Blueprint, jsonify, request

import models

bp = Blueprint("bookmarks", __name__)


def validate_bookmark(data):
    if not isinstance(data, dict):
        return "body must be a JSON object"
    for field in ("url", "title"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return f"{field} is required"
    if not isinstance(data.get("description", ""), str):
        return "description must be a string"
    return None


def validate_collection(data):
    if not isinstance(data, dict):
        return "body must be a JSON object"
    name = data.get("name")
    if not isinstance(name, str) or len(name.strip()) < 3:
        return "name is required and must be at least 3 characters"
    return None


def _is_positive_int(value):
    # bool is a subclass of int in Python, so exclude it explicitly.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_position(data):
    if not isinstance(data, dict):
        return "body must be a JSON object"
    if not _is_positive_int(data.get("position")):
        return "position must be an integer greater than 0"
    return None


def validate_membership(data):
    if not isinstance(data, dict):
        return "body must be a JSON object"
    if not _is_positive_int(data.get("bookmark_id")):
        return "bookmark_id must be an integer greater than 0"
    return None


@bp.errorhandler(models.NotFoundError)
def handle_not_found(err):
    return jsonify(error=str(err)), 404


@bp.errorhandler(models.ConflictError)
def handle_conflict(err):
    return jsonify(error=str(err)), 409


# ----------------------------------------------------------------- bookmarks


@bp.get("/bookmarks")
def list_bookmarks():
    return jsonify(models.list_bookmarks())


@bp.get("/bookmarks/<int:bookmark_id>")
def get_bookmark(bookmark_id):
    bookmark = models.get_bookmark(bookmark_id)
    if bookmark is None:
        return jsonify(error="bookmark not found"), 404
    return jsonify(bookmark)


@bp.post("/bookmarks")
def create_bookmark():
    data = request.get_json(silent=True)
    error = validate_bookmark(data)
    if error:
        return jsonify(error=error), 400
    bookmark = models.create_bookmark(
        data["url"].strip(), data["title"].strip(), data.get("description", "")
    )
    return jsonify(bookmark), 201


@bp.put("/bookmarks/<int:bookmark_id>")
def update_bookmark(bookmark_id):
    data = request.get_json(silent=True)
    error = validate_bookmark(data)
    if error:
        return jsonify(error=error), 400
    bookmark = models.update_bookmark(
        bookmark_id, data["url"].strip(), data["title"].strip(), data.get("description", "")
    )
    if bookmark is None:
        return jsonify(error="bookmark not found"), 404
    return jsonify(bookmark)


@bp.delete("/bookmarks/<int:bookmark_id>")
def delete_bookmark(bookmark_id):
    if not models.delete_bookmark(bookmark_id):
        return jsonify(error="bookmark not found"), 404
    return "", 204


# --------------------------------------------------------------- collections


@bp.get("/collections")
def list_collections():
    return jsonify(models.list_collections())


@bp.get("/collections/<int:collection_id>")
def get_collection(collection_id):
    collection = models.get_collection(collection_id)
    if collection is None:
        return jsonify(error="collection not found"), 404
    return jsonify(collection)


@bp.post("/collections")
def create_collection():
    data = request.get_json(silent=True)
    error = validate_collection(data)
    if error:
        return jsonify(error=error), 400
    return jsonify(models.create_collection(data["name"].strip())), 201


@bp.put("/collections/<int:collection_id>")
def rename_collection(collection_id):
    data = request.get_json(silent=True)
    error = validate_collection(data)
    if error:
        return jsonify(error=error), 400
    return jsonify(models.rename_collection(collection_id, data["name"].strip()))


@bp.delete("/collections/<int:collection_id>")
def delete_collection(collection_id):
    if not models.delete_collection(collection_id):
        return jsonify(error="collection not found"), 404
    return "", 204


@bp.get("/collections/<int:collection_id>/bookmarks")
def list_collection_bookmarks(collection_id):
    return jsonify(models.list_collection_bookmarks(collection_id))


@bp.post("/collections/<int:collection_id>/bookmarks")
def add_bookmark_to_collection(collection_id):
    data = request.get_json(silent=True)
    error = validate_membership(data)
    if error:
        return jsonify(error=error), 400
    membership = models.add_bookmark_to_collection(collection_id, data["bookmark_id"])
    return jsonify(membership), 201


@bp.delete("/collections/<int:collection_id>/bookmarks/<int:bookmark_id>")
def remove_bookmark_from_collection(collection_id, bookmark_id):
    models.remove_bookmark_from_collection(collection_id, bookmark_id)
    return "", 204


@bp.put("/collections/<int:collection_id>/bookmarks/<int:bookmark_id>/position")
def set_position(collection_id, bookmark_id):
    data = request.get_json(silent=True)
    error = validate_position(data)
    if error:
        return jsonify(error=error), 400
    return jsonify(models.set_position(collection_id, bookmark_id, data["position"]))
