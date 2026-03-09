"""
Google Tasks integration for rdo_googlebot.

Creates tasks in Google Tasks when 📝 emoji is present in message.
Fails silently — never blocks bot reply.
"""

import os
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/tasks']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'


def buildTasksService(tokenPath=None, credPath=None):
    """Build authenticated Google Tasks API service.

    Args:
        tokenPath: Path to token.json (default: ./token.json)
        credPath: Path to credentials.json (default: ./credentials.json)

    Returns:
        googleapiclient.discovery.Resource or None if auth fails
    """
    if not tokenPath:
        projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tokenPath = os.path.join(projectRoot, TOKEN_FILE)

    if not credPath:
        projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        credPath = os.path.join(projectRoot, CREDENTIALS_FILE)

    try:
        if not os.path.exists(tokenPath):
            print(f"⚠️  Google Tasks: {TOKEN_FILE} not found, skipping task creation")
            return None

        creds = Credentials.from_authorized_user_file(tokenPath, SCOPES)

        # Refresh token if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed credentials
            with open(tokenPath, 'w') as token:
                token.write(creds.to_json())

        service = build('tasks', 'v1', credentials=creds)
        return service

    except Exception as exc:
        print(f"⚠️  Google Tasks: Failed to build service: {exc}")
        return None


def getOrCreateTaskList(service, listName="sgbot"):
    """Get or create a task list by name.

    Args:
        service: Authenticated Google Tasks service
        listName: Name of the task list (default: "sgbot")

    Returns:
        str: Task list ID or None if failed
    """
    if not service:
        return None

    try:
        # Get all task lists
        results = service.tasklists().list().execute()
        taskLists = results.get('items', [])

        # Search for existing list
        for taskList in taskLists:
            if taskList['title'] == listName:
                return taskList['id']

        # Create new list if not found
        newList = {
            'title': listName
        }
        createdList = service.tasklists().insert(body=newList).execute()
        print(f"✓ Created Google Tasks list: {listName}")
        return createdList['id']

    except HttpError as exc:
        print(f"⚠️  Google Tasks: Failed to get/create list '{listName}': {exc}")
        return None


def createTask(service, code, note, sgUrl, assignee=None, listName="sgbot"):
    """Create a task in Google Tasks.

    Args:
        service: Authenticated Google Tasks service
        code: Shot/asset code
        note: Note text from message
        sgUrl: ShotGrid URL
        assignee: Name of assigned user (optional)
        listName: Task list name (default: "sgbot")

    Returns:
        bool: True if task created successfully, False otherwise
    """
    if not service:
        return False

    try:
        # Get or create task list
        taskListId = getOrCreateTaskList(service, listName)
        if not taskListId:
            return False

        # Build task title
        title = f"Check {code}"
        if note:
            title += f" — {note}"

        # Build task notes
        taskNotes = sgUrl
        if assignee:
            taskNotes += f"\nFrom: {assignee}"

        # Set due date to today
        today = datetime.date.today()
        dueDate = today.isoformat() + 'T00:00:00.000Z'

        # Create task
        task = {
            'title': title,
            'notes': taskNotes,
            'due': dueDate
        }

        result = service.tasks().insert(
            tasklist=taskListId,
            body=task
        ).execute()

        print(f"✓ Created Google Task: {title}")
        return True

    except HttpError as exc:
        print(f"⚠️  Google Tasks: Failed to create task: {exc}")
        return False
    except Exception as exc:
        print(f"⚠️  Google Tasks: Unexpected error: {exc}")
        return False


def createTaskFromMessage(code, note, sgUrl, assignee=None):
    """Helper function to create task with automatic service setup.

    This is the main entry point for bot scripts.
    Fails silently if authentication or task creation fails.

    Args:
        code: Shot/asset code
        note: Note text from message
        sgUrl: ShotGrid URL
        assignee: Name of assigned user (optional)

    Returns:
        bool: True if task created, False otherwise
    """
    try:
        service = buildTasksService()
        if not service:
            return False

        return createTask(service, code, note, sgUrl, assignee)

    except Exception as exc:
        print(f"⚠️  Google Tasks: Failed to create task: {exc}")
        return False
