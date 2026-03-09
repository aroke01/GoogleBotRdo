#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script to list all tasks in Google Tasks.

Verifies that tasks are being created properly.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.tasks import buildTasksService, getOrCreateTaskList


def main():
    """List all tasks in the sgbot task list."""
    print("=" * 60)
    print("Google Tasks - List Tasks")
    print("=" * 60)
    print()

    # Build service
    service = buildTasksService()
    if not service:
        print("❌ Failed to build Google Tasks service")
        print("Make sure you ran: python auth_setup.py")
        sys.exit(1)

    # Get sgbot task list
    taskListId = getOrCreateTaskList(service, "sgbot")
    if not taskListId:
        print("❌ Failed to get sgbot task list")
        sys.exit(1)

    print(f"✓ Found task list: sgbot (ID: {taskListId})")
    print()

    # List all tasks
    try:
        results = service.tasks().list(tasklist=taskListId).execute()
        tasks = results.get('items', [])

        if not tasks:
            print("No tasks found in sgbot list.")
        else:
            print(f"Found {len(tasks)} task(s):")
            print()
            for idx, task in enumerate(tasks, 1):
                title = task.get('title', '(no title)')
                status = task.get('status', 'unknown')
                due = task.get('due', 'no due date')
                notes = task.get('notes', '')

                print(f"{idx}. {title}")
                print(f"   Status: {status}")
                print(f"   Due: {due}")
                if notes:
                    print(f"   Notes: {notes}")
                print()

    except Exception as exc:
        print(f"❌ Failed to list tasks: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
