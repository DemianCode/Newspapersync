"""Sample newspaper — renders every section with realistic mock data.

Used to review the report design without any sources configured:

    python -m app.sample                       # traditional, A5 → sample.pdf
    python -m app.sample --theme retro --paper A4 --columns 2 --out retro.pdf
    python -m app.sample --all docs/samples    # every theme, one PDF each
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_PAGE_CSS = {
    "A5": "@page { size: A5 portrait; margin: 12mm 14mm; }",
    "A4": "@page { size: A4 portrait; margin: 18mm 20mm; }",
}

_PUZZLE = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
]


_SOLUTION = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2], [6, 7, 2, 1, 9, 5, 3, 4, 8], [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3], [4, 2, 6, 8, 5, 3, 7, 9, 1], [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4], [2, 8, 7, 4, 1, 9, 6, 3, 5], [3, 4, 5, 2, 8, 6, 1, 7, 9],
]


def _article(source: str, title: str, body: str, published: str, ai: bool = False,
             image_url: str | None = None) -> dict:
    return {"type": "article", "source": source, "title": title, "body": body,
            "published": published, "image_url": image_url, "ai_summarised": ai, "meta": {}}


# A stand-in comic panel, inline so the sample renders offline.
_COMIC = "data:image/svg+xml;utf8," + (
    "<svg xmlns='http://www.w3.org/2000/svg' width='360' height='120' viewBox='0 0 360 120'>"
    "<rect x='1' y='1' width='358' height='118' fill='white' stroke='black' stroke-width='2'/>"
    "<line x1='120' y1='1' x2='120' y2='119' stroke='black' stroke-width='2'/>"
    "<line x1='240' y1='1' x2='240' y2='119' stroke='black' stroke-width='2'/>"
    "<g fill='none' stroke='black' stroke-width='2'>"
    "<circle cx='60' cy='50' r='10'/><path d='M60 60v28M60 70l-14 10M60 70l14 10M60 88l-10 20M60 88l10 20'/>"
    "<circle cx='180' cy='50' r='10'/><path d='M180 60v28M180 70l-14-8M180 70l14-8M180 88l-10 20M180 88l10 20'/>"
    "<circle cx='300' cy='50' r='10'/><path d='M300 60v28M300 70l-14 10M300 70l14 10M300 88l-10 20M300 88l10 20'/>"
    "</g><text x='60' y='22' font-family='sans-serif' font-size='11' text-anchor='middle'>Hmm.</text>"
    "<text x='180' y='22' font-family='sans-serif' font-size='11' text-anchor='middle'>Aha!</text>"
    "<text x='300' y='22' font-family='sans-serif' font-size='11' text-anchor='middle'>Hmm.</text></svg>"
).replace("#", "%23").replace(" ", "%20").replace("<", "%3C").replace(">", "%3E").replace("'", "%27")


def sample_context(theme: str = "traditional", paper: str = "A5",
                   columns: int = 1, font_size: int = 9) -> dict:
    """Return a context dict shaped exactly like ``aggregator.collect``'s."""
    now = datetime.now()
    tasks = [
        {"type": "task", "source": "TickTick", "title": "Renew car registration",
         "body": "Online form needs the licence number from the glovebox.",
         "published": "2 days overdue", "meta": {"overdue": True, "priority": 5, "project": "Admin", "due_time": ""}},
        {"type": "task", "source": "TickTick", "title": "Send quarterly figures to Priya",
         "body": "", "published": "Today 14:30", "meta": {"overdue": False, "priority": 5, "project": "Work", "due_time": "14:30"}},
        {"type": "task", "source": "TickTick", "title": "Pick up dry cleaning",
         "body": "", "published": "Today", "meta": {"overdue": False, "priority": 1, "project": "Personal", "due_time": ""}},
        {"type": "task", "source": "TickTick", "title": "Book dentist for October",
         "body": "", "published": "Today", "meta": {"overdue": False, "priority": 0, "project": "", "due_time": ""}},
    ]
    emails = [
        {"type": "email", "source": "Email", "title": "Re: Friday offsite — venue confirmed",
         "body": "Great news, the boathouse is booked from 10 until 4. Lunch is included; "
                 "can you let me know dietary requirements by Wednesday?",
         "published": "07:12", "meta": {"from": "Alex Morgan", "unread_total": 12}},
        {"type": "email", "source": "Email", "title": "Your September statement is ready",
         "body": "Your statement for the period ending 20 September is now available.",
         "published": "Yesterday 18:40", "meta": {"from": "Northside Bank"}},
        {"type": "email", "source": "Email", "title": "Weekend plans?",
         "body": "Thinking of the coast walk on Saturday if the weather holds. Keen?",
         "published": "Yesterday 21:05", "meta": {"from": "Sam Chen"}},
    ]
    feeds = {
        "The Guardian": [
            _article("The Guardian", "Central bank holds rates steady as inflation eases for third month",
                     "Policymakers voted 7–2 to keep the cash rate unchanged, citing a gradual cooling in "
                     "services inflation and a softer labour market. Markets now price a first cut in early "
                     "spring, though the governor warned against reading too much into a single quarter.",
                     "06:30"),
            _article("The Guardian", "Coastal towns trial car-free weekends to ease summer congestion",
                     "Three councils will close their seafront roads on Saturdays and Sundays through "
                     "March, with extra shuttle buses running from park-and-ride sites.",
                     "05:10"),
        ],
        "Ars Technica": [
            _article("Ars Technica", "New e-ink panels promise colour at half the power draw",
                     "The display maker says its next generation of electrophoretic screens refreshes "
                     "in under 200ms and holds an image with zero power, making it a candidate for "
                     "tablets, shelf labels and transit signage.",
                     "Yesterday 22:15", ai=True),
            _article("Ars Technica", "Open-source maintainers push back on AI-generated bug reports",
                     "Several prominent projects have introduced disclosure rules after a flood of "
                     "low-quality automated submissions consumed volunteer triage time.",
                     "Yesterday 19:02"),
        ],
        "xkcd": [
            _article("xkcd", "Eureka",
                     "Every breakthrough is followed immediately by a second, slightly larger question.",
                     "Yesterday 04:00", image_url=_COMIC),
        ],
        "BBC Science": [
            _article("BBC Science", "Deep-sea survey finds dozens of species new to science",
                     "Researchers aboard a six-week expedition catalogued sea cucumbers, sponges and a "
                     "translucent octopus at depths of more than four kilometres.",
                     "Yesterday 16:45"),
        ],
    }
    jobs = [
        {"type": "job", "title": "Senior Data Engineer", "source": "Seek",
         "body": "Build and own batch and streaming pipelines on a modern cloud stack. "
                 "Hybrid, two days in the office.",
         "published": "23 Sep 2026",
         "meta": {"url": "https://www.seek.com.au/job/81234567", "company": "Harbour Analytics",
                  "location": "Sydney NSW", "salary": "$160k – $180k + super",
                  "rating": 4.5, "rating_stars": "★★★★☆", "is_new": True}},
        {"type": "job", "title": "Platform Engineer (Python)", "source": "Workday",
         "body": "Join a small team running internal developer tooling and CI infrastructure.",
         "published": "22 Sep 2026",
         "meta": {"url": "https://careers.example.org/job/R-10442", "company": "Meridian Health",
                  "location": "Remote", "salary": "", "rating": 3.8,
                  "rating_stars": "★★★★☆", "is_new": True}},
    ]
    weather = {
        "type": "weather", "source": "Open-Meteo", "title": "Forecast — Sydney",
        "body": "Partly cloudy.",
        "meta": {
            "location": "Sydney", "temp_symbol": "°C", "condition": "Partly cloudy, clearing by evening",
            "icon": "partly-cloudy", "high": 23, "low": 14, "feels_high": 22, "feels_low": 12,
            "precip_chance": 20, "precip_sum": 0.4, "wind_max": 24, "wind_unit": "km/h",
            "uv_max": 7, "uv_label": "High",
            "sunrise": "05:47", "sunset": "17:58",
            "day_parts": [
                {"label": "Morning", "time": "09:00", "temp": 17, "precip": 10, "icon": "mostly-clear"},
                {"label": "Afternoon", "time": "15:00", "temp": 22, "precip": 20, "icon": "partly-cloudy"},
                {"label": "Evening", "time": "18:00", "temp": 19, "precip": 30, "icon": "showers"},
                {"label": "Night", "time": "21:00", "temp": 15, "precip": 5, "icon": "clear"},
            ],
            "tomorrow": {"high": 20, "low": 13, "condition": "Light rain", "icon": "rain", "precip": 70},
        },
    }
    return {
        "generated_at": now.strftime("%A, %d %B %Y"),
        "generated_time": now.strftime("%H:%M"),
        "issue_no": now.timetuple().tm_yday,
        "weather": weather,
        "tasks": tasks,
        "emails": emails,
        "feeds": feeds,
        "lessons": [{
            "type": "lesson", "source": "Spanish Basics", "title": "Ser vs. estar",
            "body": "Both mean “to be”. Use ser for identity and lasting traits (Soy profesora), "
                    "and estar for location and temporary states (Estoy cansada).",
            "published": "Lesson 7 of 30",
            "meta": {"lesson_num": 7, "total_lessons": 30, "course_name": "Spanish Basics"},
        }],
        "shell_outputs": [{
            "type": "shell", "source": "Shell", "title": "Disk usage",
            "body": "Filesystem  Size  Used Avail Use%\n/dev/md1    8.0T  5.1T  2.9T  64%\n/dev/md2    4.0T  3.7T  0.3T  93%",
            "meta": {"error": None},
        }, {
            "type": "shell", "source": "Shell", "title": "Backup check",
            "body": "last snapshot: 2026-09-23 02:00 (ok)\nverifying… 1 file changed since snapshot",
            "meta": {"error": "Exit 1: /mnt/backup/offsite not mounted"},
        }],
        "sudoku": {"type": "sudoku", "title": "Sudoku — Medium", "source": "Sudoku", "published": "",
                   "body": "", "meta": {"puzzle": _PUZZLE, "solution": _SOLUTION, "difficulty": "medium",
                                         "clues": sum(1 for r in _PUZZLE for v in r if v),
                                         "previous_solution": _SOLUTION}},
        "wikipedia": {
            "type": "wikipedia", "source": "Wikipedia", "title": "Lighthouse of Alexandria",
            "body": "The Lighthouse of Alexandria, sometimes called the Pharos of Alexandria, was a "
                    "lighthouse built by the Ptolemaic Kingdom during the reign of Ptolemy II "
                    "Philadelphus (280–247 BC). It has been estimated to have been at least 100 metres "
                    "in overall height. One of the Seven Wonders of the Ancient World, for many "
                    "centuries it was one of the tallest man-made structures in the world.",
            "published": "Article of the Day",
            "meta": {"thumbnail": None, "description": "ancient lighthouse in Alexandria, Egypt",
                     "on_this_day": [
                         {"year": 1066, "text": "Harald Hardrada's Norwegian army landed in Yorkshire, days before the Battle of Stamford Bridge."},
                         {"year": 1869, "text": "Black Friday: gold prices collapsed on the New York Gold Exchange after a failed attempt to corner the market."},
                         {"year": 1996, "text": "Representatives of 71 nations signed the Comprehensive Nuclear-Test-Ban Treaty at the United Nations."},
                     ]},
        },
        "wikiquote": {
            "type": "wikiquote", "source": "Wikiquote", "title": "Quote of the Day",
            "body": "The best way out is always through.", "published": "Quote of the Day",
            "meta": {"attribution": "Robert Frost"},
        },
        "word_of_the_day": {
            "type": "word_of_the_day", "source": "Merriam-Webster", "title": "sonder",
            "body": "The realisation that each passer-by has a life as vivid and complex as your own.",
            "published": "Word of the Day",
            "meta": {"pronunciation": "SAHN-der", "part_of_speech": "noun",
                     "example": "Watching the commuters stream past the café window, she felt a quiet sense of sonder.",
                     "did_you_know": "The word was coined in 2012 for an online dictionary of invented words, and escaped into everyday use."},
        },
        "job_blocks": jobs,
        "edition_name": "Morning",
        "all_blocks": [],
        "config": {"newspaper_name": "The Daily Digest", "theme": theme,
                   "font_size": font_size, "paper_size": paper, "columns": columns},
    }


def render(out: Path, **opts) -> Path:
    from weasyprint import CSS, HTML

    ctx = sample_context(**opts)
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)),
                      autoescape=select_autoescape(["html"]))
    html = env.get_template("newspaper.html").render(**ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf(
        str(out), stylesheets=[CSS(string=_PAGE_CSS.get(ctx["config"]["paper_size"], _PAGE_CSS["A5"]))])
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--theme", default="traditional", choices=["traditional", "retro", "readable"])
    p.add_argument("--paper", default="A5", choices=["A5", "A4"])
    p.add_argument("--columns", type=int, default=1, choices=[1, 2])
    p.add_argument("--font-size", type=int, default=9)
    p.add_argument("--out", default="sample.pdf")
    p.add_argument("--all", metavar="DIR", help="render every theme into DIR")
    a = p.parse_args()

    if a.all:
        for theme in ("traditional", "retro", "readable"):
            print(render(Path(a.all) / f"sample-{theme}.pdf", theme=theme, paper=a.paper,
                         columns=a.columns, font_size=a.font_size))
    else:
        print(render(Path(a.out), theme=a.theme, paper=a.paper,
                     columns=a.columns, font_size=a.font_size))


if __name__ == "__main__":
    main()
