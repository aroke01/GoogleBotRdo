"""
explorerApi.py

API endpoints for Published Files Explorer dropdown functionality.
Provides project/entity/type/version selection for Publish UI.
"""

from fastapi import APIRouter, Query
from typing import List, Dict, Any

router = APIRouter()

sgConnectionRef = None
rootPath = ""


def configureExplorerApi(sgConnection, appRootPath: str):
    """Configure explorer API with ShotGrid connection and root path."""
    global sgConnectionRef, rootPath
    sgConnectionRef = sgConnection
    rootPath = appRootPath


@router.get("/api/explorer/projects")
def getProjects() -> List[Dict[str, Any]]:
    """Get list of all projects."""
    projects = sgConnectionRef.find(
        "Project",
        [["sg_status", "is", "Active"]],
        ["id", "name", "code"],
        order=[{"field_name": "name", "direction": "asc"}]
    )
    return [{"id": p["id"], "name": p["name"], "code": p.get("code") or p["name"]} for p in projects]


@router.get("/api/explorer/entities")
def getEntities(project: str = Query(...)) -> List[Dict[str, Any]]:
    """Get list of assets for a project."""
    assets = sgConnectionRef.find(
        "Asset",
        [["project.Project.code", "is", project]],
        ["id", "code"],
        order=[{"field_name": "code", "direction": "asc"}]
    )
    return [{"id": a["id"], "code": a["code"]} for a in assets]


@router.get("/api/explorer/types")
def getTypes(project: str = Query(...), entity: str = Query(...)) -> List[str]:
    """Get list of tank types for an asset."""
    publishes = sgConnectionRef.find(
        "TankPublishedFile",
        [
            ["project.Project.code", "is", project],
            ["entity.Asset.code", "is", entity]
        ],
        ["tank_type"],
        limit=1000
    )
    
    tankTypes = set()
    for pub in publishes:
        tankType = pub.get("tank_type")
        if tankType and isinstance(tankType, dict):
            tankTypeName = tankType.get("name")
            if tankTypeName:
                tankTypes.add(tankTypeName)
    
    return sorted(list(tankTypes))


@router.get("/api/explorer/versions")
def getVersions(
    project: str = Query(...),
    entity: str = Query(...),
    type: str = Query(...)
) -> List[Dict[str, Any]]:
    """Get list of versions for project/entity/type combination."""
    publishes = sgConnectionRef.find(
        "TankPublishedFile",
        [
            ["project.Project.code", "is", project],
            ["entity.Asset.code", "is", entity],
            ["tank_type.TankType.name", "is", type]
        ],
        ["id", "code", "name", "version_number", "created_at"],
        order=[{"field_name": "version_number", "direction": "desc"}],
        limit=100
    )
    
    return [
        {
            "id": p["id"],
            "code": p.get("code", f"v{p.get('version_number', 0):03d}"),
            "name": p.get("name", ""),
            "versionNumber": p.get("version_number", 0)
        }
        for p in publishes
    ]
