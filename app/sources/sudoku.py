"""Sudoku puzzle generator source.

Generates a valid Sudoku puzzle at easy/medium/hard difficulty.
Controlled by SUDOKU_ENABLED and SUDOKU_DIFFICULTY settings.
"""

from __future__ import annotations

import logging
import os
import random

logger = logging.getLogger(__name__)

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


def _generate_puzzle(difficulty: str) -> tuple[list[list[int]], list[list[int]]]:
    """Return (puzzle_grid, solution_grid) — 0 represents an empty cell."""
    solution: list[list[int]] = [[0] * 9 for _ in range(9)]
    _fill(solution)

    puzzle = [row[:] for row in solution]
    removals = _DIFFICULTY_REMOVALS.get(difficulty, _DIFFICULTY_REMOVALS["medium"])

    cells = list(range(81))
    random.shuffle(cells)
    for cell in cells[:removals]:
        puzzle[cell // 9][cell % 9] = 0

    return puzzle, solution


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
        },
    }]
