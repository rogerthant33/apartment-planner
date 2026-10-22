"""The .apartment format: a ZIP holding project.json and assets/. See docs/SPEC.md §8."""

import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from apartment_planner.model.project import CURRENT_SCHEMA_VERSION, ProjectDoc
from apartment_planner.persistence.errors import (
    InvalidProjectError,
    NewerVersionError,
    NotAProjectError,
)
from apartment_planner.persistence.migrations import migrate

FORMAT = "apartment-planner"
PROJECT_JSON = "project.json"
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

# Fixed timestamp so identical projects produce identical bytes.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ProjectFile:
    doc: ProjectDoc
    assets: dict[str, bytes] = field(default_factory=dict)  # asset_id -> file bytes


def asset_path(asset_id: str, mime_type: str) -> str:
    return f"assets/{asset_id}.{EXTENSIONS[mime_type]}"


def _referenced_assets(doc: ProjectDoc) -> dict[str, str]:
    """asset_id -> archive path for every asset the document uses."""
    if doc.background is None:
        return {}
    bg = doc.background
    return {bg.asset_id: asset_path(bg.asset_id, bg.mime_type)}


def encode(project: ProjectFile) -> bytes:
    payload = {
        "format": FORMAT,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project": project.doc.model_dump(mode="json"),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo(PROJECT_JSON, _ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, text.encode("utf-8"))
        for asset_id, path in sorted(_referenced_assets(project.doc).items()):
            info = zipfile.ZipInfo(path, _ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED  # images are already compressed
            archive.writestr(info, project.assets[asset_id])
    return buffer.getvalue()


def decode(data: bytes) -> ProjectFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        payload = json.loads(archive.read(PROJECT_JSON).decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NotAProjectError() from error

    with archive:
        if not isinstance(payload, dict) or payload.get("format") != FORMAT:
            raise NotAProjectError()
        doc = _load_doc(payload)
        assets: dict[str, bytes] = {}
        for asset_id, path in _referenced_assets(doc).items():
            try:
                assets[asset_id] = archive.read(path)
            except KeyError as error:
                raise InvalidProjectError([f"missing image file {path}"]) from error
    return ProjectFile(doc, assets)


def _load_doc(payload: dict[str, Any]) -> ProjectDoc:
    version = payload.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise InvalidProjectError([f"schema_version {version!r} is not a format version"])
    if version > CURRENT_SCHEMA_VERSION:
        raise NewerVersionError(version)
    project = payload.get("project")
    if not isinstance(project, dict):
        raise InvalidProjectError(["project is missing"])
    try:
        return ProjectDoc.model_validate(migrate(project, version))
    except ValidationError as error:
        raise InvalidProjectError([_describe(e) for e in error.errors()]) from error


def _describe(error: Any) -> str:
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}" if where else str(error["msg"])
