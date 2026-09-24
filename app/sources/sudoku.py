"""Sudoku puzzle generator source.

Generates a valid Sudoku puzzle at easy/medium/hard difficulty.
Controlled by SUDOKU_ENABLED and SUDOKU_DIFFICULTY settings.
"""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path("/app/config/sudoku_state.json")

# Number of cells to remove per difficulty level
_DIFFICULTY_REMOVALS = {
    "easy":   40,
    "medium": 50,
    "hard":   58,
}


def _is_valid(grid: list[list[int]], row: int, col: int, num: int) -> bool:
    if num in grid[row]:
        return False
    if any(grid[r][col] == num for r in range(9)):
        return False
    br, bc = (row // 3) * 3, (col // 3) * 3
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if grid[r][c] == num:
                return False
    return True


def _fill(grid: list[list[int]]) -> bool:
    for row in range(9):
        for col in range(9):
            if grid[row][col] == 0:
                nums = list(range(1, 10))
                random.shuffle(nums)
                for num in nums:
                    if _is_valid(grid, row, col, num):
                        grid[row][col] = num
                        if _fill(grid):
                            return True
                        grid[row][col] = 0
                return False
    return True


def _count_solutions(grid: list[list[int]], limit: int = 2) -> int:
    """Count solutions, stopping at *limit*. Fills the most constrained cell
    first, which keeps the uniqueness checks fast enough to run per cell."""
    best = None
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                options = [n for n in range(1, 10) if _is_valid(grid, r, c, n)]
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
                    if len(options) <= 1:
                        break
        if best and len(best[2]) <= 1:
            break
    if best is None:
        return 1
    r, c, options = best
    found = 0
    for n in options:
        grid[r][c] = n
        found += _count_solutions(grid, limit - found)
        grid[r][c] = 0
        if found >= limit:
            break
    return found


def _generate_puzzle(difficulty: str) -> tuple[list[list[int]], list[list[int]]]:
    """Return (puzzle_grid, solution_grid) — 0 represents an empty cell.

    A clue is only removed if the puzzle still has exactly one solution;
    removing cells blindly leaves most medium/hard grids with several.
    """
    solution: list[list[int]] = [[0] * 9 for _ in range(9)]
    _fill(solution)

    puzzle = [row[:] for row in solution]
    target = _DIFFICULTY_REMOVALS.get(difficulty, _DIFFICULTY_REMOVALS["medium"])

    cells = list(range(81))
    random.shuffle(cells)
    removed = 0
    for cell in cells:
        if removed >= target:
            break
        r, c = divmod(cell, 9)
        keep = puzzle[r][c]
        puzzle[r][c] = 0
        if _count_solutions([row[:] for row in puzzle]) == 1:
            removed += 1
        else:
            puzzle[r][c] = keep

    return puzzle, solution


def _rotate_state(solution: list[list[int]], difficulty: str) -> dict | None:
    """Remember today's solution and return the last one from an earlier day,
    so each paper can print yesterday's answer."""
    today = date.today().isoformat()
    try:
        state = json.loads(_STATE_PATH.read_text()) if _STATE_PATH.exists() else {}
    except Exception:
        state = {}

    current = state.get("current") or {}
    previous = state.get("previous")
    if current.get("date") and current.get("date") != today:
        previous = current

    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps({
            "current": {"date": today, "difficulty": difficulty, "solution": solution},
            "previous": previous,
        }))
    except Exception as exc:
        logger.warning("Could not save Sudoku state: %s", exc)
    return previous


def fetch() -> list[dict]:
    try:
        from app import config_loader
        enabled = config_loader.get("SUDOKU_ENABLED", os.environ.get("SUDOKU_ENABLED", "false"))
        difficulty = config_loader.get("SUDOKU_DIFFICULTY", os.environ.get("SUDOKU_DIFFICULTY", "medium"))
    except Exception:
        enabled = os.environ.get("SUDOKU_ENABLED", "false")
        difficulty = os.environ.get("SUDOKU_DIFFICULTY", "medium")

    if str(enabled).lower() != "true":
        return []

    difficulty = difficulty.lower()
    if difficulty not in _DIFFICULTY_REMOVALS:
        difficulty = "medium"

    puzzle, solution = _generate_puzzle(difficulty)
    previous = _rotate_state(solution, difficulty)

    return [{
        "type": "sudoku",
        "title": f"Sudoku — {difficulty.capitalize()}",
        "source": "Sudoku",
        "published": "",
        "body": "",
        "meta": {
            "puzzle": puzzle,
            "solution": solution,
            "difficulty": difficulty,
            "clues": sum(1 for row in puzzle for v in row if v),
            "previous_solution": (previous or {}).get("solution"),
        },
    }]
