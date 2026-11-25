"""Offline artwork generator shared by the static site and the local app."""
from artwork.generate import annotate_display, ensure_artwork, generate_library, plan_artwork
from artwork.normalize import merge_publication, normalize_entry
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION

__all__ = [
    "ART_VERSION",
    "EXTRACTOR_VERSION",
    "annotate_display",
    "ensure_artwork",
    "generate_library",
    "merge_publication",
    "normalize_entry",
    "plan_artwork",
]
