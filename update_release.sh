#!/bin/bash
# Script to update GitHub release notes
# Requires GITHUB_TOKEN environment variable or .github_token file

REPO="eMeF1/ha-cem-monitoring-integration"
TAG="v0.6.0"
NOTES_FILE="RELEASE_NOTES_v0.6.0.md"

# Get token from environment or file
if [ -z "$GITHUB_TOKEN" ]; then
    if [ -f .github_token ]; then
        GITHUB_TOKEN=$(cat .github_token | tr -d '\n')
    else
        echo "Error: GITHUB_TOKEN environment variable or .github_token file required"
        exit 1
    fi
fi

# Read release notes
if [ ! -f "$NOTES_FILE" ]; then
    echo "Error: $NOTES_FILE not found"
    exit 1
fi

NOTES=$(cat "$NOTES_FILE")

# Update release via GitHub API
curl -X PATCH \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/$REPO/releases/tags/$TAG" \
  -d "{\"body\": $(echo "$NOTES" | jq -Rs .)}"

echo ""
echo "Release updated successfully!"

