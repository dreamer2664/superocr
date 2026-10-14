#!/usr/bin/env bash
# preflight-pr.sh — run BEFORE opening a PR (or pushing a task branch).
#
# A branch cut from old main can look tiny on GitHub and still, if merged,
# silently delete everything that landed since. Three of those were caught by
# hand on the night of 2026-10-11/12; this is the ten-second check.
#
# Usage:  bash tools/preflight-pr.sh [branch]     (default: current branch)
# Exit:   0 = clear · 1 = deletions vs main (look before you PR) · 2 = usage
set -u

br="${1:-$(git rev-parse --abbrev-ref HEAD)}"
case "$br" in ""|HEAD) echo "usage: bash tools/preflight-pr.sh <branch>"; exit 2 ;; esac

git fetch -q origin main 2>/dev/null
git fetch -q origin "refs/heads/$br:refs/remotes/origin/$br" 2>/dev/null || true
remote="origin/$br"
git rev-parse --verify -q "$remote" >/dev/null || { echo "no branch '$br' on origin (pushed yet?)"; exit 2; }

base=$(git merge-base origin/main "$remote")
behind=$(git rev-list --count "$base..origin/main")
echo "branch:  $br"
echo "base:    $(git log -1 --format='%h %s' "$base" | cut -c1-72)"
echo "main:    $(git log -1 --format='%h %s' origin/main | cut -c1-72)"
echo "behind:  $behind commit(s) since the branch was cut"
echo

deleted=$(git diff --name-status origin/main "$remote" | awk '$1=="D"{print $2}')
if [ -n "$deleted" ]; then
  n=$(printf '%s\n' "$deleted" | wc -l | tr -d ' ')
  echo "!! FILES THAT WOULD VANISH IF THIS BRANCH MERGED ($n):"
  printf '%s\n' "$deleted" | sed 's/^/   D /'
  echo
  echo "If you did not mean to delete these, your branch is cut from old history."
  echo "Re-cut from fresh main and re-apply only your change:"
  echo "   git fetch origin && git checkout -B agent/<you>/<task-id> origin/main"
  exit 1
fi

if [ "$behind" -gt 0 ]; then
  echo "note: no deletions, but $behind commit(s) behind main - consider rebasing."
fi
echo "OK: nothing vanishes if this branch lands."
exit 0
