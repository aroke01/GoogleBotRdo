"""
ShotGrid Service Template

This module provides a template for interacting with the ShotGrid API.
Customize the methods to fit your application's needs.
"""

import os
import shotgun_api3
from typing import Any, Dict, List, Optional


def read_api_key_file() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Read SG_URL, SG_SCRIPT_NAME and SG_SCRIPT_KEY from api.key file.
    
    The api.key file should contain:
        SG_URL=https://your-site.shotgrid.autodesk.com
        SG_SCRIPT_NAME=your_script_name
        SG_SCRIPT_KEY=your_api_key
    
    Returns:
        tuple: (url, script_name, api_key) or (None, None, None) if not found
    """
    # Get project root directory (one level up from Python/)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Try multiple locations for api.key file
    possible_locations = [
        os.path.join(os.path.dirname(__file__), "api.key"),  # Python/api.key
        os.path.join(project_root, "api.key"),  # Project root/api.key
        os.path.join(os.getcwd(), "api.key"),  # Current working directory
        os.path.expanduser("~/.shotgrid/api.key"),  # User home directory
    ]
    
    for api_key_file in possible_locations:
        if not os.path.exists(api_key_file):
            continue
            
        url = None
        script_name = None
        api_key = None
        
        try:
            with open(api_key_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse KEY=VALUE format
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        
                        if key == 'SG_URL':
                            url = value
                        elif key == 'SG_SCRIPT_NAME':
                            script_name = value
                        elif key == 'SG_SCRIPT_KEY':
                            api_key = value
        except Exception:
            continue
        
        if script_name and api_key:
            return url, script_name, api_key
    
    return None, None, None


class ShotGridService:
    """
    Service class for interacting with ShotGrid API.
    
    Customize the methods below to fit your application's needs.
    """
    
    def __init__(self, url: str, script_name: str, api_key: str):
        """
        Initialize the ShotGrid service.
        
        Args:
            url: ShotGrid server URL
            script_name: API script name
            api_key: API key
        """
        # Set defaults - customize these for your organization
        url = url or "https://your-site.shotgrid.autodesk.com"
        script_name = script_name or "your_script_name"
        api_key = api_key or ""
        
        # If credentials are missing, try reading from api.key file
        if not api_key or not script_name:
            file_url, file_script_name, file_api_key = read_api_key_file()
            if file_url:
                url = file_url
            if file_script_name:
                script_name = file_script_name
            if file_api_key:
                api_key = file_api_key
        
        # Validate that we have required credentials
        if not api_key:
            raise ValueError(
                "ShotGrid API key is required. Create an api.key file with SG_SCRIPT_KEY=your_api_key"
            )
        if not script_name:
            raise ValueError(
                "ShotGrid script name is required. Create an api.key file with SG_SCRIPT_NAME=your_script_name"
            )
        
        self.sg = shotgun_api3.Shotgun(url, script_name=script_name, api_key=api_key)

    def get_projects(self) -> List[Dict[str, Any]]:
        """
        Get list of active projects.
        
        Customize the filters and fields as needed.
        """
        filters = [
            ["sg_status", "is", "Active"],
            # Add more filters as needed, e.g.:
            # {"filter_operator": "any", "filters": [
            #     ["sg_type", "is", "TV Series"],
            #     ["sg_type", "is", "Feature Film"],
            # ]},
        ]
        fields = ["id", "name", "code"]
        order = [{"field_name": "name", "direction": "asc"}]
        
        return self.sg.find("Project", filters, fields, order=order) or []

    def get_project_data(self, project_id: int) -> Dict[str, Any]:
        """
        Get data for a specific project.
        
        Customize this method based on what data your app needs.
        
        Args:
            project_id: ShotGrid project ID
            
        Returns:
            Dictionary containing project data
        """
        # Get project info
        project = self.sg.find_one(
            "Project",
            [["id", "is", project_id]],
            ["id", "name", "code", "sg_status"]
        )
        
        if not project:
            return {"error": "Project not found"}
        
        # Example: Get shots for the project
        shots = self.sg.find(
            "Shot",
            [["project", "is", {"type": "Project", "id": project_id}]],
            ["id", "code", "sg_status_list", "description"],
            order=[{"field_name": "code", "direction": "asc"}]
        ) or []
        
        # Example: Get assets for the project
        assets = self.sg.find(
            "Asset",
            [["project", "is", {"type": "Project", "id": project_id}]],
            ["id", "code", "sg_asset_type", "sg_status_list"],
            order=[{"field_name": "code", "direction": "asc"}]
        ) or []
        
        return {
            "project": project,
            "shots": shots,
            "assets": assets,
        }

    # =========================================================================
    # ADD YOUR CUSTOM METHODS BELOW
    # =========================================================================
    
    # Example: Get users assigned to a project
    # def get_project_users(self, project_id: int) -> List[Dict[str, Any]]:
    #     """Get users assigned to tasks in a project."""
    #     tasks = self.sg.find(
    #         "Task",
    #         [["project", "is", {"type": "Project", "id": project_id}]],
    #         ["task_assignees"]
    #     ) or []
    #     
    #     user_ids = set()
    #     for task in tasks:
    #         for assignee in task.get("task_assignees", []):
    #             if assignee.get("id"):
    #                 user_ids.add(assignee["id"])
    #     
    #     if not user_ids:
    #         return []
    #     
    #     return self.sg.find(
    #         "HumanUser",
    #         [["id", "in", list(user_ids)]],
    #         ["id", "name", "department", "email"]
    #     ) or []
