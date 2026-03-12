# Sources package — each module exposes a fetch() -> list[dict] interface.
# All fetch functions return a list of content blocks consumed by the aggregator.
#
# Block schema (all fields optional except 'type'):
# {
#   "type": str,          # "article" | "weather" | "task" | "email" | "section_header"
#   "source": str,        # display name of origin
#   "title": str,
#   "body": str,
#   "url": str,
#   "published": str,     # ISO datetime string or human-readable
#   "meta": dict,         # source-specific extras
# }
