import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from app import create_app
from build_site import build


class PublicationParityTests(unittest.TestCase):
    def test_both_entries_publish_identical_bytes_after_summary_updates(self):
        entries = [
            {"id": "test:english", "title": "Example", "wiki": "Example", "wiki_url": "https://example.org/work"},
            {"id": "test:embedded", "title": "Embedded", "intro_en": "Two sisters are reunited."},
        ]
        articles = {"test:english": {"intro_en": "A letter arrives.", "intro_zh": "", "translator": "none", "detail_status": "ready"}}
        for summary in ("", "两位姐妹重逢。", "一封信件藏在门后。"):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as directory:
                application = create_app(Path(directory) / "runtime", background=False)
                library = application.extensions["library"]
                library.entries = entries
                library.bundled_details = articles
                application.extensions["store"].save_details("test:english", articles["test:english"])

                def source(path, default=None):
                    if Path(path).name == "summaries_zh.json":
                        return {"Example": summary}
                    if Path(path).name == "articles.json":
                        return {"articles": articles}
                    return default

                try:
                    with patch("build_site.load_catalog", return_value=(entries, "2026-11-26")), patch("build_site.read_json", side_effect=source), patch("app.read_json", side_effect=source):
                        output = build(Path(directory) / "site")
                        static_rows = json.loads((output / "data/site-catalog.json").read_text(encoding="utf-8"))["musicals"]
                        with application.test_client() as client:
                            for row in static_rows:
                                local = client.get("/api/details", query_string={"id": row["id"]}).get_json()
                                name = row["artwork_url"].split("?")[0].rsplit("/", 1)[-1]
                                self.assertEqual(local["artwork_url"].split("?")[0].rsplit("/", 1)[-1], name)
                                with client.get(local["artwork_url"]) as response:
                                    self.assertEqual(response.status_code, 200)
                                    self.assertEqual(response.data, (output / "static/artwork" / name).read_bytes())
                finally:
                    library.pool.shutdown()
