import hashlib
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from artwork.compose import compose
from artwork.draw import drawn_motifs, render_svg
from artwork.extract import extract_imagery
from artwork.generate import annotate_display, ensure_artwork, generate_library, plan_artwork, resolve_artwork_path
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION
from artwork.normalize import normalize_entry


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

    def test_reported_evidence_edges_use_generic_rules(self):
        echoed = plan("All Out of Love", "All Out of Love is a concert of songs.", identity="en:echo")
        self.assertTrue(any("title-echo" in hit["penalties"] for hit in echoed["hits"] if hit["motif"] == "love"))
        self.assertNotIn("love", echoed["recipe"]["subjects"])
        self.assertEqual(echoed["kind"], "abstract")
        self.assertEqual(echoed["basis"], [])
        venue = plan(intro="Winter Garden Theatre is named in the company history. A letter is hidden.", identity="en:venue")
        self.assertNotIn("garden", {hit["motif"] for hit in venue["hits"]})
        self.assertEqual(venue["family"], "still")
        life = plan(intro="The composer died in 1988. Two sisters are reunited.", identity="en:life")
        self.assertNotIn("death", {hit["motif"] for hit in life["hits"]})
        self.assertEqual(life["count"], 2)
        self.assertEqual(life["recipe"]["arrangement"], "reunion")
        self.assertEqual(life["svg"].count("<circle "), 3)
        self.assertEqual([item["motif"] for item in life["basis"]], ["reunion"])
        actors = plan(intro="Two stage actors perform, not five actors.", identity="en:actors")
        self.assertEqual(actors["count"], 2)
        self.assertEqual(actors["svg"].count("<circle "), 2)
        chinese = plan(intro_zh="不是战争，是爱情。", identity="zh:negation")
        motifs = {hit["motif"] for hit in chinese["hits"]}
        self.assertNotIn("conflict", motifs)
        self.assertIn("love", motifs)
        self.assertIn("love", chinese["basis"][0]["motif"])
        self.assertNotIn("战争", json.dumps(chinese["basis"], ensure_ascii=False))

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
        self.assertRegex(first["filename"], rf"^{ART_VERSION}-{EXTRACTOR_VERSION}-[a-f0-9]{{16}}-[a-f0-9]{{12}}\.svg$")
        self.assertNotEqual(first["filename"], versioned["filename"])

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
            original = plan_artwork(rows[0])
            edited_plan = plan_artwork(edited[0])
            self.assertEqual((Path(first_dir) / original["filename"]).read_bytes(),
                             (Path(second_dir) / original["filename"]).read_bytes())
            self.assertNotEqual((Path(first_dir) / edited_plan["filename"]).read_bytes(),
                                (Path(second_dir) / original["filename"]).read_bytes())
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
        self.assertRegex(row["filename"], rf"^{ART_VERSION}-{EXTRACTOR_VERSION}-[a-f0-9]{{16}}-[a-f0-9]{{12}}\.svg$")
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
        self.assertEqual(empty["basis"], [])
        self.assertEqual(drawn_motifs(empty["recipe"]), [])

    def test_svg_is_deterministic_markup(self):
        row = plan(intro="A train crosses a bridge.", identity="en:7")
        again = render_svg(row["recipe"])
        self.assertEqual(row["svg"], again)
        self.assertNotIn("http://", row["svg"].replace("http://www.w3.org/2000/svg", ""))
        self.assertLess(len(row["svg"].encode("utf-8")), 60 * 1024)

    def test_eight_abstract_layouts_have_distinct_structure(self):
        plates = [
            render_svg({
                "family": "abstract", "subjects": [], "modifiers": [], "arrangement": "",
                "count": 0, "palette": 0, "mirror": False, "detail": 0, "abstract_layout": index,
            }, structure=True)
            for index in range(8)
        ]
        self.assertEqual(len(set(plates)), 8)
        self.assertEqual(drawn_motifs({"family": "abstract", "abstract_layout": 4}), [])

    def test_cache_concurrency_and_distinct_failure_reasons(self):
        entry = {"id": "en:cache", "title": "Cache", "intro_en": "A letter arrives."}
        weak = {"id": "en:weak", "title": "Weak", "intro_en": "A collection of songs performed in concert."}
        with tempfile.TemporaryDirectory() as directory:
            first = ensure_artwork(entry, directory, "/artwork/")
            with patch("artwork.generate.extract_imagery", side_effect=AssertionError("cache hit should not extract")):
                second = ensure_artwork(entry, directory, "/artwork/")
            self.assertEqual(first["artwork_url"], second["artwork_url"])
            self.assertEqual(plan(intro=weak["intro_en"], identity=weak["id"])["reason"], "insufficient")
            with patch("artwork.generate.render_svg", side_effect=RuntimeError("draw failed")):
                failed = generate_library([entry], directory, "/artwork/")
            self.assertEqual(failed["items"][entry["id"]]["reason"], "error")
            self.assertNotEqual(failed["items"][entry["id"]]["reason"], "insufficient")
            rows = [
                {"id": "en:a", "title": "A", "intro_en": "A letter arrives."},
                {"id": "en:b", "title": "B", "intro_en": "A ship crosses the ocean."},
                {"id": "en:c", "title": "C", "intro_en": "Five actors perform on stage."},
            ]
            for _ in range(12):
                with tempfile.TemporaryDirectory() as race_dir:
                    threads = [threading.Thread(target=ensure_artwork, args=(row, race_dir, "/artwork/")) for row in rows]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(5)
                    manifest = json.loads((Path(race_dir) / "manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(set(manifest["items"]), {row["id"] for row in rows})

    def test_late_old_write_does_not_change_new_url_bytes(self):
        new_entry = {"id": "en:race", "title": "Race", "intro_en": "A letter arrives."}
        old_entry = {"id": "en:race", "title": "Race", "intro_en": "A ship crosses the ocean."}
        gate = threading.Event()
        started = threading.Event()
        real_plan = plan_artwork

        def slow_plan(entry, *args, **kwargs):
            if str(entry.get("intro_en", "")).startswith("A ship"):
                started.set()
                self.assertTrue(gate.wait(5))
            return real_plan(entry, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with patch("artwork.generate.plan_artwork", side_effect=slow_plan):
                old_result = {}
                new_result = {}

                def run_old():
                    old_result["value"] = ensure_artwork(old_entry, directory, "/artwork/")

                def run_new():
                    new_result["value"] = ensure_artwork(new_entry, directory, "/artwork/")

                old_thread = threading.Thread(target=run_old)
                old_thread.start()
                self.assertTrue(started.wait(2))
                new_thread = threading.Thread(target=run_new)
                new_thread.start()
                new_thread.join(5)
                published = new_result["value"]
                new_name = published["artwork_file"]
                new_bytes = (Path(directory) / new_name).read_bytes()
                gate.set()
                old_thread.join(5)
            self.assertEqual((Path(directory) / new_name).read_bytes(), new_bytes)
            self.assertIn(new_name, published["artwork_url"])
            again = ensure_artwork(new_entry, directory, "/artwork/")
            self.assertEqual(again["artwork_file"], new_name)
            self.assertEqual((Path(directory) / new_name).read_bytes(), new_bytes)


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
