"""
Offline smoke test — no network, no email, no credentials required.

Run from the project root:
    python tests/smoke_test.py
    # or:
    python -m pytest tests/smoke_test.py -v
"""
from __future__ import annotations
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path so `src` is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(digest_id: str = "test-digest") -> dict:
    return {
        "id": digest_id,
        "enabled": True,
        "schedule": {
            "type": "weekly",
            "day_of_week": "monday",
            "hour": 0,
            "minute": 0,
            "timezone": "UTC",
        },
        "email": {
            "subject": f"Test Digest - {digest_id}",
            "to": ["recipient@example.com"],
        },
        "sources": [{"type": "webpage", "url": "https://example.com"}],
        "filters": {
            "include_keywords": ["python", "ai", "code"],
            "exclude_keywords": ["billing"],
            "freshness_days": 30,
            "require_any_keywords": True,
            "max_items": 3,
        },
        "scoring": {
            "keyword_hit": 2,
            "title_keyword_hit": 4,
            "recency_boost_days": 7,
            "recency_boost_score": 2,
        },
        "render": {
            "intro": "Smoke test intro line.",
        },
    }


# ---------------------------------------------------------------------------
# Test 1: models
# ---------------------------------------------------------------------------

def test_content_item():
    from src.models import ContentItem
    item = ContentItem(
        digest_id="test",
        source_type="rss",
        source_url="https://example.com/feed",
        title="A Python AI Code update",
        url="https://example.com/article/1",
        summary="Some summary",
        published_at=datetime.now(timezone.utc),
    )
    assert item.score == 0
    assert item.matched_keywords == []
    assert item.metadata == {}
    print("  [PASS] models.ContentItem")


# ---------------------------------------------------------------------------
# Test 2: store (uses a temp DB, no permanent state changes)
# ---------------------------------------------------------------------------

def test_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        import src.store as store_mod
        orig_path = store_mod.DB_PATH
        try:
            store_mod.DB_PATH = Path(tmpdir) / "state.db"
            # get_conn, mark_run, get_last_run, has_sent, mark_sent
            store_mod.mark_run("my-digest", True)
            last = store_mod.get_last_run("my-digest")
            assert last is not None
            assert isinstance(last, datetime)

            assert not store_mod.has_sent("my-digest", "https://example.com/1")
            store_mod.mark_sent("my-digest", "https://example.com/1")
            assert store_mod.has_sent("my-digest", "https://example.com/1")
            assert not store_mod.has_sent("my-digest", "https://example.com/2")
        finally:
            store_mod.DB_PATH = orig_path
    print("  [PASS] store (SQLite)")


# ---------------------------------------------------------------------------
# Test 3: pipeline filter_and_score
# ---------------------------------------------------------------------------

def test_pipeline():
    from src.models import ContentItem
    from src.pipeline import filter_and_score

    config = _make_config("pipe-test")
    now = datetime.now(timezone.utc)

    items = [
        ContentItem(
            digest_id="pipe-test",
            source_type="webpage",
            source_url="https://x.com",
            title="Python AI Code tutorial",
            url="https://x.com/article/1",
            published_at=now - timedelta(hours=1),
        ),
        ContentItem(
            digest_id="pipe-test",
            source_type="webpage",
            source_url="https://x.com",
            title="Billing update",
            url="https://x.com/article/2",
            published_at=now - timedelta(hours=2),
        ),
        ContentItem(
            digest_id="pipe-test",
            source_type="webpage",
            source_url="https://x.com",
            title="Completely unrelated sports news",
            url="https://x.com/article/3",
            published_at=now - timedelta(hours=3),
        ),
        ContentItem(
            digest_id="pipe-test",
            source_type="webpage",
            source_url="https://x.com",
            title="AI code assistant launch",
            url="https://x.com/article/4",
            published_at=now - timedelta(hours=4),
        ),
    ]

    # Patch has_sent to always return False (no DB needed)
    with patch("src.pipeline.has_sent", return_value=False):
        selected = filter_and_score(config, items)

    urls = [i.url for i in selected]
    assert "https://x.com/article/2" not in urls, "Excluded keyword 'billing' should filter article 2"
    assert "https://x.com/article/3" not in urls, "No matching keyword should filter article 3"
    assert "https://x.com/article/1" in urls
    assert "https://x.com/article/4" in urls
    assert len(selected) <= 3
    # Top item should be highest scored
    assert selected[0].score >= selected[-1].score
    print("  [PASS] pipeline.filter_and_score")


# ---------------------------------------------------------------------------
# Test 4: renderer
# ---------------------------------------------------------------------------

def test_renderer():
    from src.renderer import render_email

    config = _make_config("render-test")
    items = [
        {"title": "Hello World", "url": "https://example.com/hello", "summary": "A summary", "score": 5, "matched_keywords": ["python"]},
        {"title": "No Summary", "url": "https://example.com/nosummary", "summary": "", "score": 2, "matched_keywords": []},
    ]
    html = render_email(config, items)
    assert "Test Digest - render-test" in html
    assert "Hello World" in html
    assert "Smoke test intro line." in html
    assert "https://example.com/hello" in html
    assert "Score 5" in html
    print("  [PASS] renderer.render_email")


# ---------------------------------------------------------------------------
# Test 5: planner is_due
# ---------------------------------------------------------------------------

def test_planner():
    import src.store as store_mod
    from src.planner import is_due

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = store_mod.DB_PATH
        try:
            store_mod.DB_PATH = Path(tmpdir) / "state.db"
            now_utc = datetime.now(timezone.utc)
            # Build a config whose schedule day == today and hour already passed
            day_name = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][now_utc.weekday()]
            config = {
                "id": "planner-test",
                "enabled": True,
                "schedule": {
                    "type": "weekly",
                    "day_of_week": day_name,
                    "hour": 0,
                    "minute": 0,
                    "timezone": "UTC",
                },
            }
            # First run with no prior record → should be due
            assert is_due(config) is True
            # Mark a run as today → not due again today
            store_mod.mark_run("planner-test", True)
            assert is_due(config) is False
        finally:
            store_mod.DB_PATH = orig_path
    print("  [PASS] planner.is_due")


# ---------------------------------------------------------------------------
# Test 6: load_configs (reads real YAML files)
# ---------------------------------------------------------------------------

def test_load_configs():
    from src.main import load_configs
    configs = load_configs()
    assert len(configs) >= 2, f"Expected at least 2 digest configs, got {len(configs)}"
    ids = [c["id"] for c in configs]
    assert "vscode-weekly" in ids
    assert "ai-tools-weekly" in ids
    print("  [PASS] main.load_configs (found: {})".format(", ".join(ids)))


# ---------------------------------------------------------------------------
# Test 7: end-to-end dry-run with mocked network
# ---------------------------------------------------------------------------

def test_dry_run_e2e():
    """Full pipeline dry-run: mocked HTTP fetch, no email, temp SQLite."""
    import src.store as store_mod
    from src.main import run_digest

    fake_html = textwrap.dedent("""
        <html><body>
          <a href="/news/python-ai-code-assistant">Python AI Code Assistant launch</a>
          <a href="/news/billing-change">Billing change</a>
          <a href="/news/ai-workflow-guide">AI workflow productivity guide</a>
          <a href="/news/unrelated-sport">Sports recap</a>
        </body></html>
    """)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = fake_html

    config = _make_config("e2e-test")

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = store_mod.DB_PATH
        try:
            store_mod.DB_PATH = Path(tmpdir) / "state.db"
            with patch("src.sources.requests.get", return_value=mock_response):
                # dry_run=True: renders HTML and prints, does NOT call send_email
                run_digest(config, dry_run=True)

            # rendered HTML should exist
            rendered_dir = PROJECT_ROOT / "data" / "rendered"
            rendered_file = rendered_dir / "e2e-test.html"
            assert rendered_file.exists(), f"Rendered file not found at {rendered_file}"
            content = rendered_file.read_text(encoding="utf-8")
            assert "Test Digest - e2e-test" in content
        finally:
            store_mod.DB_PATH = orig_path

    print("  [PASS] end-to-end dry-run (mocked network)")


# ---------------------------------------------------------------------------
# Test 8: schedule_to_cron conversion
# ---------------------------------------------------------------------------

def test_schedule_to_cron():
    """
    Verify that schedule_to_cron produces correct UTC cron strings for
    representative weekly and daily schedules across timezone offsets.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generate_workflows",
        PROJECT_ROOT / "scripts" / "generate_workflows.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    schedule_to_cron = mod.schedule_to_cron

    # --- weekly cases ---

    # UTC — no shift
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "monday",
                              "hour": 9, "minute": 0, "timezone": "UTC"})
    assert cron == "0 9 * * 1", f"UTC Monday 09:00 -> expected '0 9 * * 1', got {cron!r}"

    # America/Toronto (EST = UTC-5): Sunday 10:00 local → Sunday 15:00 UTC (cron dow 0)
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "sunday",
                              "hour": 10, "minute": 0, "timezone": "America/Toronto"})
    assert cron == "0 15 * * 0", f"Toronto Sunday 10:00 -> expected '0 15 * * 0', got {cron!r}"

    # America/Toronto (EST = UTC-5): Friday 18:00 local → Friday 23:00 UTC (cron dow 5)
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "friday",
                              "hour": 18, "minute": 0, "timezone": "America/Toronto"})
    assert cron == "0 23 * * 5", f"Toronto Friday 18:00 -> expected '0 23 * * 5', got {cron!r}"

    # Day-rollover forward: Saturday 23:00 UTC+2 (e.g. Europe/Paris standard)
    # 23:00+02:00 = 21:00 UTC, same day
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "saturday",
                              "hour": 23, "minute": 0, "timezone": "Europe/Paris"})
    assert cron == "0 22 * * 6", f"Paris Saturday 23:00 -> expected '0 22 * * 6', got {cron!r}"

    # Day-rollover backward: Sunday 01:00 UTC-5 → Saturday 06:00 UTC becomes Sunday... let's
    # use a clear case: Sunday 01:00 America/Toronto (UTC-5) = Sunday 06:00 UTC
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "sunday",
                              "hour": 1, "minute": 30, "timezone": "America/Toronto"})
    assert cron == "30 6 * * 0", f"Toronto Sunday 01:30 -> expected '30 6 * * 0', got {cron!r}"

    # Day-rollover backward across midnight: Saturday 22:00 UTC-5 = Sunday 03:00 UTC
    cron = schedule_to_cron({"type": "weekly", "day_of_week": "saturday",
                              "hour": 22, "minute": 15, "timezone": "America/Toronto"})
    assert cron == "15 3 * * 0", f"Toronto Saturday 22:15 -> expected '15 3 * * 0', got {cron!r}"

    # --- daily cases ---
    cron = schedule_to_cron({"type": "daily", "hour": 8, "minute": 30,
                              "timezone": "America/Toronto"})
    assert cron == "30 13 * * *", f"Toronto daily 08:30 -> expected '30 13 * * *', got {cron!r}"

    cron = schedule_to_cron({"type": "daily", "hour": 0, "minute": 0,
                              "timezone": "UTC"})
    assert cron == "0 0 * * *", f"UTC daily 00:00 -> expected '0 0 * * *', got {cron!r}"

    print("  [PASS] schedule_to_cron (UTC conversion, weekly + daily)")


# ---------------------------------------------------------------------------
# Test 9: workflow generation for sample digest YAMLs
# ---------------------------------------------------------------------------

def test_workflow_generation():
    """
    Run generate_workflows.generate_all in dry-run mode against the real
    digests directory and verify:
      - a workflow is generated for each enabled digest
      - each generated workflow is valid YAML
      - the workflow contains the expected digest id
      - the workflow contains a properly quoted cron string
    """
    import importlib.util
    import io
    import re
    import yaml as pyyaml
    from contextlib import redirect_stdout

    spec = importlib.util.spec_from_file_location(
        "generate_workflows",
        PROJECT_ROOT / "scripts" / "generate_workflows.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from src.main import load_configs
    enabled_ids = [c["id"] for c in load_configs() if c.get("enabled", True)]
    assert enabled_ids, "Expected at least one enabled digest config"

    for cfg in (c for c in load_configs() if c.get("enabled", True)):
        digest_id = cfg["id"]
        # Build workflow string directly
        content = mod.build_workflow(cfg)

        # Must be parseable YAML
        try:
            doc = pyyaml.safe_load(content)
        except pyyaml.YAMLError as exc:
            raise AssertionError(f"Generated workflow for {digest_id!r} is not valid YAML: {exc}")
        assert doc is not None, f"Generated workflow for {digest_id!r} parsed as None"

        # Must contain the digest id
        assert digest_id in content, \
            f"Digest id {digest_id!r} not found in generated workflow"

        # Must contain a cron string (quoted, 5 fields)
        cron_pattern = re.compile(r'cron:\s*["\']([\d\*/]+ [\d\*/]+ [\d\*/]+ [\d\*/]+ [\d\*/]+)["\']')
        match = cron_pattern.search(content)
        assert match, f"No valid quoted cron found in workflow for {digest_id!r}\n{content}"
        cron_str = match.group(1)
        parts = cron_str.split()
        assert len(parts) == 5, \
            f"Cron string {cron_str!r} for {digest_id!r} does not have 5 fields"

        # Must contain workflow_dispatch with dry_run input
        assert "workflow_dispatch" in content, \
            f"workflow_dispatch missing from {digest_id!r} workflow"
        assert "dry_run" in content, \
            f"dry_run input missing from {digest_id!r} workflow"

        print(f"    [OK] {digest_id}: cron={cron_str!r}")

    # Also verify generate_all writes files to a temp dir
    import tempfile
    orig_workflows_dir = mod.WORKFLOWS_DIR
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.WORKFLOWS_DIR = Path(tmpdir)
            count = mod.generate_all(dry_run_flag=False, check=False)
            assert count == len(enabled_ids), \
                f"Expected {len(enabled_ids)} workflow(s), generate_all reported {count}"
            written = list(Path(tmpdir).glob("digest-*.yml"))
            assert len(written) == len(enabled_ids), \
                f"Expected {len(enabled_ids)} file(s), found {len(written)}"
            for wf in written:
                doc = pyyaml.safe_load(wf.read_text(encoding="utf-8"))
                assert doc is not None
    finally:
        mod.WORKFLOWS_DIR = orig_workflows_dir

    print("  [PASS] workflow generation (all enabled digests, valid YAML, correct cron format)")


# ---------------------------------------------------------------------------
# Test 10: resolve_recipients — DIGEST_TO_EMAILS parsing + dedupe
# ---------------------------------------------------------------------------

def test_resolve_recipients():
    from src.main import resolve_recipients

    # Comma-separated env value with whitespace and blanks
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": "a@example.com,b@example.com, c@example.com ,, "}, clear=False):
        out = resolve_recipients({"email": {"to": []}})
        assert out == ["a@example.com", "b@example.com", "c@example.com"], out

    # YAML list is preserved; env recipients are appended
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": "env@example.com"}, clear=False):
        out = resolve_recipients({"email": {"to": ["yaml@example.com"]}})
        assert out == ["yaml@example.com", "env@example.com"], out

    # Case-insensitive dedupe across YAML list and env, preserves first-seen casing
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": "A@Example.com, c@example.com"}, clear=False):
        out = resolve_recipients({"email": {"to": ["a@example.com", "B@example.com"]}})
        assert out == ["a@example.com", "B@example.com", "c@example.com"], out

    # Empty env var → only YAML list
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": ""}, clear=False):
        out = resolve_recipients({"email": {"to": ["only@example.com"]}})
        assert out == ["only@example.com"], out

    # Whitespace-only env entries collapse to empty
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": " , ,  "}, clear=False):
        out = resolve_recipients({"email": {"to": []}})
        assert out == [], out

    # Missing env var entirely → only YAML list
    env_no_var = {k: v for k, v in os.environ.items() if k != "DIGEST_TO_EMAILS"}
    with patch.dict(os.environ, env_no_var, clear=True):
        out = resolve_recipients({"email": {"to": ["yaml@example.com"]}})
        assert out == ["yaml@example.com"], out

    # YAML duplicates within the same list are deduped
    with patch.dict(os.environ, {"DIGEST_TO_EMAILS": ""}, clear=False):
        out = resolve_recipients({"email": {"to": ["x@example.com", "X@EXAMPLE.com"]}})
        assert out == ["x@example.com"], out

    print("  [PASS] resolve_recipients (comma-separated DIGEST_TO_EMAILS + dedupe)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_content_item,
    test_store,
    test_pipeline,
    test_renderer,
    test_planner,
    test_load_configs,
    test_dry_run_e2e,
    test_schedule_to_cron,
    test_workflow_generation,
    test_resolve_recipients,
]


def run_all():
    print(f"\nRunning {len(TESTS)} smoke tests...\n")
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All smoke tests passed.")


if __name__ == "__main__":
    run_all()
