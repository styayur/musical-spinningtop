"""Controlled publication races, including native Windows spawn processes."""
import json
import multiprocessing
import os
import tempfile
import threading
import traceback
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from artwork import generate as gen


def entry(identity="en:race", intro="A letter arrives."):
    return {"id": identity, "title": "Race", "intro_en": intro}


def manifest(directory):
    return json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))


def process_publish(directory, row, output, barrier=None, started=None, release=None,
                    counter=None, art_version="2", extractor_version="2", library=False,
                    request_attempt=None):
    """Spawn-safe worker: report exceptions to the parent, not just stderr."""
    real_plan = gen.plan_artwork
    real_lock = gen._file_lock

    @contextmanager
    def controlled_lock(path):
        if request_attempt is not None and path.name != ".artwork.lock":
            request_attempt.set()
        with real_lock(path):
            yield

    def controlled_plan(*args, **kwargs):
        if counter is not None:
            with counter.get_lock():
                counter.value += 1
        if started is not None:
            started.set()
        if release is not None and not release.wait(15):
            raise TimeoutError("Parent did not release artwork planning")
        if barrier is not None:
            barrier.wait(15)
        return real_plan(*args, **kwargs)

    try:
        with patch.object(gen, "plan_artwork", side_effect=controlled_plan), \
                patch.object(gen, "_file_lock", side_effect=controlled_lock):
            method = gen.generate_library if library else gen.ensure_artwork
            result = method([row] if library else row, directory, "/artwork/",
                            art_version=art_version, extractor_version=extractor_version)
        output.put(("ok", result))
    except BaseException:
        output.put(("error", traceback.format_exc()))


def process_lock(directory, attempted, acquired, release, orphan=False):
    attempted.set()
    with gen._directory_lock(directory):
        if orphan:
            fd, name = tempfile.mkstemp(dir=directory, prefix=".artwork-", suffix=".tmp")
            with os.fdopen(fd, "wb") as stream:
                stream.write(b"partial publication")
        acquired.set()
        if not release.wait(15):
            raise TimeoutError("Parent did not release directory lock")


class ArtworkConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ctx = multiprocessing.get_context("spawn")

    def start_process(self, target, *args, **kwargs):
        process = self.ctx.Process(target=target, args=args, kwargs=kwargs)
        process.start()

        def cleanup():
            if process.is_alive():
                process.terminate()
            process.join(10)
            process.close()

        self.addCleanup(cleanup)
        return process

    def output_queue(self):
        output = self.ctx.Queue()
        self.addCleanup(output.close)
        return output

    def result(self, process, output):
        status, value = output.get(timeout=20)
        process.join(10)
        self.assertFalse(process.is_alive(), "Spawned publication did not finish")
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(status, "ok", value)
        if "items" in value:
            self.assertEqual(value["stats"]["failed"], 0)
        else:
            self.assertNotEqual(value["artwork_reason"], "error", value)
        return value

    def assert_files_exist(self, value):
        for record in value["items"].values():
            self.assertIsNotNone(gen.resolve_artwork_path(self.directory, record["filename"]))
        self.assertEqual(list(self.directory.glob(".artwork-*.tmp")), [])

    def test_native_process_lock_blocks_then_releases(self):
        attempted, acquired, release = (self.ctx.Event() for _ in range(3))
        self.addCleanup(release.set)
        with gen._directory_lock(self.directory):
            worker = self.start_process(process_lock, str(self.directory), attempted, acquired, release)
            self.assertTrue(attempted.wait(10))
            self.assertFalse(acquired.wait(0.25), "A separate process bypassed the directory lock")
        self.assertTrue(acquired.wait(10))
        release.set()
        worker.join(10)
        self.assertEqual(worker.exitcode, 0)

    def test_process_exit_releases_lock_and_cleans_only_owned_temporary(self):
        attempted, acquired, release = (self.ctx.Event() for _ in range(3))
        foreign = self.directory / "someone-else.tmp"
        foreign.write_bytes(b"keep")
        worker = self.start_process(process_lock, str(self.directory), attempted, acquired, release, True)
        self.assertTrue(acquired.wait(10))
        self.assertEqual(len(list(self.directory.glob(".artwork-*.tmp"))), 1)
        worker.terminate()
        worker.join(10)
        output = self.output_queue()
        recovery = self.start_process(process_publish, str(self.directory), entry(), output)
        self.result(recovery, output)
        self.assert_files_exist(manifest(self.directory))
        self.assertEqual(foreign.read_bytes(), b"keep")
        self.assertTrue((self.directory / ".artwork.lock").exists())

    def test_distinct_process_publications_merge_after_same_snapshot(self):
        for sample in range(3):
            with self.subTest(sample=sample):
                barrier = self.ctx.Barrier(4)
                output = self.output_queue()
                rows = [entry(f"en:process-{sample}-{i}") for i in range(4)]
                workers = [self.start_process(process_publish, str(self.directory), row, output,
                                              barrier=barrier) for row in rows]
                for worker in workers:
                    self.result(worker, output)
                current = manifest(self.directory)
                self.assertEqual(len(current["items"]), (sample + 1) * 4)
                self.assertEqual(current["seq"], (sample + 1) * 4)
                self.assert_files_exist(current)

    def test_same_input_processes_plan_once(self):
        started, release = self.ctx.Event(), self.ctx.Event()
        self.addCleanup(release.set)
        counter = self.ctx.Value("i", 0)
        output = self.output_queue()
        first = self.start_process(process_publish, str(self.directory), entry(), output,
                                   started=started, release=release, counter=counter)
        self.assertTrue(started.wait(10))
        attempted = [self.ctx.Event() for _ in range(3)]
        duplicate_plan = self.ctx.Event()
        others = [self.start_process(process_publish, str(self.directory), entry(), output,
                                    counter=counter, started=duplicate_plan, request_attempt=event)
                  for event in attempted]
        try:
            for event in attempted:
                self.assertTrue(event.wait(10))
            self.assertFalse(duplicate_plan.wait(0.25), "Same-input waiters duplicated rendering")
        finally:
            release.set()
        results = [self.result(worker, output) for worker in [first, *others]]
        self.assertEqual(counter.value, 1)
        self.assertEqual(len({row["artwork_url"] for row in results}), 1)
        self.assertEqual(manifest(self.directory)["seq"], 1)

    def test_late_process_does_not_revert_source_or_generator_versions(self):
        variants = [({"intro_en": "A ship crosses the ocean."}, "2", "2"),
                    ({}, "3", "2"), ({}, "2", "3")]
        for index, (changes, art_version, extractor_version) in enumerate(variants):
            with self.subTest(art_version=art_version, extractor_version=extractor_version, changes=changes):
                old = entry(f"en:late-{index}")
                started, release = self.ctx.Event(), self.ctx.Event()
                self.addCleanup(release.set)
                output = self.output_queue()
                worker = self.start_process(process_publish, str(self.directory), old, output,
                                            started=started, release=release)
                try:
                    self.assertTrue(started.wait(10))
                    new = gen.ensure_artwork({**old, **changes}, self.directory, "/artwork/",
                                             art_version, extractor_version)
                    svg = (self.directory / new["artwork_file"]).read_bytes()
                    sequence = manifest(self.directory)["seq"]
                finally:
                    release.set()
                late = self.result(worker, output)
                self.assertEqual(late, new)
                self.assertEqual(manifest(self.directory)["seq"], sequence)
                self.assertEqual((self.directory / new["artwork_file"]).read_bytes(), svg)

    def test_thread_publications_merge_after_same_snapshot(self):
        barrier = threading.Barrier(6)
        real_plan = gen.plan_artwork

        def controlled_plan(*args, **kwargs):
            barrier.wait(10)
            return real_plan(*args, **kwargs)

        rows = [entry(f"en:thread-{index}") for index in range(6)]
        with patch.object(gen, "plan_artwork", side_effect=controlled_plan), ThreadPoolExecutor(6) as pool:
            futures = [pool.submit(gen.ensure_artwork, row, self.directory, "/artwork/") for row in rows]
            for future in futures:
                self.assertNotEqual(future.result(15)["artwork_reason"], "error")
        self.assertEqual(set(manifest(self.directory)["items"]), {row["id"] for row in rows})
        self.assert_files_exist(manifest(self.directory))

    def test_unrelated_publication_does_not_cancel_a_pending_refresh(self):
        old = entry()
        gen.ensure_artwork(old, self.directory, "/artwork/")
        changed = entry(intro="A ship crosses the ocean.")
        started, release = threading.Event(), threading.Event()
        real_plan = gen.plan_artwork

        def controlled_plan(row, *args, **kwargs):
            if row == changed:
                started.set()
                if not release.wait(10):
                    raise TimeoutError("Refresh not released")
            return real_plan(row, *args, **kwargs)

        with patch.object(gen, "plan_artwork", side_effect=controlled_plan), ThreadPoolExecutor(1) as pool:
            pending = pool.submit(gen.ensure_artwork, changed, self.directory, "/artwork/")
            try:
                self.assertTrue(started.wait(10))
                gen.ensure_artwork(entry("en:unrelated"), self.directory, "/artwork/")
            finally:
                release.set()
            result = pending.result(15)
        self.assertEqual(result["source_digest"], gen.normalize_entry(changed)["source_digest"])
        self.assertEqual(manifest(self.directory)["items"][changed["id"]]["filename"], result["artwork_file"])

    def test_bulk_process_preserves_concurrent_refresh_and_insert(self):
        old = entry()
        original = gen.ensure_artwork(old, self.directory, "/artwork/")
        removed = gen.ensure_artwork(entry("en:removed"), self.directory, "/artwork/")
        old_bytes = (self.directory / original["artwork_file"]).read_bytes()
        started, release = self.ctx.Event(), self.ctx.Event()
        self.addCleanup(release.set)
        output = self.output_queue()
        worker = self.start_process(process_publish, str(self.directory), old, output,
                                    started=started, release=release, library=True)
        try:
            self.assertTrue(started.wait(10))
            new = gen.ensure_artwork(entry(intro="A ship crosses the ocean."), self.directory, "/artwork/")
            inserted = entry("en:inserted")
            gen.ensure_artwork(inserted, self.directory, "/artwork/")
        finally:
            release.set()
        built = self.result(worker, output)
        self.assertEqual(built, manifest(self.directory))
        self.assertEqual(set(built["items"]), {old["id"], inserted["id"]})
        self.assertEqual(built["items"][old["id"]]["filename"], new["artwork_file"])
        self.assertEqual((self.directory / original["artwork_file"]).read_bytes(), old_bytes)
        self.assertTrue((self.directory / removed["artwork_file"]).is_file())
        self.assert_files_exist(built)

    def test_bulk_publication_wins_over_an_already_planning_runtime_request(self):
        started, release = self.ctx.Event(), self.ctx.Event()
        self.addCleanup(release.set)
        output = self.output_queue()
        worker = self.start_process(process_publish, str(self.directory), entry(), output,
                                    started=started, release=release)
        try:
            self.assertTrue(started.wait(10))
            built = gen.generate_library([entry(intro="A ship crosses the ocean.")], self.directory, "/artwork/")
        finally:
            release.set()
        result = self.result(worker, output)
        self.assertEqual(result["artwork_file"], built["items"][entry()["id"]]["filename"])
        self.assertEqual(manifest(self.directory), built)

    def test_cache_hit_does_not_render_read_svg_or_rewrite_files(self):
        first = gen.ensure_artwork(entry(), self.directory, "/artwork/")
        before = {path.name: path.stat().st_mtime_ns for path in self.directory.iterdir()}
        with patch.object(gen, "plan_artwork", side_effect=AssertionError("planned cache hit")), \
                patch.object(gen, "render_base", side_effect=AssertionError("rendered base")), \
                patch.object(gen, "_atomic_text", side_effect=AssertionError("rewrote cache")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("read SVG bytes")):
            second = gen.ensure_artwork(entry(), self.directory, "/other-prefix/")
        self.assertEqual(second["artwork_file"], first["artwork_file"])
        self.assertTrue(second["artwork_url"].startswith("/other-prefix/"))
        self.assertEqual(before, {path.name: path.stat().st_mtime_ns for path in self.directory.iterdir()})

    def test_failed_render_is_retryable_and_base_is_not_rewritten(self):
        with patch.object(gen, "render_svg", side_effect=RuntimeError("transient renderer failure")):
            failed = gen.ensure_artwork(entry(), self.directory, "/artwork/")
        base = (self.directory / "base.svg").read_bytes()
        self.assertEqual(failed["artwork_reason"], "error")
        recovered = gen.ensure_artwork(entry(), self.directory, "/artwork/")
        self.assertNotEqual(recovered["artwork_file"], "base.svg")
        self.assertEqual((self.directory / "base.svg").read_bytes(), base)

    def test_changed_bytes_cannot_overwrite_an_existing_version_url(self):
        first = gen.generate_library([entry()], self.directory, "/artwork/")
        original = gen.plan_artwork(entry())
        changed = {**original, "svg": original["svg"] + "\n"}
        with patch.object(gen, "plan_artwork", return_value=changed):
            with self.assertRaisesRegex(ValueError, "bump the generator version"):
                gen.generate_library([entry()], self.directory, "/artwork/")
        self.assertEqual((self.directory / original["filename"]).read_bytes(), original["svg"].encode("utf-8"))
        self.assertEqual(manifest(self.directory), first)
        self.assertEqual(list(self.directory.glob(".artwork-*.tmp")), [])

    def test_library_counts_internal_and_external_planning_errors_once(self):
        for function in ("render_svg", "plan_artwork"):
            with self.subTest(function=function), patch.object(gen, function, side_effect=RuntimeError("failed")):
                built = gen.generate_library([entry()], self.directory, "/artwork/")
            self.assertEqual(built["stats"]["failed"], 1)
            self.assertEqual(built["stats"]["fallback"], 1)
            self.assertEqual(built["items"][entry()["id"]]["reason"], "error")

    def test_delayed_bulk_error_cannot_replace_concurrent_success(self):
        started, release = threading.Event(), threading.Event()
        real_plan = gen.plan_artwork

        def controlled_plan(row, *args, **kwargs):
            if threading.current_thread() is not threading.main_thread():
                started.set()
                if not release.wait(10):
                    raise TimeoutError("Bulk failure not released")
                return gen._error_plan(row["id"], gen.normalize_entry(row)["source_digest"],
                                       gen.ART_VERSION, gen.EXTRACTOR_VERSION)
            return real_plan(row, *args, **kwargs)

        with patch.object(gen, "plan_artwork", side_effect=controlled_plan), ThreadPoolExecutor(1) as pool:
            pending = pool.submit(gen.generate_library, [entry()], self.directory, "/artwork/")
            try:
                self.assertTrue(started.wait(10))
                successful = gen.ensure_artwork(entry(), self.directory, "/artwork/")
            finally:
                release.set()
            built = pending.result(15)
        self.assertEqual(built["items"][entry()["id"]]["filename"], successful["artwork_file"])
        self.assertEqual(built["stats"]["failed"], 1)
        self.assertEqual(built["stats"]["fallback"], 0)

    def test_atomic_replace_failure_preserves_manifest_and_removes_temporary(self):
        path = self.directory / "manifest.json"
        path.write_text("previous", encoding="utf-8")
        with gen._directory_lock(self.directory), \
                patch.object(gen.os, "replace", side_effect=PermissionError("busy")), \
                patch.object(gen.time, "sleep"):
            with self.assertRaises(PermissionError):
                gen._atomic_text(path, "replacement")
        self.assertEqual(path.read_text(encoding="utf-8"), "previous")
        self.assertEqual(list(self.directory.glob(".artwork-*.tmp")), [])

    def test_atomic_replace_retries_transient_windows_denial(self):
        real_replace = os.replace
        path = self.directory / "manifest.json"
        attempts = []

        def replace(source, target):
            attempts.append(target)
            if len(attempts) < 3:
                raise PermissionError("reader temporarily holds the file")
            return real_replace(source, target)

        with gen._directory_lock(self.directory), patch.object(gen.os, "replace", side_effect=replace), \
                patch.object(gen.time, "sleep"):
            gen._atomic_text(path, "published")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(path.read_text(encoding="utf-8"), "published")
        self.assertEqual(list(self.directory.glob(".artwork-*.tmp")), [])

    def test_version_names_are_injective_even_on_case_insensitive_filesystems(self):
        versions = ["2", "test-2", "test2", "TEST2", "v0", "v0746573742d32", "", "版本"]
        names = [gen.safe_filename("id", version, "2", "a" * 64) for version in versions]
        self.assertEqual(len({name.casefold() for name in names}), len(versions))
        for name in names:
            self.assertIsNotNone(gen.SAFE_NAME.fullmatch(name))


if __name__ == "__main__":
    unittest.main()
