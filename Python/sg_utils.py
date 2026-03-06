#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility functions for ShotGrid dependency tracking.

This module contains helper functions for date formatting, path parsing,
entity type extraction, and other common operations.
"""

import datetime as dt
import os
import re
from typing import Optional, List, Dict

from models import PathInfo, PublishRef, VersionRef


SG_VERSION_FIELDS = [
    "code", "created_at", "user", "sg_status_list", "entity", "project",
    "sg_department", "sg_step", "version_number", "sg_client_name", "tank_published_file",
    "sg_uploaded_movie", "sg_path_to_frames", "sg_path", "sg_path_to_movie", "description"
]

SG_PUB_FIELDS = [
    "id", "code", "name", "version_number", "published_file_type",
    "path", "created_at", "created_by", "sg_version", "tank_type",
    "upstream_tank_published_files", "downstream_tank_published_files",
    "description", "sg_status_list",
    "entity", "project", "sg_metadata", "tags",
    "entity.Shot.sg_sequence", "entity.Shot.code",
    "entity.Asset.code", "project.Project.code",
    "sg_version.Version.sg_path_to_movie"
]

# ShotGrid base URL for generating links
SG_BASE_URL = "https://rodeofx.shotgrid.autodesk.com"


def buildShotgridUrl(entityType, entityId):
    """
    Build a ShotGrid URL for an entity.

    Args:
        entityType: Entity type (e.g., "TankPublishedFile", "Version", "Shot")
        entityId: Entity ID

    Returns:
        Full ShotGrid URL string
    """
    if not entityType or not entityId:
        return None
    return f"{SG_BASE_URL}/detail/{entityType}/{entityId}"


def buildMediaCenterUrl(projectId, versionId):
    """
    Build a ShotGrid media center URL for a Version.

    Args:
        projectId: Project entity ID
        versionId: Version entity ID

    Returns:
        Full ShotGrid media center URL string
    """
    if not projectId or not versionId:
        return None
    return f"{SG_BASE_URL}/page/media_center?project_id={projectId}&type=Version&id={versionId}"


def buildContextString(pub):
    """
    Build a rich context string from publish data.

    Format: "Project · EntityName (EntityType)"

    Args:
        pub: ShotGrid publish entity dictionary

    Returns:
        Context string
    """
    parts = []

    # Project
    project = pub.get("project")
    if project:
        projectName = project.get("name") or pub.get("project.Project.code") or ""
        if projectName:
            parts.append(projectName)

    # Entity (Shot or Asset)
    entity = pub.get("entity")
    if entity:
        entityType = entity.get("type", "")
        entityName = entity.get("name") or ""

        # Try to get sequence for shots
        if entityType == "Shot":
            sequence = pub.get("entity.Shot.sg_sequence")
            if sequence and sequence.get("name"):
                entityName = f"{sequence.get('name')} / {entityName}"

        if entityName:
            parts.append(f"{entityName} ({entityType})")

    return " · ".join(parts) if parts else ""

TYPE_COLOR = {
    "render": 34,
    "camera": 36,
    "usdLayerStack": 35,
    "usdManifest": 35,
    "usdPayloadPackage": 35,
    "textureBundle2": 33,
    "groom": 33,
    "workfile": 90,
    "workfileChunk": 90,
    "plate": 32,
    "lensDistortion": 32,
    "precomp": 31,
}


def formatDatetime(dateValue):
    """
    Format a datetime value to a readable string.

    Args:
        dateValue: datetime object, ISO string, or None

    Returns:
        Formatted date string (YYYY-MM-DD HH:MM) or "Unknown"
    """
    if not dateValue:
        return "Unknown"
    if isinstance(dateValue, dt.datetime):
        return dateValue.strftime("%Y-%m-%d %H:%M")
    try:
        return dt.datetime.fromisoformat(str(dateValue).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dateValue)


def createdDatetime(value):
    """
    Convert a value to a datetime object.

    Args:
        value: datetime object, ISO string, or other value

    Returns:
        datetime object or None if conversion fails
    """
    if isinstance(value, dt.datetime):
        return value
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def parseDate(dateString):
    """
    Parse a date string in various formats.

    Args:
        dateString: Date string to parse

    Returns:
        datetime object

    Raises:
        ValueError: If date string cannot be parsed
    """
    if not dateString:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(dateString, fmt)
        except Exception:
            pass
    try:
        return dt.datetime.fromisoformat(dateString.replace("Z", "+00:00"))
    except Exception:
        raise ValueError(f"Could not parse date: {dateString!r}")


def datetimeString(dateValue: Optional[dt.datetime]) -> str:
    """
    Convert datetime to formatted string.

    Args:
        dateValue: datetime object or None

    Returns:
        Formatted string or empty string
    """
    return dateValue.strftime("%Y-%m-%d %H:%M") if dateValue else ""


def getPubTypeName(pub):
    """
    Extract the type name from a publish entity.

    Args:
        pub: ShotGrid publish entity dictionary

    Returns:
        Type name string or "Unknown"
    """
    tankTypeName = (pub.get("tank_type") or {}).get("name") or ""
    return tankTypeName or (pub.get("published_file_type") or {}).get("name") or "Unknown"


def getIdFromLink(linkValue):
    """
    Extract ID from a ShotGrid link value.

    Args:
        linkValue: Dictionary with 'id' key, integer, or other value

    Returns:
        Integer ID or None
    """
    if isinstance(linkValue, dict):
        return linkValue.get("id")
    if isinstance(linkValue, int):
        return linkValue
    return None


def normalizePath(pathString: Optional[str]) -> Optional[str]:
    """
    Normalize a file path.

    Args:
        pathString: Path string to normalize

    Returns:
        Normalized path or None
    """
    if not pathString:
        return None
    return os.path.normpath(pathString)


def pathParts(path: str) -> PathInfo:
    """
    Parse a file path into structured components.

    Extracts information like show name, sequence, shot, department, version
    from Rodeo FX pipeline path structure.

    Args:
        path: File path string to parse

    Returns:
        PathInfo object with parsed components
    """
    rawPath = path
    cleanPath = normalizePath(path) or path
    parts = {
        "root": "",
        "show": "",
        "sequence": "",
        "shot": "",
        "department": "",
        "wip_or_pub": "",
        "asset": "",
        "version": "",
        "filename": os.path.basename(cleanPath),
        "ext": os.path.splitext(cleanPath)[1]
    }

    segments = cleanPath.split(os.sep)
    try:
        rdo_idx = segments.index("rdo")
    except ValueError:
        rdo_idx = None

    if rdo_idx is not None and len(segments) > rdo_idx + 2 and segments[rdo_idx + 1] == "shows":
        parts["root"] = os.sep.join(segments[: rdo_idx + 1])
        parts["show"] = segments[rdo_idx + 2]

    if ".published" in segments:
        pubIdx = segments.index(".published")
        if len(segments) > pubIdx + 2:
            parts["sequence"] = segments[pubIdx + 1]
            parts["shot"] = segments[pubIdx + 2]
        parts["wip_or_pub"] = "published"
    else:
        parts["wip_or_pub"] = "wip"

    filename = parts["filename"]
    tokens = filename.split(".")
    if len(tokens) >= 2:
        parts["department"] = tokens[0]

    versionMatch = re.search(r"/v(\d{2,3})(?=/|$)", cleanPath)
    if versionMatch:
        parts["version"] = f"v{versionMatch.group(1)}"
    else:
        versionMatch2 = re.search(r"_v(\d{2,3})(?=\.)", filename)
        if versionMatch2:
            parts["version"] = f"v{versionMatch2.group(1)}"

    return PathInfo(raw=rawPath, clean=cleanPath, parts=parts)


def categorizePublish(pub: PublishRef) -> str:
    """
    Categorize a publish for display purposes.

    Args:
        pub: PublishRef object

    Returns:
        Category string (e.g., "Quicktime movie", "Precomp scene")
    """
    tankType = pub.tankType or ""
    publishedType = pub.publishedFileType or ""
    name = pub.name or ""

    if "mov" in name.lower() or "quicktime" in tankType.lower():
        return "Quicktime movie"

    if ".nk" in name or "nuke" in tankType.lower():
        return "Precomp scene"

    if "#" in name or "%04d" in name or name.endswith((".exr", ".dpx", ".jpg", ".png")):
        return "Frames (EXR seq)"

    if "workfile" in tankType.lower() or any(ext in name for ext in [".hip", ".ma", ".mb", ".hda"]):
        return "Source Work File"

    return f"Asset ({tankType})"


def extractAllPathsFromPublish(pubData):
    """
    Extract all file paths from a publish's path and metadata fields.

    Args:
        pubData: ShotGrid publish entity dictionary

    Returns:
        List of path strings
    """
    paths = []

    if pubData.get("path"):
        if isinstance(pubData["path"], dict):
            for key in ["local_path", "linux_path", "mac_path", "windows_path"]:
                if pubData["path"].get(key):
                    paths.append(pubData["path"][key])
        else:
            paths.append(pubData["path"])

    for field in ["metadata", "description", "sg_path", "sg_path_to_movie", "sg_path_to_frames"]:
        if pubData.get(field):
            value = pubData[field]
            if isinstance(value, str):
                unixPaths = re.findall(r'(/[^\s"\'<]+)', value)
                paths.extend(unixPaths)
            elif isinstance(value, dict):
                for key in ["local_path", "linux_path", "mac_path", "windows_path"]:
                    if value.get(key):
                        paths.append(value[key])

    return [pathStr for pathStr in paths if pathStr and not pathStr.startswith("S:")]


def synthesizeFilename(pathInfo, pubData):
    """
    Synthesize a filename if we only have a version directory.

    Args:
        pathInfo: PathInfo object
        pubData: ShotGrid publish entity dictionary

    Returns:
        Tuple of (filename, full_path) or None
    """
    folder = pathInfo.clean
    if not folder:
        return None

    verMatch = re.search(r'/v(\d+)$', folder)
    if not verMatch:
        filename = pathInfo.parts.get("filename", "")
        if filename and any(filename.endswith(ext) for ext in [".hip", ".ma", ".mb", ".nk", ".hda"]):
            return filename, folder
        return None

    versionNum = verMatch.group(1)

    appHint = "houdini"
    if "houdini" in folder.lower():
        appHint = "houdini"
    elif "maya" in folder.lower():
        appHint = "maya"
    elif "nuke" in folder.lower():
        appHint = "nuke"

    parentFolder = folder[:verMatch.start()]
    baseName = parentFolder.split("/")[-1]

    extMap = {"houdini": ".hip", "maya": ".ma", "nuke": ".nk"}
    ext = extMap.get(appHint, ".hip")

    syntheticName = f"{baseName}_v{versionNum}{ext}"
    syntheticPath = f"{folder}/{syntheticName}"

    return syntheticName, syntheticPath


def ansiColor(text, color=None, enable=False):
    """
    Apply ANSI color codes to text.

    Args:
        text: Text to colorize
        color: ANSI color code (integer)
        enable: Whether to apply color

    Returns:
        Colorized or plain text string
    """
    if not enable or not color:
        return text
    return f"\x1b[{color}m{text}\x1b[0m"


def normalizeListArg(value):
    """
    Normalize a comma-separated string to a set.

    Args:
        value: Comma-separated string or None

    Returns:
        Set of strings or None
    """
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return set(parts) if parts else None


def expandLinks(values):
    """
    Expand a list of ShotGrid link values to IDs.

    Args:
        values: List of link dictionaries or integers

    Returns:
        List of integer IDs
    """
    out = []
    if not values:
        return out
    for item in values:
        itemId = getIdFromLink(item)
        if itemId:
            out.append(itemId)
    return out


def createPublishRef(pubData) -> PublishRef:
    """
    Convert ShotGrid publish data to PublishRef object.

    Args:
        pubData: ShotGrid publish entity dictionary

    Returns:
        PublishRef object
    """
    pathInfo = None
    if pubData.get("path"):
        if isinstance(pubData["path"], dict):
            pathInfo = pubData["path"].get("local_path")
        else:
            pathInfo = pubData["path"]

    return PublishRef(
        id=pubData["id"],
        code=pubData.get("code", ""),
        createdAt=datetimeString(createdDatetime(pubData.get("created_at"))),
        path=normalizePath(pathInfo),
        name=pubData.get("name", ""),
        versionNumber=pubData.get("version_number"),
        tankType=(pubData.get("tank_type") or {}).get("name") if pubData.get("tank_type") else None,
        publishedFileType=(pubData.get("published_file_type") or {}).get("name") if pubData.get("published_file_type") else None,
        createdBy=pubData.get("created_by"),
        upstreamIds=expandLinks(pubData.get("upstream_tank_published_files")),
        downstreamIds=expandLinks(pubData.get("downstream_tank_published_files"))
    )


def createVersionRef(versionData) -> VersionRef:
    """
    Convert ShotGrid version data to VersionRef object.

    Args:
        versionData: ShotGrid version entity dictionary

    Returns:
        VersionRef object
    """
    return VersionRef(
        id=versionData["id"],
        code=versionData.get("code", ""),
        createdAt=datetimeString(createdDatetime(versionData.get("created_at"))),
        user=versionData.get("user"),
        entity=versionData.get("entity"),
        project=versionData.get("project"),
        department=versionData.get("sg_department"),
        moviePath=versionData.get("sg_path_to_movie"),
        framesPath=versionData.get("sg_path_to_frames")
    )
