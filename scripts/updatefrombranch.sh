#!/usr/bin/env bash
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
# Script to inspect, pull, or undo changes from a git branch or PR as unstaged modifications.

set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: This script must be run inside a git repository." >&2
  exit 1
fi

UNDO_MODE=0
BRANCH_ARG=""

for arg in "$@"; do
  case "$arg" in
    --undo|-undo|-u|--revert)
      UNDO_MODE=1
      ;;
    *)
      if [[ -z "${BRANCH_ARG}" ]]; then
        BRANCH_ARG="$arg"
      fi
      ;;
  esac
done

echo "Fetching all remotes..."
git fetch --all --quiet

if [[ -z "${BRANCH_ARG}" ]]; then
  echo
  echo "No branch specified. Recent remote branches:"
  git for-each-ref --sort=-committerdate --format='  %(refname:short) (%(committerdate:relative))' refs/remotes/origin/ | head -n 12
  echo
  read -r -p "Enter branch name or PR number: " BRANCH_ARG
  if [[ -z "${BRANCH_ARG}" ]]; then
    echo "Error: No branch specified." >&2
    exit 1
  fi
fi

TARGET_BRANCH="${BRANCH_ARG}"

# Handle PR numbers (e.g. 492)
if [[ "${TARGET_BRANCH}" =~ ^[0-9]+$ ]]; then
  PR_NUM="${TARGET_BRANCH}"
  TMP_BRANCH="pr-${PR_NUM}-temp"
  echo "Fetching PR #${PR_NUM} head..."
  git fetch -f origin "pull/${PR_NUM}/head:${TMP_BRANCH}" --quiet
  TARGET_BRANCH="${TMP_BRANCH}"
elif ! git rev-parse --verify --quiet "${TARGET_BRANCH}" >/dev/null; then
  if git rev-parse --verify --quiet "origin/${TARGET_BRANCH}" >/dev/null; then
    TARGET_BRANCH="origin/${TARGET_BRANCH}"
  fi
fi

if ! git rev-parse --verify --quiet "${TARGET_BRANCH}" >/dev/null; then
  echo "Error: Cannot resolve branch '${BRANCH_ARG}' to a valid git ref." >&2
  exit 1
fi

TARGET_REV="$(git rev-parse --short "${TARGET_BRANCH}")"
BASE="$(git merge-base HEAD "${TARGET_BRANCH}")"

echo
echo "=========================================================================="
echo " Target Branch : ${TARGET_BRANCH} (${TARGET_REV})"
echo " Merge-Base    : ${BASE:0:7}"
echo " Mode          : $(if [[ ${UNDO_MODE} -eq 1 ]]; then echo "UNDO / REVERT"; else echo "PULL / APPLY"; fi)"
echo "=========================================================================="
echo
echo "Commits on ${TARGET_BRANCH} since merge-base:"
git log --oneline "${BASE}..${TARGET_BRANCH}" || echo "  (no new commits)"

echo
echo "Diff summary of changes from ${TARGET_BRANCH}:"
git diff --stat "${BASE}" "${TARGET_BRANCH}"

CHANGED_FILES="$(git diff --name-only "${BASE}" "${TARGET_BRANCH}")"
if [[ -z "${CHANGED_FILES}" ]]; then
  echo
  echo "No files modified on ${TARGET_BRANCH} relative to merge-base."
  exit 0
fi

if [[ ${UNDO_MODE} -eq 1 ]]; then
  echo
  read -r -p "Revert all changes touched by ${TARGET_BRANCH} back to HEAD? [y/N] " CONFIRM
  case "${CONFIRM}" in
    [yY][eE][sS]|[yY])
      echo
      echo "Reverting touched files to HEAD state..."
      for f in ${CHANGED_FILES}; do
        if git cat-file -e "HEAD:${f}" 2>/dev/null; then
          git checkout HEAD -- "${f}"
          git reset HEAD -- "${f}" >/dev/null 2>&1 || true
        else
          rm -f "${f}"
        fi
      done
      echo "Successfully reverted all files touched by ${TARGET_BRANCH} back to HEAD."
      ;;
    *)
      echo "Aborted. No changes reverted."
      exit 0
      ;;
  esac
  exit 0
fi

echo
read -r -p "Pull these changes and leave them unstaged? [y/N] " CONFIRM
case "${CONFIRM}" in
  [yY][eE][sS]|[yY])
    echo
    echo "Applying changes unstaged..."
    git checkout "${TARGET_BRANCH}" -- ${CHANGED_FILES}
    git reset HEAD ${CHANGED_FILES} >/dev/null 2>&1 || true
    echo "Successfully updated working tree with unstaged changes from ${TARGET_BRANCH}."
    ;;
  *)
    echo "Aborted. No changes applied."
    exit 0
    ;;
esac
