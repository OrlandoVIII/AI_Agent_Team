#!/usr/bin/env python3
"""
Backend Dev Agent - Self Healing Fix Script
Triggered when the Code Reviewer Agent requests changes on a backend PR.
Reads the review comments, calls Claude to fix the issues, and pushes the fix.
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
BACKEND_AGENT_TOKEN = os.environ["BACKEND_AGENT_TOKEN"]
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]
PR_NUMBER = int(os.environ["PR_NUMBER"])
PR_BRANCH = os.environ["PR_BRANCH"]
REVIEW_BODY = os.environ.get("REVIEW_BODY", "")
REVIEWER_LOGIN = os.environ.get("REVIEWER_LOGIN", "")

# Max number of self-healing attempts to prevent infinite loops
MAX_FIX_ATTEMPTS = 3


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def load_prompt() -> str:
    """Load the fix system prompt."""
    prompt_path = Path(__file__).parent / "backend_agent_fix_prompt.txt"
    return prompt_path.read_text()


def get_pr_details() -> tuple[str, list[dict]]:
    """Get the PR review comments and current file contents."""
    github = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    repo = github.get_repo(REPO_FULL_NAME)
    pr = repo.get_pull(PR_NUMBER)

    # Get all review comments (inline) and review bodies
    all_findings = []

    # Get the main review body (the structured review from our bot)
    for review in pr.get_reviews():
        if review.state == "CHANGES_REQUESTED":
            all_findings.append({
                "type": "review_body",
                "reviewer": review.user.login,
                "body": review.body
            })

    # Get inline review comments
    for comment in pr.get_review_comments():
        all_findings.append({
            "type": "inline_comment",
            "file": comment.path,
            "line": comment.original_line,
            "body": comment.body
        })

    return pr.title, all_findings


def get_current_files() -> dict[str, str]:
    """Read all current files in the repo that are relevant."""
    relevant_extensions = {".py", ".yml", ".yaml", ".env.example", ".txt", ".dockerfile"}
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "alembic/versions"}

    files = {}
    for path in Path(".").rglob("*"):
        if path.is_file():
            # Skip hidden dirs and irrelevant paths
            parts = set(path.parts)
            if parts.intersection(skip_dirs):
                continue
            if path.suffix.lower() in relevant_extensions or path.name == "Dockerfile":
                try:
                    files[str(path)] = path.read_text()
                except Exception:
                    pass

    return files


def check_fix_attempt_count() -> int:
    """Count how many fix attempts have been made by checking commit history."""
    result = subprocess.run(
        ["git", "log", "--oneline", "--grep=fix: address code review"],
        capture_output=True, text=True
    )
    return len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0


def call_claude(pr_title: str, findings: list[dict], current_files: dict) -> dict:
    """Call Claude with the review findings and current files to get fixes."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt()

    # Format findings for Claude
    findings_text = "\n\n".join([
        f"**{f['type'].replace('_', ' ').title()}**"
        + (f" ({f['file']} line {f.get('line', '?')})" if f['type'] == 'inline_comment' else "")
        + f"\n{f['body']}"
        for f in findings
    ])

    # Format current files (limit size)
    files_text = ""
    total_chars = 0
    for path, content in current_files.items():
        if total_chars > 60_000:
            files_text += f"\n[... remaining files truncated for length ...]"
            break
        files_text += f"\n\n### {path}\n```\n{content}\n```"
        total_chars += len(content)

    user_message = f"""
## Pull Request: {pr_title}

## Code Review Findings (Changes Requested)
{findings_text}

## Current File Contents
{files_text}

Please fix ALL the issues found in the review and respond with the JSON fix object.
""".strip()

    print("   Calling Claude API for fixes...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def apply_fixes(result: dict) -> bool:
    """Write the fixed files, commit and push."""
    files = result.get("files", [])
    if not files:
        print("   No files to fix.")
        return False

    print(f"   Applying fixes to {len(files)} file(s)...")

    for file_entry in files:
        file_path = Path(file_entry["path"])
        content = file_entry["content"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        print(f"     ✅ Fixed: {file_path}")

    # Stage and commit
    subprocess.run(["git", "add", "."], check=True)

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True
    )

    if not status.stdout.strip():
        print("   No changes after fix — files may already be correct.")
        return False

    commit_message = result.get("commit_message", "fix: address code review findings")
    subprocess.run(["git", "commit", "-m", commit_message], check=True)

    # Push using agent token
    repo_url = f"https://x-access-token:{BACKEND_AGENT_TOKEN}@github.com/{REPO_FULL_NAME}.git"
    subprocess.run(["git", "push", repo_url, PR_BRANCH], check=True)

    print(f"   ✅ Fix pushed to {PR_BRANCH}")
    return True


def post_fix_comment(result: dict) -> None:
    """Post a comment on the PR explaining what was fixed."""
    agent_github = Github(auth=Auth.Token(BACKEND_AGENT_TOKEN))
    repo = agent_github.get_repo(REPO_FULL_NAME)
    pr = repo.get_pull(PR_NUMBER)

    fix_comment = result.get("pr_comment", "Fixed the issues raised in the code review.")

    pr.create_issue_comment(
        f"🤖 **Backend Dev Agent — Self-Healing Fix**\n\n"
        f"{fix_comment}\n\n"
        f"_Pushed fix commit and awaiting re-review from Code Reviewer Agent._"
    )


def post_error_comment(error_message: str) -> None:
    """Post a comment if the fix fails."""
    try:
        agent_github = Github(auth=Auth.Token(BACKEND_AGENT_TOKEN))
        repo = agent_github.get_repo(REPO_FULL_NAME)
        pr = repo.get_pull(PR_NUMBER)
        pr.create_issue_comment(
            f"🤖 **Backend Dev Agent — Fix Failed**\n\n"
            f"I attempted to fix the review issues but encountered an error:\n\n"
            f"```\n{error_message}\n```\n\n"
            f"Please review the issues manually."
        )
    except Exception as e:
        print(f"   Could not post error comment: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🔧 Backend Dev Agent — Self-Healing Fix starting...")
    print(f"   PR #{PR_NUMBER}: {PR_BRANCH}")
    print(f"   Reviewer: {REVIEWER_LOGIN}")

    # Safety check — prevent infinite fix loops
    attempt_count = check_fix_attempt_count()
    print(f"   Fix attempt #{attempt_count + 1} of {MAX_FIX_ATTEMPTS}")

    if attempt_count >= MAX_FIX_ATTEMPTS:
        msg = (
            f"Maximum fix attempts ({MAX_FIX_ATTEMPTS}) reached. "
            f"Please review the remaining issues manually."
        )
        print(f"\n⚠️  {msg}")
        post_error_comment(msg)
        sys.exit(0)  # Exit 0 so the workflow doesn't fail permanently

    try:
        # Step 1: Get PR review details
        print("\n📋 Step 1: Reading review findings...")
        pr_title, findings = get_pr_details()
        print(f"   Found {len(findings)} review finding(s)")

        if not findings:
            print("   No findings to fix — exiting.")
            return

        # Step 2: Read current files
        print("\n📂 Step 2: Reading current files...")
        current_files = get_current_files()
        print(f"   Read {len(current_files)} file(s)")

        # Step 3: Call Claude for fixes
        print("\n🤖 Step 3: Generating fixes with Claude...")
        result = call_claude(pr_title, findings, current_files)
        print(f"   Files to fix: {len(result.get('files', []))}")

        # Step 4: Apply fixes and push
        print("\n✏️  Step 4: Applying and pushing fixes...")
        changed = apply_fixes(result)

        if changed:
            # Step 5: Post a comment explaining the fix
            print("\n💬 Step 5: Posting fix comment...")
            post_fix_comment(result)
            print("\n✅ Self-healing fix complete! Code Reviewer will re-review automatically.")
        else:
            print("\n⚠️  No changes were applied.")

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
