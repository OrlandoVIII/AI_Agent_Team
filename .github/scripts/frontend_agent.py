#!/usr/bin/env python3
"""
Frontend Dev Agent
Triggered by GitHub Actions when an issue is assigned to opulence-frontend1-bot.
Generates React/TypeScript code using Claude and opens a PR.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic
from github import Github, Auth

# ─── CONFIG ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FRONTEND_AGENT_TOKEN = os.environ["FRONTEND_AGENT_TOKEN"]
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
ISSUE_TITLE = os.environ["ISSUE_TITLE"]
ISSUE_BODY = os.environ["ISSUE_BODY"]

MAX_FIX_ATTEMPTS = 3


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def load_prompt() -> str:
    prompt_path = Path(__file__).parent / "frontend_agent_prompt.txt"
    return prompt_path.read_text()


def call_claude(issue_title: str, issue_body: str) -> dict:
    """Call Claude to generate frontend code for the issue."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt()

    user_message = f"""
## Issue #{ISSUE_NUMBER}: {issue_title}

{issue_body}

Please implement this issue by generating all necessary files.
Respond with ONLY a valid JSON object — no markdown, no preamble.
""".strip()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # Find JSON object boundaries
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    return json.loads(raw)


def create_branch(issue_number: int, issue_title: str) -> str:
    """Create a feature branch for this issue."""
    slug = issue_title.lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:6])
    branch_name = f"feature/frontend/{issue_number}-{slug}"

    subprocess.run(["git", "checkout", "-b", branch_name], check=True)
    print(f"   Created branch: {branch_name}")
    return branch_name


def write_files(files: list) -> list:
    """Write generated files to disk."""
    written = []
    for file_obj in files:
        path = Path(file_obj["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file_obj["content"])
        written.append(str(path))
        print(f"   ✅ Written: {path}")
    return written


def commit_and_push(branch_name: str, commit_message: str) -> None:
    """Stage all files, commit, and push."""
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", commit_message], check=True)
    subprocess.run(["git", "push", "origin", branch_name], check=True)
    print(f"   Pushed to: {branch_name}")


def open_pr(branch_name: str, title: str, body: str) -> int:
    """Open a PR using the frontend bot account."""
    bot_github = Github(auth=Auth.Token(FRONTEND_AGENT_TOKEN))
    bot_repo = bot_github.get_repo(REPO_FULL_NAME)

    pr = bot_repo.create_pull(
        title=title,
        body=body,
        head=branch_name,
        base="develop"
    )
    print(f"   PR opened: #{pr.number} — {pr.html_url}")
    return pr.number


def post_issue_comment(comment: str) -> None:
    """Post a comment on the issue."""
    bot_github = Github(auth=Auth.Token(FRONTEND_AGENT_TOKEN))
    bot_repo = bot_github.get_repo(REPO_FULL_NAME)
    issue = bot_repo.get_issue(ISSUE_NUMBER)
    issue.create_comment(comment)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🤖 Frontend Dev Agent starting...")
    print(f"   Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}")

    # Call Claude to generate the code
    print("   Calling Claude to generate frontend code...")
    result = call_claude(ISSUE_TITLE, ISSUE_BODY)

    commit_message = result.get("commit_message", f"feat: {ISSUE_TITLE.lower()}")
    pr_description = result.get("pr_description", "")
    files = result.get("files", [])

    print(f"   Claude generated {len(files)} files")

    if not files:
        print("❌ No files generated — aborting.")
        sys.exit(1)

    # Create branch
    branch_name = create_branch(ISSUE_NUMBER, ISSUE_TITLE)

    # Write files
    print("   Writing files...")
    write_files(files)

    # Commit and push
    print("   Committing and pushing...")
    commit_and_push(branch_name, commit_message)

    # Build PR body
    file_list = "\n".join(f"- `{f['path']}`" for f in files)
    pr_body = f"""## Summary
{pr_description}

Closes #{ISSUE_NUMBER}

## Changes
{file_list}

## Testing
- Run `cd frontend && npm install && npm run dev`
- Visit http://localhost:5173 for the app
- Run `npm run build` to verify production build
"""

    # Open PR
    print("   Opening PR...")
    pr_number = open_pr(
        branch_name=branch_name,
        title=f"feat: {ISSUE_TITLE}",
        body=pr_body
    )

    # Comment on issue
    post_issue_comment(
        f"🤖 **Frontend Dev Agent** has started working on this issue.\n\n"
        f"Pull request opened: #{pr_number}\n\n"
        f"The Code Reviewer Agent will review the code automatically."
    )

    print(f"\n✅ Done! PR #{pr_number} opened and ready for review.")


if __name__ == "__main__":
    main()
