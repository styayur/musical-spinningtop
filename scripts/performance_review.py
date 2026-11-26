"""Offline controlled /api/random experiment; writes JSON, never CI thresholds.

Run after app/artwork edits settle:
    python scripts/performance_review.py
All imports, databases and generated images live in temporary snapshots. main's
app.py and catalog.py are extracted with git show, not reimplemented. No server,
external network, production runtime, stdout instrumentation or commits are used.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SEED = "spinningtop-performance-2026-11-26"
ARMS = ("main", "current", "current_artwork_bypass")
DATA = ("catalog.json", "articles.json", "musicals.json", "summaries_zh.json", "exclusions.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def source_class(source, name):
    text = source.decode("utf-8").replace("\r\n", "\n")
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name == name)
    return ast.get_source_segment(text, node).encode("utf-8")


def store_methods(source):
    text = source.decode("utf-8").replace("\r\n", "\n")
    store = next(node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name == "Store")
    lines = text.splitlines()
    return {node.name: "\n".join(lines[min([node.lineno] + [decorator.lineno for decorator in node.decorator_list]) - 1:node.end_lineno]).encode("utf-8")
            for node in store.body if isinstance(node, ast.FunctionDef)}


def summary(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "p50_ms": None, "p95_ms": None, "max_ms": None, "mean_ms": None}
    return {"n": len(values), "p50_ms": ordered[math.ceil(0.50 * len(values)) - 1],
            "p95_ms": ordered[math.ceil(0.95 * len(values)) - 1],
            "max_ms": max(values), "mean_ms": statistics.mean(values)}


def measured_worker(args):
    import flask
    import requests

    sys.path.insert(0, str(args.snapshot))
    os.environ["SPINNINGTOP_DATA_DIR"] = str(args.runtime / "import-only")
    args.runtime.mkdir(parents=True, exist_ok=True)
    attempts = []

    def forbidden(*_args, **_kwargs):
        attempts.append("socket/DNS attempted")
        raise AssertionError("Network is disabled for this experiment")

    with patch.object(socket, "socket", forbidden), patch.object(socket, "getaddrinfo", forbidden):
        import app as module

        module.app.extensions["library"].pool.shutdown(wait=True)
        def choose(pool):
            """Pair IDs while retaining the real Store transaction and writes."""
            identity = flask.request.headers["X-Benchmark-Id"]
            return next(row for row in pool if row["id"] == identity)

        module.secrets = SimpleNamespace(choice=choose)
        if args.arm == "current_artwork_bypass":
            module.artwork_fields = lambda *_args, **_kwargs: {}
        state = threading.local()
        original_pick = module.Store.pick

        def pick(store, *a, **kw):
            if getattr(state, "entered", None) is not None:
                state.entered.set()
            start = time.perf_counter_ns()
            try:
                return original_pick(store, *a, **kw)
            finally:
                state.pick_ms = (time.perf_counter_ns() - start) / 1e6

        module.Store.pick = pick
        if hasattr(module, "artwork_fields"):
            original_artwork = module.artwork_fields

            def artwork(*a, **kw):
                start = time.perf_counter_ns()
                try:
                    return original_artwork(*a, **kw)
                finally:
                    state.artwork_ms = (time.perf_counter_ns() - start) / 1e6

            module.artwork_fields = artwork

        apps = []
        records = {}
        checks = {}

        def create(name):
            application = module.create_app(args.runtime / name, background=False)
            application.testing = True
            apps.append(application)
            return application

        cold = create("cold")
        entries = sorted(cold.extensions["library"].snapshot(),
                         key=lambda row: digest((SEED + row["id"]).encode()))
        assert args.samples + args.batches * args.clients + args.lock_samples + 1 < len(entries) - 2

        def reset(application):
            with application.extensions["store"].connect() as db:
                db.execute("DELETE FROM seen")
                db.execute("DELETE FROM last_pick")

        def request_one(application, index, barrier=None, entered=None):
            identity = entries[index]["id"]
            state.pick_ms = state.artwork_ms = 0.0
            state.entered = entered
            with application.test_client() as client:
                if barrier is not None:
                    barrier.wait(timeout=30)
                start = time.perf_counter_ns()
                response = client.post("/api/random", headers={"X-Benchmark-Id": identity})
                stop = time.perf_counter_ns()
            payload = response.get_json()
            assert response.status_code == 200, (response.status_code, payload)
            assert payload["id"] == identity
            assert payload.get("artwork_reason") != "error", payload
            item = {"id": identity, "elapsed_ms": (stop - start) / 1e6,
                    "store_pick_ms": state.pick_ms, "artwork_fields_ms": state.artwork_ms,
                    "start_ns": start, "stop_ns": stop, "status": response.status_code}
            if args.arm == "current":
                name = payload["artwork_url"].split("?")[0].rsplit("/", 1)[-1]
                path = application.extensions["store"].directory / "artwork" / name
                item["artwork_file"] = name
                item["svg_sha256"] = digest(path.read_bytes())
            return item

        records["normal_cold"] = [request_one(cold, i) for i in range(args.samples)]
        hot = create("hot")
        artwork_dir = hot.extensions["store"].directory / "artwork"
        if args.arm != "main":
            from artwork.generate import ensure_artwork, generate_library
            from artwork.normalize import merge_publication

            library = hot.extensions["library"]
            summaries = module.read_json(args.snapshot / "data" / "summaries_zh.json", {})
            publication = [merge_publication(row, library.bundled_details.get(row["id"], {}),
                                             summaries.get(row["title"], "")) for row in entries]
            result = generate_library(publication, artwork_dir, "/artwork/")
            assert result["stats"]["failed"] == 0
            checks["prewarmed_manifest_items"] = len(result["items"])
            checks["prewarmed_manifest_bytes"] = (artwork_dir / "manifest.json").stat().st_size
            checks["prewarmed_svg_files"] = len(list(artwork_dir.glob("*.svg")))
            before = digest((artwork_dir / "manifest.json").read_bytes())
        records["normal_hot"] = [request_one(hot, i) for i in range(args.samples)]
        if args.arm != "main":
            checks["hot_manifest_unchanged"] = before == digest((artwork_dir / "manifest.json").read_bytes())
            assert checks["hot_manifest_unchanged"], "Hot inputs unexpectedly invalidated the cache"
        with hot.extensions["store"].connect() as db:
            checks["sqlite"] = {"journal_mode": db.execute("PRAGMA journal_mode").fetchone()[0],
                                "synchronous": db.execute("PRAGMA synchronous").fetchone()[0],
                                "busy_timeout_ms": db.execute("PRAGMA busy_timeout").fetchone()[0]}

        def held_writer(count, hold_ms):
            reset(hot)
            measured = []
            with ThreadPoolExecutor(max_workers=1) as executor:
                for index in range(count):
                    entered = threading.Event()
                    blocker = sqlite3.connect(hot.extensions["store"].database, timeout=15)
                    try:
                        blocker.execute("BEGIN IMMEDIATE")
                        future = executor.submit(request_one, hot, index, entered=entered)
                        assert entered.wait(30), "Request did not reach Store.pick"
                        start = time.perf_counter_ns()
                        time.sleep(hold_ms / 1000)
                        assert not future.done(), "Request escaped a confirmed SQLite writer lock"
                        blocker.rollback()
                        released = time.perf_counter_ns()
                        item = future.result(timeout=30)
                        item["confirmed_hold_ms"] = (released - start) / 1e6
                        measured.append(item)
                    finally:
                        blocker.close()
            return measured

        records["held_writer"] = held_writer(args.lock_samples, args.hold_ms)
        if args.long_hold_ms:
            records["held_writer_long"] = held_writer(1, args.long_hold_ms)
        reset(hot)
        updates = []
        concurrent = []
        def update_one(batch, lane, barrier):
            row = {**publication[-1 - lane], "intro_en": f"Two lovers cross a river. Revision {batch} lane {lane}.",
                   "intro_zh": ""}
            barrier.wait(timeout=30)
            start = time.perf_counter_ns()
            result = ensure_artwork(row, artwork_dir, "/artwork/")
            stop = time.perf_counter_ns()
            assert result["artwork_reason"] != "error"
            name = result["artwork_file"]
            return {"batch": batch, "lane": lane, "id": row["id"],
                    "elapsed_ms": (stop - start) / 1e6, "start_ns": start, "stop_ns": stop,
                    "artwork_file": name, "svg_sha256": digest((artwork_dir / name).read_bytes()),
                    "source_digest": result["source_digest"]}

        lanes = 0 if args.arm == "main" else 2
        with ThreadPoolExecutor(max_workers=args.clients + lanes) as executor:
            for batch in range(args.batches):
                barrier = threading.Barrier(args.clients + lanes)
                futures = [executor.submit(request_one, hot, batch * args.clients + i, barrier)
                           for i in range(args.clients)]
                writers = [executor.submit(update_one, batch, lane, barrier) for lane in range(lanes)]
                concurrent.extend(f.result(timeout=60) for f in futures)
                updates.extend(f.result(timeout=60) for f in writers)
        records["concurrent_hot"] = concurrent
        records["concurrent_artwork_updates"] = updates
        if lanes:
            manifest = json.loads((artwork_dir / "manifest.json").read_text(encoding="utf-8"))
            assert len(manifest["items"]) == len(entries), "Manifest lost an entry"
            for item in concurrent + updates:
                if "artwork_file" in item:
                    assert digest((artwork_dir / item["artwork_file"]).read_bytes()) == item["svg_sha256"]
            for item in updates[-lanes:]:
                assert manifest["items"][item["id"]]["source_digest"] == item["source_digest"]
            checks["concurrent_requests_overlapping_update"] = sum(
                any(u["start_ns"] < row["stop_ns"] and u["stop_ns"] > row["start_ns"] for u in updates)
                for row in concurrent)
            assert checks["concurrent_requests_overlapping_update"] > 0
            checks["manifest_items_retained"] = len(manifest["items"])
            checks["published_svg_bytes_preserved"] = True
            checks["temporary_files_remaining"] = len(list(artwork_dir.glob("*.tmp")))
            assert checks["temporary_files_remaining"] == 0
        checks["network_attempts"] = attempts
        assert not attempts
        for application in apps:
            application.extensions["library"].pool.shutdown(wait=True)
        write_json(args.result, {"arm": args.arm, "records": records, "checks": checks,
                                 "catalogue_count": len(entries)})


def experiment(args):
    started = datetime.now(timezone.utc).isoformat()
    commit = git("rev-parse", args.baseline).decode().strip()
    paths = ["app.py", "catalog.py"] + [f"data/{name}" for name in DATA]
    current_paths = paths + sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "artwork").glob("*.py"))
    current = {path: (ROOT / path).read_bytes() for path in current_paths}
    baseline = {path: git("show", f"{commit}:{path}") for path in paths}
    store_main = source_class(baseline["app.py"], "Store")
    store_current = source_class(current["app.py"], "Store")
    main_methods = store_methods(baseline["app.py"])
    current_methods = store_methods(current["app.py"])
    methods_equal = {name: source == current_methods.get(name) for name, source in main_methods.items()}
    assert all(methods_equal.values()), "Existing Store methods changed: revise attribution before benchmarking"
    data_equal = {path: baseline[path].replace(b"\r\n", b"\n") == current[path].replace(b"\r\n", b"\n")
                  for path in paths if path != "app.py"}
    assert all(data_equal.values()), "Paired baseline requires identical catalogue code and data"
    runs = []
    with tempfile.TemporaryDirectory(prefix="spinningtop-performance-") as temporary:
        root = Path(temporary)
        for name, snapshot in (("main", baseline), ("current", current)):
            for path, content in snapshot.items():
                destination = root / name / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        for repetition in range(args.rounds):
            order = ARMS[repetition % 3:] + ARMS[:repetition % 3]
            for arm in order:
                result = root / f"{repetition}-{arm}.json"
                command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker",
                           "--arm", arm, "--snapshot", str(root / ("main" if arm == "main" else "current")),
                           "--runtime", str(root / f"runtime-{repetition}-{arm}"), "--result", str(result),
                           "--samples", str(args.samples), "--batches", str(args.batches),
                           "--clients", str(args.clients), "--lock-samples", str(args.lock_samples),
                           "--hold-ms", str(args.hold_ms), "--long-hold-ms", str(args.long_hold_ms if repetition == 0 else 0)]
                completed = subprocess.run(command, cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                           capture_output=True, text=True, timeout=600)
                if completed.returncode:
                    raise RuntimeError(f"{arm} worker failed:\n{completed.stderr}")
                run = json.loads(result.read_text(encoding="utf-8"))
                run.update(repetition=repetition, execution_position=len(runs))
                runs.append(run)
    unchanged = all((ROOT / path).read_bytes() == content for path, content in current.items())
    assert unchanged, "Sources changed during measurement; rerun after agents finish"
    aggregated = {}
    for arm in ARMS:
        aggregated[arm] = {}
        scenarios = runs[0]["records"].keys()
        for scenario in scenarios:
            samples = [row for run in runs if run["arm"] == arm for row in run["records"].get(scenario, [])]
            aggregated[arm][scenario] = {"latency": summary([row["elapsed_ms"] for row in samples]),
                                        "store_pick": summary([row["store_pick_ms"] for row in samples if "store_pick_ms" in row]),
                                        "artwork_fields": summary([row["artwork_fields_ms"] for row in samples if "artwork_fields_ms" in row])}
    differences = {}
    for scenario in ("normal_cold", "normal_hot", "held_writer", "held_writer_long", "concurrent_hot"):
        differences[scenario] = {}
        for comparator in ("main", "current_artwork_bypass"):
            delta = []
            for repetition in range(args.rounds):
                actual = next(run for run in runs if run["arm"] == "current" and run["repetition"] == repetition)
                control = next(run for run in runs if run["arm"] == comparator and run["repetition"] == repetition)
                a = actual["records"].get(scenario, [])
                b = control["records"].get(scenario, [])
                assert [row["id"] for row in a] == [row["id"] for row in b]
                delta.extend(x["elapsed_ms"] - y["elapsed_ms"] for x, y in zip(a, b))
            differences[scenario][f"current_minus_{comparator}"] = {**summary(delta), "samples_ms": delta}
    report = {
        "schema_version": 1, "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "command": f"python scripts/performance_review.py --baseline {commit} " + " ".join(
            f"--{name.replace('_', '-')} {getattr(args, name)}" for name in
            ("rounds", "samples", "batches", "clients", "lock_samples", "hold_ms", "long_hold_ms")),
        "environment": {"os": platform.platform(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                        "flask": importlib.metadata.version("flask"), "cpu_count": os.cpu_count()},
        "provenance": {"baseline_ref": args.baseline, "baseline_commit": commit,
                       "worktree_head": git("rev-parse", "HEAD").decode().strip(),
                       "store_class_source_identical": store_main == store_current,
                       "existing_store_methods_identical": methods_equal,
                       "added_store_methods": sorted(set(current_methods) - set(main_methods)),
                       "store_method_sha256": {name: digest(source) for name, source in main_methods.items()},
                       "store_verification": "Exact method source segment equality after CRLF normalization; main read with git show <commit>:app.py. archive_daily is newly added but is not called by /api/random.",
                       "catalogue_code_and_data_equal": data_equal, "sources_unchanged_during_run": unchanged,
                       "current_sha256": {path: digest(content) for path, content in current.items()},
                       "baseline_sha256": {path: digest(content) for path, content in baseline.items()},
                       "script_sha256": digest(Path(__file__).read_bytes())},
        "method": {
            "seed": SEED, "transport": "Flask test_client POST /api/random; full dispatch and JSON serialization, no HTTP server or TCP",
            "timing": "perf_counter_ns; response parsing and SVG verification excluded; all samples retained; nearest-rank percentiles",
            "pairing": "Identical SHA256-sorted IDs selected from the real Store pool through a benchmark-only choice replacement; Store unchanged",
            "cold": "Fresh app/runtime per arm/round; distinct unseen artwork for each request; growing manifest; SQLite tables initialized before timing",
            "hot": "Full 2650-entry manifest generated outside timing in both current arms; SQLite detail cache empty, bundled local summaries; manifest unchanged asserted",
            "sqlite": "Production defaults, no WAL or timeout changes; uncontended sequential cold/hot; held BEGIN IMMEDIATE writer uses independent connection",
            "held_writer": f"{args.hold_ms} ms after confirmed Store.pick entry; request must remain blocked until rollback; actual hold recorded",
            "held_writer_long": f"One {args.long_hold_ms} ms hold per arm in first round; diagnostic only, not a tail-probability estimate",
            "concurrent": f"{args.clients} requests and two distinct-ID ensure_artwork updates released by a barrier per batch; both updates write new SVGs and the shared manifest; main has request workers only",
            "bypass": "Same current app/publication merge/SQLite; artwork_fields returns {}; full cache and concurrent updater workload retained",
            "isolation": "Frozen source snapshots, subprocess per arm/round, TemporaryDirectory runtimes, background=False, socket and DNS denied",
            "reproduction": "Use the recorded baseline commit and matching current_sha256 source/data files; run the recorded command from the repository root. Results depend on host load; no pass/fail latency threshold is imposed.",
            "limits": ["Cold means application/artwork cache miss, not cold OS page cache or process startup latency",
                       "Benchmark choice scans for a fixed ID instead of production secrets.choice; this small selection overhead is present in every arm",
                       "No browser image transfer/render, remote detail refresh, fsync durability change, or deployment latency measured",
                       "Threaded contention in this benchmark; cross-process correctness belongs to the concurrency regression tests",
                       "Shared Windows host load and antivirus can affect tails; rotated sequential arms are paired inputs, not simultaneous or causal proof",
                       "Manifest updates target distinct IDs from measured draws; same-ID version races are covered separately by concurrency tests",
                       "Artificial held-writer delays demonstrate an imposed blocker; they do not establish the cause or frequency of a previous slow request"]},
        "interpretation": {
            "store": "Every existing main Store method is source-identical, including pick/connect/cached_details. The class has gained archive_daily, which /api/random does not call. Shared transaction and busy-wait costs cannot be attributed to a new random-draw Store algorithm.",
            "artwork": "current minus current_artwork_bypass estimates incremental request artwork work with other current app behavior retained; measured artwork_fields spans provide supporting attribution.",
            "baseline": "current minus main includes artwork plus publication/payload changes; it is not an artwork-only comparison. Concurrent main lacks artwork writers, so bypass is the better contention control.",
            "lock": "A deliberately held SQLite writer can dominate both versions before artwork runs; compare store_pick spans and confirmed_hold_ms rather than assuming image generation caused the entire delay."},
        "summary": aggregated, "paired_differences": differences, "runs": runs,
    }
    write_json(args.output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="main")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/artwork-review/performance.json")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--batches", type=int, default=20)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--lock-samples", type=int, default=8)
    parser.add_argument("--hold-ms", type=float, default=250)
    parser.add_argument("--long-hold-ms", type=float, default=5250)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    for name in ("snapshot", "runtime", "result"):
        parser.add_argument(f"--{name}", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.rounds, args.samples, args.batches, args.clients, args.lock_samples) < 1 or args.hold_ms <= 0 or args.long_hold_ms < 0:
        parser.error("Counts and hold-ms must be positive; long-hold-ms may be zero")
    if args.worker:
        measured_worker(args)
    else:
        experiment(args)


if __name__ == "__main__":
    main()
