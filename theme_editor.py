#!/usr/bin/env python3
"""
Interactive theme editor for Newspapersync.

This tool allows visual editing of newspaper themes without direct template editing.
Generates a preview HTML file that shows how changes look in real-time.

Usage:
    python theme_editor.py
    python theme_editor.py --export config.yml
    python theme_editor.py --preview
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml


def get_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / "config").exists() and (current / "app").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root. Run from the Newspapersync directory.")


PROJECT_ROOT = get_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "appearance.yml"


# Default theme configuration
DEFAULT_CONFIG = {
    "newspaper_name": "The Daily Digest",
    "theme": "traditional",  # traditional, retro, readable
    "font_size": 9,  # points
    "paper_size": "A5",  # A5, A4
    "columns": 1,  # 1, 2
    # Theme-specific colors (for future expansion)
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
    # Spacing scale (in points)
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


class ThemeEditor:
    """Interactive theme editor with preview generation."""

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load current configuration or return defaults."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                loaded = yaml.safe_load(f) or {}
            # Merge with defaults
            merged = DEFAULT_CONFIG.copy()
            merged.update(loaded)
            return merged
        return DEFAULT_CONFIG.copy()

    def save_config(self) -> None:
        """Save current configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        print(f"✓ Configuration saved to {self.config_path}")

    def print_menu(self) -> None:
        """Print the main menu."""
        print("\n" + "=" * 60)
        print("NEWSPAPERSYNC THEME EDITOR")
        print("=" * 60)
        print(f"\nCurrent Configuration:")
        print(f"  📰 Newspaper Name: {self.config['newspaper_name']}")
        print(f"  🎨 Theme: {self.config['theme']}")
        print(f"  📏 Font Size: {self.config['font_size']}pt")
        print(f"  📄 Paper Size: {self.config['paper_size']}")
        print(f"  📋 Columns: {self.config['columns']}")
        print(f"\nOptions:")
        print(f"  1. Edit newspaper name")
        print(f"  2. Change theme (traditional, retro, readable)")
        print(f"  3. Adjust font size ({self.config['font_size']}pt)")
        print(f"  4. Change paper size ({self.config['paper_size']})")
        print(f"  5. Set number of columns ({self.config['columns']})")
        print(f"  6. Generate preview HTML")
        print(f"  7. Show color palette")
        print(f"  8. Show spacing scale")
        print(f"  9. Save & exit")
        print(f"  0. Exit without saving")

    def edit_newspaper_name(self) -> None:
        """Edit the newspaper name."""
        current = self.config["newspaper_name"]
        new_name = input(f"\nEnter newspaper name (current: '{current}'): ").strip()
        if new_name:
            self.config["newspaper_name"] = new_name
            print(f"✓ Newspaper name updated to '{new_name}'")

    def change_theme(self) -> None:
        """Change the theme."""
        themes = ["traditional", "retro", "readable"]
        print(f"\nAvailable themes:")
        for i, theme in enumerate(themes, 1):
            marker = "●" if theme == self.config["theme"] else "○"
            print(f"  {marker} {i}. {theme}")

        try:
            choice = input("Select theme (1-3): ").strip()
            if choice in ["1", "2", "3"]:
                self.config["theme"] = themes[int(choice) - 1]
                print(f"✓ Theme changed to '{self.config['theme']}'")
        except (ValueError, IndexError):
            print("Invalid selection.")

    def adjust_font_size(self) -> None:
        """Adjust the font size."""
        current = self.config["font_size"]
        try:
            size = int(input(f"\nEnter font size in points (current: {current}, recommended: 8-10): ").strip())
            if 6 <= size <= 14:
                self.config["font_size"] = size
                print(f"✓ Font size updated to {size}pt")
            else:
                print("Font size should be between 6 and 14 points.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    def change_paper_size(self) -> None:
        """Change paper size."""
        sizes = ["A5", "A4"]
        print(f"\nAvailable paper sizes:")
        for i, size in enumerate(sizes, 1):
            marker = "●" if size == self.config["paper_size"] else "○"
            print(f"  {marker} {i}. {size}")

        try:
            choice = input("Select paper size (1-2): ").strip()
            if choice in ["1", "2"]:
                self.config["paper_size"] = sizes[int(choice) - 1]
                print(f"✓ Paper size changed to {self.config['paper_size']}")
        except (ValueError, IndexError):
            print("Invalid selection.")

    def set_columns(self) -> None:
        """Set number of columns."""
        print(f"\nColumn layouts:")
        print(f"  ○ 1. Single column (better readability)")
        print(f"  ○ 2. Two columns (more compact)")

        try:
            choice = input("Select columns (1-2): ").strip()
            if choice in ["1", "2"]:
                self.config["columns"] = int(choice)
                print(f"✓ Layout changed to {int(choice)} column(s)")
        except (ValueError, IndexError):
            print("Invalid selection.")

    def show_color_palette(self) -> None:
        """Display the color palette for the current theme."""
        theme = self.config["theme"]
        colors = self.config["colors"].get(theme, {})

        print(f"\n{'=' * 60}")
        print(f"COLOR PALETTE — {theme.upper()} THEME")
        print(f"{'=' * 60}")
        for name, color in colors.items():
            print(f"  {name.ljust(12)}: {color}")
        print(f"\nNote: To edit colors, modify config/appearance.yml directly.")

    def show_spacing_scale(self) -> None:
        """Display the spacing scale."""
        spacing = self.config["spacing"]

        print(f"\n{'=' * 60}")
        print(f"SPACING SCALE (Grid-based 4pt system)")
        print(f"{'=' * 60}")
        for name, size in spacing.items():
            bar = "█" * (size // 2)
            print(f"  {name.ljust(4)}: {size:2d}pt {bar}")

    def generate_preview(self) -> None:
        """Generate an HTML preview of the current theme configuration."""
        theme = self.config["theme"]
        font_size = self.config["font_size"]
        columns = self.config["columns"]

        # Map theme to example colors
        theme_colors = self.config["colors"].get(theme, {})

        preview_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Newspapersync Theme Preview — {theme.title()}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: {self._get_font_family(theme)};
            font-size: {font_size}pt;
            line-height: 1.5;
            color: {theme_colors.get('text', '#000')};
            background: {theme_colors.get('background', '#fff')};
            padding: 20px;
        }}

        .preview-container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border: 1px solid #ddd;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .masthead {{
            text-align: center;
            border-top: 3px solid {theme_colors.get('accent', '#000')};
            border-bottom: 1px solid {theme_colors.get('accent', '#000')};
            padding: 8pt 0;
            margin-bottom: 16pt;
        }}

        .masthead h1 {{
            font-size: {font_size * 2.4:.0f}pt;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}

        .masthead p {{
            font-size: {font_size - 1}pt;
            color: {theme_colors.get('accent', '#666')};
            margin-top: 4pt;
        }}

        .section-header {{
            font-size: {font_size - 1.5:.0f}pt;
            font-weight: bold;
            text-transform: uppercase;
            border-top: 2px solid {theme_colors.get('accent', '#000')};
            border-bottom: 1px solid {theme_colors.get('borders', '#999')};
            padding: 8pt 0;
            margin: 16pt 0 12pt;
            color: {theme_colors.get('accent', '#000')};
            letter-spacing: 0.12em;
        }}

        .sample-article {{
            margin-bottom: 12pt;
            padding-bottom: 8pt;
            border-bottom: 1px dotted {theme_colors.get('borders', '#ccc')};
        }}

        .sample-article:last-child {{ border-bottom: none; }}

        .article-title {{
            font-size: {font_size}pt;
            font-weight: bold;
            margin-bottom: 4pt;
        }}

        .article-meta {{
            font-size: {font_size - 2.5:.0f}pt;
            color: {theme_colors.get('accent', '#888')};
            margin-bottom: 4pt;
        }}

        .article-body {{
            font-size: {font_size - 1}pt;
            line-height: 1.4;
            color: {theme_colors.get('text', '#222')};
        }}

        .theme-info {{
            background: #f5f5f5;
            border-left: 4px solid {theme_colors.get('accent', '#999')};
            padding: 12px;
            margin-top: 20px;
            font-size: 12px;
            color: #666;
        }}

        .spacing-demo {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px solid #eee;
        }}

        .spacing-box {{
            background: {theme_colors.get('accent', '#ddd')};
            color: white;
            padding: 8px;
            margin-bottom: 8px;
            text-align: center;
            opacity: 0.3;
        }}
    </style>
</head>
<body>
    <div class="preview-container">
        <div class="masthead">
            <h1>{self.config['newspaper_name']}</h1>
            <p>Theme Preview</p>
        </div>

        <div class="section-header">Sample Section</div>

        <div class="sample-article">
            <div class="article-title">This is a sample headline</div>
            <div class="article-meta">by Example Author · Today</div>
            <div class="article-body">
                This is sample body text to show you how your newspaper will look with
                the current theme settings. The font size is {font_size}pt and the theme
                is "{theme}". Adjust the settings to see how the layout changes.
            </div>
        </div>

        <div class="sample-article">
            <div class="article-title">Another sample article</div>
            <div class="article-meta">by Example Author · Today</div>
            <div class="article-body">
                This demonstrates spacing and typography consistency across multiple
                articles. The column layout is set to {columns} column(s).
            </div>
        </div>

        <div class="spacing-demo">
            <strong style="color: {theme_colors.get('accent', '#000')};">Spacing Scale (4pt grid):</strong>
            <div style="margin-top: 8px;">
                <div class="spacing-box" style="height: 4px; margin-bottom: 4px;"></div>
                <div class="spacing-box" style="height: 8px; margin-bottom: 8px;"></div>
                <div class="spacing-box" style="height: 12px; margin-bottom: 12px;"></div>
                <div class="spacing-box" style="height: 16px; margin-bottom: 16px;"></div>
            </div>
        </div>

        <div class="theme-info">
            <strong>Theme Configuration:</strong><br>
            Theme: {theme} | Font: {font_size}pt | Columns: {columns} | Paper: {self.config['paper_size']}
        </div>
    </div>
</body>
</html>"""

        preview_path = Path("theme_preview.html")
        with open(preview_path, "w") as f:
            f.write(preview_html)

        print(f"\n✓ Preview generated: {preview_path.absolute()}")
        print(f"  Open this file in a browser to see the theme preview.")

    def _get_font_family(self, theme: str) -> str:
        """Get appropriate font family for theme."""
        fonts = {
            "traditional": '"Liberation Serif", "Georgia", serif',
            "retro": '"Liberation Mono", "Courier New", monospace',
            "readable": '"OpenDyslexic", "DejaVu Sans", sans-serif',
        }
        return fonts.get(theme, '"System Font", sans-serif')

    def run(self) -> None:
        """Run the interactive editor."""
        while True:
            self.print_menu()
            choice = input("\nEnter your choice (0-9): ").strip()

            if choice == "1":
                self.edit_newspaper_name()
            elif choice == "2":
                self.change_theme()
            elif choice == "3":
                self.adjust_font_size()
            elif choice == "4":
                self.change_paper_size()
            elif choice == "5":
                self.set_columns()
            elif choice == "6":
                self.generate_preview()
            elif choice == "7":
                self.show_color_palette()
            elif choice == "8":
                self.show_spacing_scale()
            elif choice == "9":
                self.save_config()
                print("\n✓ Theme editor closed. Configuration saved.")
                break
            elif choice == "0":
                confirm = input("Are you sure you want to exit without saving? (y/n): ").strip().lower()
                if confirm == "y":
                    print("Exiting without saving.")
                    break
            else:
                print("Invalid choice. Please try again.")


def main():
    """Main entry point."""
    try:
        editor = ThemeEditor()
        editor.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
