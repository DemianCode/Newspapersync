"""Theme management and utilities for Newspapersync.

This module provides utilities for loading, validating, and applying theme configurations.
The theme editor tool (theme_editor.py) uses this module to manage theme settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
import yaml
import logging

logger = logging.getLogger(__name__)


class ThemeConfig:
    """Manages theme configuration loading and validation."""

    # Default configuration
    DEFAULTS = {
        "newspaper_name": "The Daily Digest",
        "theme": "traditional",  # traditional, retro, readable
        "font_size": 9,  # points
        "paper_size": "A5",  # A5, A4
        "columns": 1,  # 1, 2
        "colors": {
            "traditional": {
                "text": "#111",
                "background": "#fff",
                "accent": "#444",
                "borders": "#888",
            },
            "retro": {
                "text": "#1a0a00",
                "background": "#fdf6e3",
                "accent": "#8b4513",
                "borders": "#c8a87a",
            },
            "readable": {
                "text": "#1a1208",
                "background": "#faf8f2",
                "accent": "#6b5c42",
                "borders": "#c8b89a",
            },
        },
        "spacing": {
            "xs": 2,
            "sm": 4,
            "md": 8,
            "lg": 12,
            "xl": 16,
            "2xl": 20,
            "3xl": 24,
        },
    }

    VALID_THEMES = ["traditional", "retro", "readable"]
    VALID_PAPER_SIZES = ["A5", "A4"]
    VALID_COLUMN_COUNTS = [1, 2]

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize theme config.

        Args:
            config_path: Path to appearance.yml. If None, uses default config.
        """
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = yaml.safe_load(f) or {}
                # Merge with defaults
                config = self.DEFAULTS.copy()
                config.update(loaded)
                logger.debug(f"Loaded theme config from {self.config_path}")
                return config
            except Exception as e:
                logger.warning(f"Failed to load theme config: {e}. Using defaults.")
                return self.DEFAULTS.copy()
        return self.DEFAULTS.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default or self.DEFAULTS.get(key))

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the configuration.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Validate theme
        theme = self.config.get("theme", "traditional")
        if theme not in self.VALID_THEMES:
            errors.append(f"Invalid theme '{theme}'. Must be one of: {', '.join(self.VALID_THEMES)}")

        # Validate font size
        font_size = self.config.get("font_size", 9)
        if not isinstance(font_size, (int, float)) or font_size < 6 or font_size > 20:
            errors.append(f"Font size must be between 6 and 20, got {font_size}")

        # Validate paper size
        paper_size = self.config.get("paper_size", "A5")
        if paper_size not in self.VALID_PAPER_SIZES:
            errors.append(f"Invalid paper size '{paper_size}'. Must be one of: {', '.join(self.VALID_PAPER_SIZES)}")

        # Validate columns
        columns = self.config.get("columns", 1)
        if columns not in self.VALID_COLUMN_COUNTS:
            errors.append(f"Columns must be one of: {', '.join(map(str, self.VALID_COLUMN_COUNTS))}, got {columns}")

        return len(errors) == 0, errors

    def get_theme_colors(self) -> Dict[str, str]:
        """Get color palette for the current theme."""
        theme = self.config.get("theme", "traditional")
        colors = self.config.get("colors", self.DEFAULTS["colors"])
        return colors.get(theme, colors.get("traditional", {}))

    def get_spacing(self, level: str) -> int:
        """Get spacing value for a given level (xs, sm, md, lg, xl, 2xl, 3xl)."""
        spacing = self.config.get("spacing", self.DEFAULTS["spacing"])
        return spacing.get(level, self.DEFAULTS["spacing"].get(level, 0))

    def as_dict(self) -> Dict[str, Any]:
        """Return the full configuration dictionary."""
        return self.config.copy()

    def to_yaml(self) -> str:
        """Return configuration as YAML string."""
        return yaml.dump(self.config, default_flow_style=False, sort_keys=False)
