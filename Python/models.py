#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data models for ShotGrid dependency tracking.

This module contains dataclass definitions for representing ShotGrid entities
including path information, publish references, and version references.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PathInfo:
    """
    Represents parsed file path information.

    Attributes:
        raw: Original unprocessed path string
        clean: Normalized path string
        parts: Dictionary containing parsed path components (root, show, sequence, etc.)
    """
    raw: str
    clean: str
    parts: Dict[str, str] = field(default_factory=dict)


@dataclass
class PublishRef:
    """
    Reference to a ShotGrid TankPublishedFile entity.

    Attributes:
        id: ShotGrid entity ID
        code: Entity code/name
        createdAt: Creation timestamp as formatted string
        path: File system path to the published file
        name: Display name of the publish
        versionNumber: Version number of the publish
        tankType: Tank type name (e.g., 'render', 'camera')
        publishedFileType: Published file type name
        createdBy: Dictionary containing creator user information
        upstreamIds: List of upstream dependency IDs
        downstreamIds: List of downstream dependency IDs
    """
    id: int
    code: str
    createdAt: str
    path: Optional[str] = None
    name: Optional[str] = None
    versionNumber: Optional[int] = None
    tankType: Optional[str] = None
    publishedFileType: Optional[str] = None
    createdBy: Optional[dict] = None
    upstreamIds: List[int] = field(default_factory=list)
    downstreamIds: List[int] = field(default_factory=list)


@dataclass
class VersionRef:
    """
    Reference to a ShotGrid Version entity.

    Attributes:
        id: ShotGrid entity ID
        code: Version code/name
        createdAt: Creation timestamp as formatted string
        user: Dictionary containing user information
        entity: Dictionary containing linked entity (Shot/Asset)
        project: Dictionary containing project information
        department: Department name (e.g., 'comp', 'lighting')
        moviePath: Path to uploaded movie/quicktime
        framesPath: Path to frame sequence
    """
    id: int
    code: str
    createdAt: str
    user: Optional[dict] = None
    entity: Optional[dict] = None
    project: Optional[dict] = None
    department: Optional[str] = None
    moviePath: Optional[str] = None
    framesPath: Optional[str] = None
