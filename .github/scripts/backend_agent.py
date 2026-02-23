#!/usr/bin/env python3
"""
Backend Dev Agent
Triggered when a GitHub issue is assigned to the backend agent account.
Reads the issue, calls Claude to generate code, creates a branch and opens a PR.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import anthropic
from github import Github, Auth

# ─── CONFIG ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
BACKEND_AGENT_TOKEN = os.environ["BACKEND_AGENT_TOKEN"]
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
ISSUE_TITLE = os.environ["ISSUE_TITLE"]
ISSUE_BODY = os.environ.get("ISSUE_BODY", "No description provided.")

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def load_prompt() -> str:
    """Load the backend agent system prompt."""
    prompt_path = Path(__file__).parent / "backend_agent_prompt.txt"
    return prompt_path.read_text()


def call_claude(issue_title: str, issue_body: str) -> dict:
    """Call Claude with the issue details and get code back."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt()

    user_message = f"""
## GitHub Issue #{ISSUE_NUMBER}

**Title:** {issue_title}

**Description:**
{issue_body}

Please implement this issue and respond with the JSON output as specified.
""".strip()

    print("   Calling Claude API...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    raw = message.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def sanitize_branch_name(text: str) -> str:
    """Convert text to a valid git branch name segment."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9-]', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')[:30]


def create_branch_and_files(result: dict) -> str:
    """Create the feature branch, write files, commit and push."""
    branch_suffix = sanitize_branch_name(result.get("branch_suffix", f"issue-{ISSUE_NUMBER}"))
    branch_name = f"feature/backend/{ISSUE_NUMBER}-{branch_suffix}"

    print(f"   Creating branch: {branch_name}")

    # Make sure we're on develop and up to date
    subprocess.run(["git", "checkout", "develop"], check=True)
    subprocess.run(["git", "pull", "origin", "develop"], check=True)

    # Create and switch to feature branch
    subprocess.run(["git", "checkout", "-b", branch_name], check=True)

    # Write all files
    files = result.get("files", [])
    print(f"   Writing {len(files)} file(s)...")

    for file_entry in files:
        file_path = Path(file_entry["path"])
        content = file_entry["content"]

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        file_path.write_text(content)
        print(f"     ✅ {file_path}")

    # Stage all changes
    subprocess.run(["git", "add", "."], check=True)

    # Check if there's anything to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True
    )

    if not status.stdout.strip():
        print("   No changes to commit.")
        return branch_name

    # Commit
    commit_message = result.get("commit_message", f"feat: resolve issue #{ISSUE_NUMBER}")
    subprocess.run(["git", "commit", "-m", commit_message], check=True)

    # Push using the agent token for authentication
    repo_url = f"https://x-access-token:{BACKEND_AGENT_TOKEN}@github.com/{REPO_FULL_NAME}.git"
    subprocess.run(
        ["git", "push", repo_url, branch_name],
        check=True
    )

    print(f"   ✅ Branch pushed: {branch_name}")
    return branch_name


def open_pr(branch_name: str, result: dict) -> None:
    """Open a pull request from the feature branch to develop."""
    agent_github = Github(auth=Auth.Token(BACKEND_AGENT_TOKEN))
    repo = agent_github.get_repo(REPO_FULL_NAME)

    pr_title = result.get("pr_title", f"feat: resolve issue #{ISSUE_NUMBER} - {ISSUE_TITLE}")
    pr_body = result.get("pr_body", f"Resolves #{ISSUE_NUMBER}")

    # Ensure the PR body references the issue for auto-close
    if f"#{ISSUE_NUMBER}" not in pr_body:
        pr_body += f"\n\nCloses #{ISSUE_NUMBER}"

    print(f"   Opening PR: {pr_title}")

    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=branch_name,
        base="develop",
        draft=False
    )

    print(f"   ✅ PR opened: {pr.html_url}")

    # Comment on the original issue with a link to the PR
    issue = repo.get_issue(ISSUE_NUMBER)
    issue.create_comment(
        f"🤖 **Backend Dev Agent** has started working on this issue.\n\n"
        f"Pull request opened: {pr.html_url}\n\n"
        f"The Code Reviewer Agent will review the code automatically."
    )


def post_error_comment(error_message: str) -> None:
    """Post a comment on the issue if something goes wrong."""
    try:
        agent_github = Github(auth=Auth.Token(BACKEND_AGENT_TOKEN))
        repo = agent_github.get_repo(REPO_FULL_NAME)
        issue = repo.get_issue(ISSUE_NUMBER)
        issue.create_comment(
            f"🤖 **Backend Dev Agent** encountered an error while working on this issue:\n\n"
            f"```\n{error_message}\n```\n\n"
            f"Please check the GitHub Actions logs for more details."
        )
    except Exception as e:
        print(f"   Could not post error comment: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🤖 Backend Dev Agent starting...")
    print(f"   Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}")
    print(f"   Repo: {REPO_FULL_NAME}")

    try:
        # Step 1: Call Claude to generate the code
        print("\n📝 Step 1: Generating code with Claude...")
        result = call_claude(ISSUE_TITLE, ISSUE_BODY)
        print(f"   Files to create: {len(result.get('files', []))}")

        # Step 2: Create branch, write files, commit, push
        print("\n🌿 Step 2: Creating branch and committing files...")
        branch_name = create_branch_and_files(result)

        # Step 3: Open the PR
        print("\n🔀 Step 3: Opening pull request...")
        open_pr(branch_name, result)

        print("\n✅ Backend Dev Agent completed successfully!")
        print(f"   Branch: {branch_name}")

    except json.JSONDecodeError as e:
        error = f"Failed to parse Claude's response as JSON: {e}"
        print(f"\n❌ {error}")
        post_error_comment(error)
        sys.exit(1)

    except subprocess.CalledProcessError as e:
        error = f"Git operation failed: {e}"
        print(f"\n❌ {error}")
        post_error_comment(error)
        sys.exit(1)

    except Exception as e:
        error = f"Unexpected error: {e}"
        print(f"\n❌ {error}")
        post_error_comment(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
