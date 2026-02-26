#!/usr/bin/env python3
"""
Code Reviewer Agent
Triggered by GitHub Actions on every PR to develop.
Analyzes the diff using Claude and posts a structured review via the bot account.
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
REVIEWER_BOT_TOKEN = os.environ["REVIEWER_BOT_TOKEN"]
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]
PR_NUMBER = int(os.environ["PR_NUMBER"])
BASE_SHA = os.environ["BASE_SHA"]
HEAD_SHA = os.environ["HEAD_SHA"]

# Only CRITICAL findings block the PR
BLOCKING_SEVERITIES = {"CRITICAL"}

# File extensions we want to review (skip lock files, generated files, etc.)
REVIEWABLE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".sql", ".yml", ".yaml", ".dockerfile",
    ".json", ".env.example", ".sh"
}

SKIP_PATHS = {
    "package-lock.json", "yarn.lock", "poetry.lock",
    "requirements.txt",  # reviewed separately
    "alembic/versions/",  # migration files get a lighter review
}

MAX_DIFF_CHARS = 80_000  # ~20k tokens, safe limit for Claude


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_diff() -> str:
    """Get the PR diff using git."""
    result = subprocess.run(
        ["git", "diff", f"{BASE_SHA}...{HEAD_SHA}"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def filter_diff(diff: str) -> str:
    """Remove files we don't want to review and truncate if too large."""
    lines = diff.split("\n")
    filtered_lines = []
    skip_current_file = False

    for line in lines:
        # Detect file header
        if line.startswith("diff --git"):
            skip_current_file = False
            # Check if this file should be skipped
            for skip_path in SKIP_PATHS:
                if skip_path in line:
                    skip_current_file = True
                    break
            if not skip_current_file:
                # Check extension
                parts = line.split(" b/")
                if len(parts) > 1:
                    filename = parts[1]
                    ext = Path(filename).suffix.lower()
                    if ext not in REVIEWABLE_EXTENSIONS and ext != "":
                        skip_current_file = True

        if not skip_current_file:
            filtered_lines.append(line)

    filtered = "\n".join(filtered_lines)

    # Truncate if too large
    if len(filtered) > MAX_DIFF_CHARS:
        filtered = filtered[:MAX_DIFF_CHARS]
        filtered += "\n\n[DIFF TRUNCATED — too large. Review remaining files manually.]"

    return filtered


def load_prompt() -> str:
    """Load the reviewer system prompt."""
    prompt_path = Path(__file__).parent / "reviewer_prompt.txt"
    return prompt_path.read_text()


def call_claude(diff: str, pr_title: str, pr_body: str) -> dict:
    """Send the diff to Claude and get a structured review back."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt()

    user_message = f"""
## Pull Request
**Title:** {pr_title}
**Description:** {pr_body or 'No description provided.'}

## Diff
```diff
{diff}
```

Please review this diff and respond with the JSON review object.
""".strip()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude added them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def format_pr_comment(review: dict) -> str:
    """Format the Claude review JSON into a readable GitHub PR comment."""
    verdict = review["verdict"]
    summary = review["summary"]
    findings = review["findings"]
    stats = review["stats"]

    # Header
    if verdict == "APPROVE":
        header = "## ✅ Code Review — Approved"
    else:
        header = "## ❌ Code Review — Changes Requested"

    # Stats bar
    stats_line = (
        f"🔴 **{stats['critical']} Critical** &nbsp;|&nbsp; "
        f"🟡 **{stats['warning']} Warning** &nbsp;|&nbsp; "
        f"🟢 **{stats['info']} Info**"
    )

    # Findings
    findings_md = ""
    if findings:
        findings_md = "\n---\n## Findings\n"
        for f in findings:
            icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(f["severity"], "⚪")
            severity_label = f["severity"]
            file_ref = f"`{f['file']}`" if f.get("file") else ""
            line_ref = f" line {f['line']}" if f.get("line") else ""

            findings_md += f"""
### {icon} [{severity_label}] {f['title']}
**Location:** {file_ref}{line_ref}

{f['description']}

**Suggestion:**
```
{f['suggestion']}
```
"""
    else:
        findings_md = "\n\n_No issues found._"

    # Footer
    if verdict == "APPROVE":
        footer = (
            "\n---\n"
            "_🤖 Reviewed by Code Reviewer Agent. "
            "No critical issues found — this PR is approved for merge to `develop`._"
        )
    else:
        footer = (
            "\n---\n"
            "_🤖 Reviewed by Code Reviewer Agent. "
            "Fix the 🔴 CRITICAL issues above and push — I'll re-review automatically._"
        )

    return f"{header}\n\n{stats_line}\n\n{summary}{findings_md}{footer}"


def post_review(review: dict, comment_body: str, pr_author: str) -> None:
    """Post the review to GitHub using the bot account."""
    bot_github = Github(auth=Auth.Token(REVIEWER_BOT_TOKEN))
    bot_repo = bot_github.get_repo(REPO_FULL_NAME)
    pr = bot_repo.get_pull(PR_NUMBER)
    bot_user = bot_github.get_user().login

    verdict = review["verdict"]
    github_event = "APPROVE" if verdict == "APPROVE" else "REQUEST_CHANGES"

    # GitHub does not allow reviewing your own PR.
    # This happens when YOU open a test PR manually.
    # In production, agents open PRs so this won't occur.
    if pr_author == bot_user:
        print(f"   ⚠️  PR author ({pr_author}) is the bot — cannot post formal review.")
        print(f"   Falling back to a regular comment instead.")
        fallback = (
            f"{comment_body}\n\n"
            f"> ⚠️ _Could not post a formal review because the PR author and reviewer are the same account. "
            f"In production, agents open PRs so this won't happen._"
        )
        pr.create_issue_comment(fallback)
        print(f"✅ Comment posted (fallback mode)")
    else:
        pr.create_review(body=comment_body, event=github_event)
        print(f"✅ Review posted: {github_event}")

    print(f"   Critical: {review['stats']['critical']}")
    print(f"   Warning:  {review['stats']['warning']}")
    print(f"   Info:     {review['stats']['info']}")


def dismiss_previous_reviews() -> None:
    """
    Dismiss previous bot reviews so the PR isn't stuck on stale reviews
    when the author pushes a fix.
    """
    bot_github = Github(auth=Auth.Token(REVIEWER_BOT_TOKEN))
    bot_repo = bot_github.get_repo(REPO_FULL_NAME)
    pr = bot_repo.get_pull(PR_NUMBER)

    bot_user = bot_github.get_user().login

    for review in pr.get_reviews():
        if review.user.login == bot_user and review.state == "CHANGES_REQUESTED":
            try:
                review.dismiss("Re-reviewing after new commits.")
                print(f"   Dismissed stale review {review.id}")
            except Exception as e:
                print(f"   Could not dismiss review {review.id}: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🤖 Code Reviewer Agent starting...")

    # Get PR info using the default GITHUB_TOKEN (read-only is fine here)
    github = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    repo = github.get_repo(REPO_FULL_NAME)
    pr = repo.get_pull(PR_NUMBER)
    pr_author = pr.user.login

    print(f"   PR #{PR_NUMBER}: {pr.title}")
    print(f"   Author: {pr_author}")
    print(f"   Branch: {pr.head.ref} → {pr.base.ref}")

    # Dismiss any previous REQUEST_CHANGES from the bot (re-review on new push)
    print("   Dismissing stale reviews...")
    dismiss_previous_reviews()

    # Get and filter the diff
    print("   Fetching diff...")
    raw_diff = get_diff()
    diff = filter_diff(raw_diff)

    if not diff.strip():
        print("   Diff is empty — nothing to review.")
        bot_github = Github(auth=Auth.Token(REVIEWER_BOT_TOKEN))
        bot_repo = bot_github.get_repo(REPO_FULL_NAME)
        bot_pr = bot_repo.get_pull(PR_NUMBER)
        bot_pr.create_issue_comment(
            "## ✅ Code Review — Approved\n\n_No reviewable code changes detected._"
        )
        return

    print(f"   Diff size: {len(diff)} chars")

    # Call Claude
    print("   Calling Claude for review...")
    review = call_claude(diff, pr.title, pr.body)

    # Format and post
    print("   Posting review to GitHub...")
    comment = format_pr_comment(review)
    post_review(review, comment, pr_author)

    # Exit with error code if changes requested — marks the CI check as failed
    if review["verdict"] == "REQUEST_CHANGES":
        print("\n❌ Review completed: CHANGES REQUESTED (critical issues found)")
        sys.exit(1)
    else:
        print("\n✅ Review completed: APPROVED")
        auto_merge(pr)
        sys.exit(0)


if __name__ == "__main__":
    main()


def auto_merge(pr) -> None:
    """Merge the PR into develop after approval, then delete the branch."""
    try:
        print("   🔀 Auto-merging PR into develop...")
        branch_name = pr.head.ref
        repo = pr.base.repo
        pr.merge(
            commit_title=f"feat: merge {branch_name} into develop (auto-approved)",
            commit_message=f"Auto-merged by Code Reviewer Agent after approval.\n\nPR #{pr.number}: {pr.title}",
            merge_method="squash"
        )
        print("   ✅ PR merged successfully!")

        # Delete the feature branch after merge
        try:
            ref = repo.get_git_ref(f"heads/{branch_name}")
            ref.delete()
            print(f"   🗑️ Branch '{branch_name}' deleted.")
        except Exception as e:
            print(f"   ⚠️ Could not delete branch '{branch_name}': {e}")

    except Exception as e:
        print(f"   ⚠️ Auto-merge failed: {e}")
        print("   PR approved but must be merged manually.")
