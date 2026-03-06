#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command-line interface for ShotGrid dependency tracking.

This script provides a CLI for querying ShotGrid version dependencies
with various filtering and output options.
"""

import argparse
import json
import re
from collections import Counter

from sg_auth import getShotgridConnection
from sg_core import (
    fetchVersion,
    fetchVersionByIdOrName,
    getPublishedFilesForVersion,
    crawlTree,
    Node
)
from sg_utils import (
    formatDatetime,
    parseDate,
    normalizeListArg,
    getPubTypeName,
    createdDatetime,
    ansiColor,
    TYPE_COLOR
)


def pubMatches(pub, includeTypes=None, excludeTypes=None, users=None,
               sinceDt=None, untilDt=None, regex=None):
    """
    Check if a publish passes all provided filters.

    Args:
        pub: Publish entity dictionary
        includeTypes: Set of types to include
        excludeTypes: Set of types to exclude
        users: Set of user names to include
        sinceDt: Minimum creation datetime
        untilDt: Maximum creation datetime
        regex: Compiled regex pattern

    Returns:
        True if publish matches all filters
    """
    typeName = getPubTypeName(pub)

    if includeTypes and typeName not in includeTypes:
        return False
    if excludeTypes and typeName in excludeTypes:
        return False

    userName = (pub.get("created_by") or {}).get("name") or ""
    if users and userName not in users:
        return False

    createdDt = createdDatetime(pub.get("created_at"))
    if sinceDt and createdDt and createdDt < sinceDt:
        return False
    if untilDt and createdDt and createdDt > untilDt:
        return False

    if regex:
        name = pub.get("name") or pub.get("code") or ""
        haystack = f"{name}|{typeName}"
        if not regex.search(haystack):
            return False

    return True


def pubLabel(pub):
    """
    Generate a display label for a publish.

    Args:
        pub: Publish entity dictionary

    Returns:
        Formatted label string
    """
    typeName = getPubTypeName(pub)
    version = pub.get("version_number") or "-"
    name = pub.get("name") or pub.get("code") or f"TPF_{pub.get('id')}"
    who = (pub.get("created_by") or {}).get("name") or "Unknown"
    when = formatDatetime(pub.get("created_at"))
    return f"{name}  [{typeName}]  v{version}  by {who} @ {when}"


def printFlat(rows, rootLabel, color=False):
    """
    Print dependencies as a flat aligned list.

    Args:
        rows: List of (id, pub, depth) tuples
        rootLabel: Label for the root version
        color: Whether to apply ANSI colors
    """
    print(rootLabel)
    if not rows:
        print("  (no dependencies)")
        return

    rows = sorted(rows, key=lambda row: (row[2], row[0]))
    idWidth = max(len(str(pubId)) for pubId, _, _ in rows)
    typeWidth = max(len(getPubTypeName(pub)) for _, pub, _ in rows)
    verWidth = max(len(str((pub.get("version_number") or "-"))) for _, pub, _ in rows)
    userWidth = max(len((pub.get("created_by") or {}).get("name") or "Unknown") for _, pub, _ in rows)

    for pubId, pub, depth in rows:
        typeName = getPubTypeName(pub)
        version = pub.get("version_number") or "-"
        who = (pub.get("created_by") or {}).get("name") or "Unknown"
        when = formatDatetime(pub.get("created_at"))
        name = pub.get("name") or pub.get("code") or f"TPF_{pub.get('id')}"
        typeDisplay = ansiColor(typeName.ljust(typeWidth), TYPE_COLOR.get(typeName), color)
        print("  {pid:>{idw}}  {typ}  v{ver:<{verw}}  {who:<{usw}}  {when}  {nm}".format(
            pid=pubId, idw=idWidth, typ=typeDisplay, ver=version, verw=verWidth,
            who=who, usw=userWidth, when=when, nm=name
        ))


def printTreeBranchwise(roots, rootLabel, color=False):
    """
    Print dependencies as a tree structure.

    Args:
        roots: List of root Node objects
        rootLabel: Label for the root version
        color: Whether to apply ANSI colors
    """
    print(rootLabel)

    if not roots:
        print("  (no dependencies)")
        return

    def sortChildren(node):
        """Sort children recursively."""
        node.children.sort(key=lambda child: (child.depth, child.id))
        for child in node.children:
            sortChildren(child)

    for root in roots:
        sortChildren(root)

    def walk(node, indent):
        """Walk tree and print nodes."""
        pub = node.pub
        typeName = getPubTypeName(pub)
        label = pubLabel(pub)
        label = label.replace(f"[{typeName}]", f"[{ansiColor(typeName, TYPE_COLOR.get(typeName), color)}]")
        print(f"{indent}└─ {node.id}: {label}")

        nextIndent = indent + '  '
        for child in node.children:
            walk(child, nextIndent)

    for root in roots:
        walk(root, indent="  ")


def toJson(version, pubs):
    """
    Convert version and publishes to JSON structure.

    Args:
        version: Version entity dictionary
        pubs: List of (id, pub, depth) tuples

    Returns:
        Dictionary for JSON serialization
    """
    out = {
        "version": {
            "id": version["id"],
            "code": version.get("code"),
            "department": version.get("sg_department"),
            "created_at": formatDatetime(version.get("created_at")),
            "user": (version.get("user") or {}).get("name"),
        },
        "dependencies": []
    }
    for pubId, pub, depth in pubs:
        from sg_utils import expandLinks, getIdFromLink
        out["dependencies"].append({
            "id": pubId,
            "depth": depth,
            "name": pub.get("name") or pub.get("code"),
            "type": getPubTypeName(pub),
            "version_number": pub.get("version_number"),
            "created_at": formatDatetime(pub.get("created_at")),
            "created_by": (pub.get("created_by") or {}).get("name"),
            "links": {
                "upstream_ids": expandLinks(pub.get("upstream_tank_published_files")),
                "downstream_ids": expandLinks(pub.get("downstream_tank_published_files")),
            },
            "linked_version_id": getIdFromLink(pub.get("sg_version")),
        })
    return out


def main(argv=None):
    """
    Main CLI entry point.

    Args:
        argv: Command line arguments (defaults to sys.argv)
    """
    parser = argparse.ArgumentParser(
        description="ShotGrid dependency crawler (Version -> TankPublishedFile deps)."
    )
    parser.add_argument("-v", "--version-id", type=str, required=True,
                        help="ShotGrid Version ID (e.g., 4339035) or Version Name (e.g., 306dtt_1740.lig.creative.main.defPart.v10).")
    parser.add_argument("-d", "--direction", choices=["upstream", "downstream", "both"],
                        default="upstream")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of a text view.")

    parser.add_argument("--include-types",
                        help="CSV of tank/published types to include (exact names).")
    parser.add_argument("--exclude-types", help="CSV of types to exclude.")
    parser.add_argument("--by-user",
                        help="CSV of creator display-names to include (exact).")
    parser.add_argument("--since", help="Only items created on/after YYYY-MM-DD.")
    parser.add_argument("--until", help="Only items created on/before YYYY-MM-DD.")
    parser.add_argument("--match",
                        help="Regex (case-insensitive) applied to name/code/type.")
    parser.add_argument("--summary", action="store_true",
                        help="Print summary by type and by user.")
    parser.add_argument("--color", action="store_true",
                        help="Colorize output by type.")
    parser.add_argument("--flat", action="store_true",
                        help="Print a flat, aligned list instead of a tree.")
    parser.add_argument("--hide-empty", action="store_true",
                        help="Suppress '(no dependencies)' if filters remove all rows.")

    parser.add_argument("--sg-server")
    parser.add_argument("--sg-script")
    parser.add_argument("--sg-key")

    args = parser.parse_args(argv)

    includeTypes = normalizeListArg(args.include_types)
    excludeTypes = normalizeListArg(args.exclude_types)
    users = normalizeListArg(args.by_user)
    sinceDt = parseDate(args.since) if args.since else None
    untilDt = parseDate(args.until) if args.until else None
    regex = re.compile(args.match, re.I) if args.match else None

    sgConnection = getShotgridConnection(args)
    versionData = fetchVersionByIdOrName(sgConnection, args.version_id)
    pubsData = getPublishedFilesForVersion(sgConnection, versionData)
    startIds = [pub["id"] for pub in pubsData]

    forest = crawlTree(sgConnection, startIds, args.direction, args.max_depth)

    def flatten(node):
        """Flatten tree to list."""
        out = [(node.id, node.pub, node.depth)]
        for child in node.children:
            out.extend(flatten(child))
        return out

    allRows = []
    for root in forest:
        allRows.extend(flatten(root))

    filteredIds = {
        pubId for (pubId, pub, depth) in allRows
        if pubMatches(pub, includeTypes, excludeTypes, users, sinceDt, untilDt, regex)
    }

    def prune(node):
        """Prune tree to filtered nodes."""
        keepSelf = node.id in filteredIds
        keptChildren = []
        for child in node.children:
            kept = prune(child)
            if kept:
                keptChildren.append(kept)
        if keepSelf or keptChildren:
            newNode = Node(node.id, node.pub, node.depth)
            newNode.children = keptChildren
            return newNode
        return None

    pruned = []
    for root in forest:
        kept = prune(root)
        if kept:
            pruned.append(kept)

    rootLabel = "Version {id}: {code} [{dept}] @ {when}".format(
        id=versionData["id"], code=versionData.get("code"),
        dept=versionData.get("sg_department"), when=formatDatetime(versionData.get("created_at"))
    )

    if args.summary:
        def collect(node, bag):
            """Collect all nodes."""
            bag.append(node.pub)
            for child in node.children:
                collect(child, bag)

        bag = []
        for root in pruned:
            collect(root, bag)
        byType = Counter(getPubTypeName(pub) for pub in bag)
        byUser = Counter((pub.get("created_by") or {}).get("name") or "Unknown" for pub in bag)
        print("\nSummary by type:")
        for key, value in byType.most_common():
            print(f"  {key:22} {value}")
        print("Summary by user:")
        for key, value in byUser.most_common():
            print(f"  {key:22} {value}")
        print("")

    if args.json:
        flat = []

        def flatCollect(node, depth=0):
            """Flatten for JSON."""
            flat.append((node.id, node.pub, depth))
            for child in node.children:
                flatCollect(child, depth + 1)

        for root in pruned:
            flatCollect(root, 0)
        print(json.dumps(toJson(versionData, flat), indent=2))
    else:
        if args.flat:
            flat = []

            def flatCollect(node, depth=0):
                """Flatten for display."""
                flat.append((node.id, node.pub, depth))
                for child in node.children:
                    flatCollect(child, depth + 1)

            for root in pruned:
                flatCollect(root, 0)
            if not flat and args.hide_empty:
                print(rootLabel)
            else:
                printFlat(flat, rootLabel, color=args.color)
        else:
            if not pruned and args.hide_empty:
                print(rootLabel)
            else:
                printTreeBranchwise(pruned, rootLabel, color=args.color)


if __name__ == "__main__":
    main()
