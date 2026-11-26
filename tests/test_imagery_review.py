"""Independent synthetic review cases; no catalogue titles or fixture overrides."""
import xml.etree.ElementTree as ET

import unittest
from functools import wraps

from artwork.draw import drawn_motifs, render_svg
from artwork.extract import extract_imagery
from artwork.generate import plan_artwork
from artwork.normalize import normalize_entry


def extract(en="", zh="", **extra):
    return extract_imagery(normalize_entry({"intro_en": en, "intro_zh": zh, **extra}))


def plan(en="", zh="", **extra):
    return plan_artwork({"id": "review:unseen", "intro_en": en, "intro_zh": zh, **extra})


def figure_heads(svg):
    """Count head primitives independently of motif reporting and recipe counts."""
    return [node for node in ET.fromstring(svg).iter()
            if node.tag.endswith("}circle") and node.get("r") in {"6", "8"}]


def cases(names, rows):
    """Run every fixture under unittest discovery, including stacked dimensions."""
    names = [name.strip() for name in names.split(",")]

    def decorate(method):
        @wraps(method)
        def run(self, **outer):
            for row in rows:
                values = (row,) if len(names) == 1 else row
                params = {**outer, **dict(zip(names, values))}
                with self.subTest(**params):
                    method(self, **params)
        return run
    return decorate


class ImageryReviewTests(unittest.TestCase):
    @cases("en,zh,absent,present", [
        ("There is no war, but love endures.", "", "conflict", "love"),
        ("Not only a family tale: there is no war.", "", "conflict", "family"),
        ("No one finds the letter.", "", "conflict", "letter"),
        ("Without warning, the ghost returns.", "", "conflict", "ghost"),
        ("", "没有战争，只有爱情。", "conflict", "love"),
        ("", "不是一场战争，而是家庭重逢。", "conflict", "reunion"),
        ("", "不仅是爱情故事，也有战争。", "death", "conflict"),
    ])
    def test_clause_local_negation(self, en, zh, absent, present):
        motifs = {hit["motif"] for hit in extract(en, zh)["hits"]}
        assert absent not in motifs
        assert present in motifs


    @cases("title,summary", [
        ("Paper War", '"Paper War" is a musical.'),
        ("战争", "《战争》是一部音乐剧。"),
        ("War", "War is a musical. War is a musical."),
    ])
    def test_title_mentions_are_not_story_evidence(self, title, summary):
        result = plan(summary, title=title)
        assert result["kind"] == "abstract"
        assert result["basis"] == []


    def test_title_prefix_does_not_hide_a_different_word(self):
        result = extract("Lovers cross the square.", title="Love")
        assert result["synopsis_scores"]["love"] >= 1.6


    def test_biography_filter_preserves_character_death(self):
        assert "death" in extract("Her father died in 1932.")["synopsis_scores"]
        assert "death" not in extract("The composer died in 1932.")["synopsis_scores"]
        assert "death" in extract("A composer witnesses a murder.")["synopsis_scores"]


    @cases("text,vehicle", [
        ("Actors train daily.", False),
        ("They train to improve.", False),
        ("Students train for the audition.", False),
        ("We train as acrobats.", False),
        ("Actors board a train daily.", True),
        ("They board a train to the coast.", True),
        ("Students board a train for the audition.", True),
        ("We board a train as the sun rises.", True),
    ])
    def test_train_verb_context_preserves_vehicle_noun(self, text, vehicle):
        hits = [hit for hit in extract(text)["hits"] if hit["motif"] == "train"]
        self.assertEqual(bool(hits), vehicle)
        result = plan(text)
        self.assertEqual("train" in [item["motif"] for item in result["basis"]], vehicle)
        self.assertEqual(result["family"], "route" if vehicle else "abstract")


    def test_boilerplate_cannot_accumulate_into_story(self):
        assert plan("Opened at Palace Theatre. " * 8)["kind"] == "abstract"
        assert plan(zh="首演于宫殿剧院。故事讲述信件。信件被藏起。")["family"] == "still"


    @cases("text,motif", [
        ("A comic created by Clara Woods.", "forest"),
        ("Illustrator Martin King supplied the drawings.", "power"),
        ('The musical includes hits such as "Silver Clock", "Paper Crown" and "Silent Forest".', "forest"),
        ('The songs include "Golden Queen" and "Three Actors".', "power"),
        ("歌曲包括《森林之声》和《国王》。", "power"),
        ("A national tour started in Harbor Island, in September.", "island"),
        ("The revival opened in Cedar Forest.", "forest"),
        ("巡演在森林剧院开始。", "forest"),
    ])
    def test_metadata_contexts_do_not_select_story_motifs(self, text, motif):
        result = extract(text)
        self.assertNotIn(motif, result["synopsis_scores"])
        self.assertTrue(any(hit["motif"] == motif and "meta" in hit["penalties"] for hit in result["hits"]))
        self.assertIsNone(result["count"])
        self.assertEqual(plan(text)["kind"], "abstract")


    @cases("text,motif", [
        ("Created by Clara Woods. A girl enters the forest.", "forest"),
        ('The songs include "Golden Queen". The queen hides a letter.', "power"),
        ('She whispers "the queen is here" before leaving.', "power"),
        ("A tour started in Harbor Island, but the story follows a queen.", "power"),
        ("The characters tour an island.", "island"),
        ("歌曲包括《国王》。故事讲述森林中的家庭。", "forest"),
        ("巡演在森林剧院开始，但故事讲述国王。", "power"),
    ])
    def test_metadata_exclusions_preserve_plot_evidence(self, text, motif):
        self.assertIn(motif, extract(text)["synopsis_scores"])


    @cases("en,zh,expected,extra", [
        ("Two years later three actors perform on stage.", "", 3, {}),
        ("Not two actors. Four stage actors perform.", "", 4, {}),
        ("No war. Three actors perform on stage.", "", 3, {}),
        ("Music by two performers. Four actors perform on stage.", "", 4, {}),
        ('"Eight Actors" is a musical. Three actors perform on stage.', "", 3, {"title": "Eight Actors"}),
        ("", "十二位演员离开。三位演员登上舞台。", 3, {}),
        ("", "没有两位演员，只有四位演员登上舞台。", 4, {}),
        ("", "一位演员独自在舞台上。", 1, {}),
        ("", "3名演员登上舞台。", 3, {}),
        ("", "两位演员登上舞台，八位朋友离开。", 2, {}),
    ])
    def test_count_binds_to_people_not_time_titles_or_credits(self, en, zh, expected, extra):
        assert extract(en, zh, **extra)["count"] == expected
        result = plan(en, zh, **extra)
        assert result["count"] == expected
        assert len(figure_heads(result["svg"])) == expected


    @cases("arrangement", ["together", "apart", "reunion", "conflict", "power", "absence", "ghost", "family"])
    @cases("count", range(9))
    def test_relation_count_matches_actual_svg(self, arrangement, count):
        recipe = {"family": "relation", "subjects": ["family"], "arrangement": arrangement, "count": count}
        heads = figure_heads(render_svg(recipe))
        assert len(heads) == count
        assert len({(head.get("cx"), head.get("cy")) for head in heads}) == count


    @cases("family,subjects", [("portal", ["search"]), ("stage", ["perform"]), ("route", ["travel"])])
    @cases("count", [0, 1, 2, 7, 8])
    def test_other_figure_layouts_keep_explicit_count(self, family, subjects, count):
        assert len(figure_heads(render_svg({"family": family, "subjects": subjects, "count": count}))) == count


    @cases("text", ["Eight actors find a letter.", "Eight actors board a train.", "Eight actors enter a palace.", "Eight actors enter a forest."])
    def test_object_and_landscape_plates_do_not_report_undrawn_people(self, text):
        result = plan(text)
        assert result["count"] == 0
        assert figure_heads(result["svg"]) == []


    def test_ranked_route_subject_is_the_one_drawn(self):
        result = plan("A train passes another train beside a ship.")
        assert result["recipe"]["subjects"][0] == "train"
        assert [item["motif"] for item in result["basis"]] == ["train"]
        assert len([node for node in ET.fromstring(result["svg"]).iter() if node.get("r") == "14"]) == 3


    def test_dance_and_death_have_distinct_drawn_marks(self):
        plain = {"family": "stage", "subjects": ["perform"], "count": 2}
        assert render_svg(plain, structure=True) != render_svg({**plain, "subjects": ["dance"]}, structure=True)
        heaven = {**plain, "modifiers": ["heaven"]}
        assert render_svg(heaven, structure=True) != render_svg({**heaven, "modifiers": ["heaven", "death"]}, structure=True)


    def test_reported_motifs_follow_valid_painter_subjects(self):
        assert drawn_motifs({"family": "still", "subjects": ["ghost"]}) == ["letter"]
        assert drawn_motifs({"family": "terrain", "subjects": ["clock"]}) == ["forest"]
        assert drawn_motifs({"family": "city", "subjects": ["train"]}) == ["city"]
        assert "dance" not in drawn_motifs({"family": "stage", "subjects": ["dance"], "count": 0})


    def test_child_only_evidence_has_a_child_in_svg_and_basis(self):
        result = plan("An orphan waits.")
        assert [item["motif"] for item in result["basis"]] == ["child"]
        assert any(head.get("r") == "6" for head in figure_heads(result["svg"]))

if __name__ == "__main__":
    unittest.main()
