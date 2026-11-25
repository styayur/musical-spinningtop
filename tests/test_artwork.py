import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artwork.compose import compose
from artwork.draw import render_svg
from artwork.extract import extract_imagery
from artwork.generate import annotate_display, generate_library, plan_artwork, resolve_artwork_path
from artwork.normalize import normalize_entry
from artwork.versions import ART_VERSION


def plan(title="Show", intro="", intro_zh="", identity="en:1", **extra):
    return plan_artwork({"id": identity, "title": title, "intro_en": intro, "intro_zh": intro_zh, **extra})


class ImageryTests(unittest.TestCase):
    def test_word_boundaries_and_creator_context(self):
        ward = plan(intro="Joe Patrick Ward is making a crown for the king after winning an award.")
        motifs = {hit["motif"] for hit in ward["hits"]}
        self.assertNotIn("conflict", motifs)
        self.assertIn("crown", motifs)
        self.assertIn("power", motifs)
        boundary = plan(intro="The award went to a working musician who is making notes about the season.")
        self.assertEqual(boundary["hits"], [])
        self.assertEqual(boundary["kind"], "abstract")

    def test_local_negation_and_ambiguous_without(self):
        clear = plan(intro="This is not a love story. It follows a captain at sea.")
        self.assertNotIn("love", clear["recipe"]["subjects"])
        self.assertIn("ocean", {hit["motif"] for hit in clear["hits"]})
        soft = plan(intro="A family survives without love in a small city.")
        love = next(hit for hit in soft["hits"] if hit["motif"] == "love")
        self.assertIn("uncertain-negation", love["penalties"])
        self.assertLess(love["score"], 1)
        self.assertIn("family", soft["recipe"]["subjects"])
        kept = plan(intro="This is not only a love story. Two sisters share a house.")
        self.assertIn("love", {hit["motif"] for hit in kept["hits"]})

    def test_title_cannot_decide_and_meta_is_downweighted(self):
        title = plan("War", intro="A collection of songs performed in concert.")
        self.assertEqual(title["kind"], "abstract")
        self.assertTrue(any(hit["source_field"] == "title" for hit in title["hits"]))
        meta = plan(intro="Music by John London. The story premiered at the Palace Theatre on Broadway. A girl hides a letter.")
        palace = next(hit for hit in meta["hits"] if hit["motif"] == "palace")
        self.assertIn("meta", palace["penalties"])
        self.assertEqual(meta["family"], "still")

    def test_chinese_phrases_and_duplicate_summaries(self):
        row = plan(intro_zh="这不涉及战争，只写一封信件。", intro="ignored")
        self.assertNotIn("conflict", {hit["motif"] for hit in row["hits"]})
        self.assertEqual(row["family"], "still")
        duplicated = normalize_entry({"id": "en:2", "title": "X", "intro_en": "A letter arrives by train.", "intro_zh": "A letter arrives by train."})
        extracted = extract_imagery(duplicated)
        self.assertEqual(sum(1 for hit in extracted["hits"] if hit["motif"] == "letter"), 1)
        self.assertIn("intro_en", duplicated["collapsed"])

    def test_grave_white_way_uses_generic_rules(self):
        row = plan(
            "The Grave White Way",
            "The Grave White Way is a musical theatre stage play written by Joe Patrick Ward. "
            "The show follows five dead stage actors attempting to gain admittance to Heaven by performing.",
            identity="en:54112115",
        )
        self.assertEqual(row["family"], "stage")
        self.assertEqual(row["count"], 5)
        self.assertIn("heaven", row["recipe"]["modifiers"])
        self.assertNotIn("conflict", {hit["motif"] for hit in row["hits"]})
        self.assertNotIn("The Grave White Way", row["svg"])


class DeterminismTests(unittest.TestCase):
    def test_repeat_reorder_and_version(self):
        first = plan(intro="A letter arrives.", identity="en:9")
        second = plan(intro="A letter arrives.", identity="en:9")
        self.assertEqual(first["svg"], second["svg"])
        changed = plan(intro="A ship crosses the ocean.", identity="en:9")
        self.assertNotEqual(first["source_digest"], changed["source_digest"])
        other = plan(intro="A letter arrives.", identity="en:10")
        self.assertNotEqual(first["filename"], other["filename"])
        versioned = plan_artwork({"id": "en:9", "title": "Show", "intro_en": "A letter arrives."}, art_version="test-2")
        self.assertNotEqual(first["recipe_digest"], versioned["recipe_digest"])

    def test_library_order_and_single_edit(self):
        rows = [
            {"id": "en:1", "title": "One", "intro_en": "A letter arrives."},
            {"id": "en:2", "title": "Two", "intro_en": "Five actors perform on stage."},
        ]
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            generate_library(rows, first_dir, "/artwork/")
            generate_library(list(reversed(rows)), second_dir, "/artwork/")
            for name in Path(first_dir).glob("*.svg"):
                self.assertEqual(name.read_bytes(), (Path(second_dir) / name.name).read_bytes())
            edited = [dict(rows[0], intro_en="A ship leaves the harbor."), rows[1]]
            generate_library(edited, first_dir, "/artwork/")
            self.assertNotEqual((Path(first_dir) / plan_artwork(rows[0])["filename"]).read_bytes(),
                                (Path(second_dir) / plan_artwork(rows[0])["filename"]).read_bytes())
            self.assertEqual((Path(first_dir) / plan_artwork(rows[1])["filename"]).read_bytes(),
                             (Path(second_dir) / plan_artwork(rows[1])["filename"]).read_bytes())


class SafetyTests(unittest.TestCase):
    def test_hostile_text_never_enters_svg_or_filename(self):
        hostile = '<script>alert(1)</script> " onclick=alert(1) javascript:alert(1)'
        row = plan(hostile, intro=hostile + " A letter is hidden.", identity="en:99")
        self.assertNotIn("<script", row["svg"].lower())
        self.assertNotIn("onclick", row["svg"].lower())
        self.assertNotIn("javascript:", row["svg"].lower())
        self.assertNotIn(hostile, row["svg"])
        self.assertRegex(row["filename"], r"^[a-f0-9]{20}\.svg$")
        missing = plan_artwork({"title": "../" + hostile, "intro_en": "A door."})
        self.assertEqual(missing["filename"], "base.svg")
        self.assertEqual(missing["reason"], "no-id")

    def test_path_resolution_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "base.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            self.assertIsNotNone(resolve_artwork_path(directory, "base.svg"))
            self.assertIsNone(resolve_artwork_path(directory, "../app.py"))
            self.assertIsNone(resolve_artwork_path(directory, "not a file.svg"))
            self.assertIsNone(resolve_artwork_path(directory, "abcd.svg"))

    def test_display_policy_does_not_treat_a_url_as_permission(self):
        entry = {"image": "https://example.test/a.jpg", "image_source": "https://example.test/file"}
        art = {"artwork_url": "/artwork/abc.svg", "artwork_kind": "generated", "artwork_family": "still", "artwork_basis": [], "artwork_reason": None}
        hidden = annotate_display(entry, art)
        self.assertIsNone(hidden["display_image"])
        self.assertEqual(hidden["image_reuse"], "unverified")
        shown = annotate_display({**entry, "image_reuse": "verified"}, art)
        self.assertEqual(shown["display_image"], entry["image"])
        self.assertNotEqual(shown["artwork_url"], shown["image"])

    def test_new_and_empty_entries_need_no_manual_override(self):
        fresh = plan("A Door by the Sea", "A woman searches for a letter behind a door near the sea.", identity="test:lighthouse-door")
        self.assertEqual(fresh["kind"], "generated")
        self.assertTrue(fresh["basis"])
        empty = plan("Untitled", "", identity="test:empty")
        self.assertEqual(empty["kind"], "abstract")
        self.assertEqual(empty["reason"], "empty")
        self.assertIn("<svg", empty["svg"])

    def test_svg_is_deterministic_markup(self):
        row = plan(intro="A train crosses a bridge.", identity="en:7")
        again = render_svg(row["recipe"])
        self.assertEqual(row["svg"], again)
        self.assertNotIn("http://", row["svg"].replace("http://www.w3.org/2000/svg", ""))
        self.assertLess(len(row["svg"].encode("utf-8")), 60 * 1024)


class CatalogArtworkTests(unittest.TestCase):
    def test_full_snapshot_is_offline_and_covered(self):
        from artwork.normalize import merge_publication
        from catalog import BASE, read_json
        catalog = read_json(BASE / "data" / "catalog.json", {})["musicals"]
        articles = read_json(BASE / "data" / "articles.json", {}).get("articles", {})
        summaries = read_json(BASE / "data" / "summaries_zh.json", {})
        rows = [merge_publication(row, articles.get(row["id"]), summaries.get(row["title"], "")) for row in catalog]
        def blocked(*_args, **_kwargs):
            raise AssertionError("artwork generation used the network")
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=blocked), patch("socket.create_connection", side_effect=blocked):
            manifest = generate_library(rows, directory, "./static/artwork/")
            self.assertEqual(manifest["stats"]["failed"], 0)
            self.assertEqual(manifest["stats"]["total"], len(rows))
            self.assertEqual(len(manifest["items"]), len({row["id"] for row in rows}))
            missing = [row["id"] for row in rows if not (Path(directory) / manifest["items"][row["id"]]["filename"]).is_file()]
            self.assertEqual(missing, [])
            self.assertTrue((Path(directory) / "base.svg").is_file())
            self.assertGreater(manifest["stats"]["generated"], 0)
            self.assertGreater(manifest["stats"]["abstract"], 0)


if __name__ == "__main__":
    unittest.main()
