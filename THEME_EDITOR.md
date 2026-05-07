# Newspapersync Theme Editor

A command-line tool for visual editing of newspaper themes without directly modifying template files.

## Overview

The theme editor allows you to:
- Change the newspaper name, theme, font size, and layout
- Preview changes in real-time with HTML previews
- View and understand the color palette and spacing system
- Save configuration to `config/appearance.yml`

## Usage

### Basic Usage

```bash
python theme_editor.py
```

This launches an interactive menu where you can make changes and preview them.

### Menu Options

| Option | Description |
|--------|-------------|
| 1 | Edit newspaper name |
| 2 | Change theme (traditional, retro, readable) |
| 3 | Adjust font size (6-14pt, default 9pt) |
| 4 | Change paper size (A5, A4) |
| 5 | Set number of columns (1 or 2) |
| 6 | Generate preview HTML |
| 7 | Show color palette |
| 8 | Show spacing scale |
| 9 | Save & exit |
| 0 | Exit without saving |

## Available Themes

### Traditional
- **Style**: Classic serif newspaper
- **Font**: Liberation Serif (Georgia)
- **Colors**: Black & white with gray accents
- **Best for**: Professional, timeless look

### Retro
- **Style**: 80s-inspired monospace newsletter
- **Font**: Liberation Mono (Courier)
- **Colors**: Warm amber on cream (#fdf6e3)
- **Best for**: Nostalgic, retro aesthetic

### Readable
- **Style**: Dyslexia-friendly with generous spacing
- **Font**: OpenDyslexic or DejaVu Sans
- **Colors**: Warm, high-contrast palette
- **Best for**: Accessibility, maximum readability

## Configuration Files

### appearance.yml

The main theme configuration file located at `config/appearance.yml`:

```yaml
newspaper_name: "The Daily Digest"
theme: "traditional"              # traditional, retro, readable
font_size: 9                       # points (6-14 recommended)
paper_size: "A5"                   # A5, A4
columns: 1                         # 1 or 2
colors:
  traditional:
    text: "#111"
    background: "#fff"
    accent: "#444"
    borders: "#888"
  retro:
    text: "#1a0a00"
    background: "#fdf6e3"
    accent: "#8b4513"
    borders: "#c8a87a"
  readable:
    text: "#1a1208"
    background: "#faf8f2"
    accent: "#6b5c42"
    borders: "#c8b89a"
spacing:
  xs: 2      # extra small (2pt)
  sm: 4      # small (4pt)
  md: 8      # medium (8pt)
  lg: 12     # large (12pt)
  xl: 16     # extra large (16pt)
  2xl: 20    # 2x large (20pt)
  3xl: 24    # 3x large (24pt)
```

## Theme Preview

The theme editor can generate an HTML preview file (`theme_preview.html`) showing:
- How your current theme configuration looks
- Sample masthead and articles
- Typography hierarchy
- Spacing demonstrations

To generate a preview:
1. Run `python theme_editor.py`
2. Select option 6 (Generate preview HTML)
3. Open `theme_preview.html` in a web browser
4. The preview updates based on your configuration

## Spacing System

The newspaper uses a **4-point grid system** for consistent spacing:

```
xs (2pt)   ██
sm (4pt)   ████
md (8pt)   ████████
lg (12pt)  ████████████
xl (16pt)  ████████████████
2xl (20pt) ████████████████████
3xl (24pt) ████████████████████████
```

All margins, padding, and gaps throughout the newspaper are multiples of the base 4pt unit.

## Weather Icons

The newspaper now displays weather condition icons in the forecast:

- ☀️ Clear sky
- 🌤️ Mainly clear
- ⛅ Partly cloudy
- ☁️ Overcast
- 🌫️ Fog
- 🌧️ Rain
- ❄️ Snow
- ⛈️ Thunderstorm

Icons are displayed at prominent sizes (14pt) in the hourly forecast.

## Programmatic Usage

You can also use the theme configuration in Python code:

```python
from app.theming import ThemeConfig
from pathlib import Path

# Load configuration
config = ThemeConfig(Path("config/appearance.yml"))

# Get values
name = config.get("newspaper_name")
theme = config.get("theme")
font_size = config.get("font_size")

# Get theme colors
colors = config.get_theme_colors()
accent_color = colors["accent"]

# Get spacing
gap = config.get_spacing("md")  # Returns 8

# Validate configuration
is_valid, errors = config.validate()
if not is_valid:
    for error in errors:
        print(f"Configuration error: {error}")
```

## Tips

1. **Font Size**: Recommended range is 8-10pt for A5 paper, 10-12pt for A4
2. **Paper Size**: A5 is optimized for reMarkable tablets, A4 for standard printing
3. **Columns**: Single column (1) is more readable, two columns (2) fits more content
4. **Theme Selection**: Try all three themes to find the one that matches your preference
5. **Custom Colors**: To customize colors beyond the presets, edit `config/appearance.yml` directly

## Troubleshooting

**Q: The theme changes aren't showing in the newspaper**
A: Make sure you saved the configuration (option 9) before generating a new newspaper.

**Q: The preview HTML looks different from the actual PDF**
A: The preview is approximate. Some features (like page breaks) only appear in the PDF output.

**Q: Can I create custom themes?**
A: Currently, you can edit colors and spacing directly in `config/appearance.yml`. To create a completely new theme, modify the template CSS in `app/templates/newspaper.html`.

## Related Files

- **`theme_editor.py`** - Interactive theme editor (this tool)
- **`app/theming.py`** - Theme configuration utilities
- **`app/templates/newspaper.html`** - Newspaper template (theme CSS: lines 6-404)
- **`config/appearance.yml`** - Active theme configuration
