#!/usr/bin/env python3
"""Update GitHub release notes for v0.6.0"""

import os
import json
import sys
from pathlib import Path

REPO = "eMeF1/ha-cem-monitoring-integration"
TAG = "v0.6.0"
NOTES_FILE = "RELEASE_NOTES_v0.6.0.md"

def get_token():
    """Get GitHub token from environment or file"""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    
    token_file = Path(".github_token")
    if token_file.exists():
        return token_file.read_text().strip()
    
    print("Error: GITHUB_TOKEN environment variable or .github_token file required")
    sys.exit(1)

def read_notes():
    """Read release notes from file"""
    notes_path = Path(NOTES_FILE)
    if not notes_path.exists():
        print(f"Error: {NOTES_FILE} not found")
        sys.exit(1)
    return notes_path.read_text()

def update_release(token, notes):
    """Update GitHub release via API"""
    import urllib.request
    import urllib.error
    
    url = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
    
    data = json.dumps({"body": notes}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="PATCH"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✓ Release {TAG} updated successfully!")
            print(f"  URL: {result.get('html_url', 'N/A')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Error updating release: {e.code}")
        print(error_body)
        return False

if __name__ == "__main__":
    token = get_token()
    notes = read_notes()
    update_release(token, notes)

