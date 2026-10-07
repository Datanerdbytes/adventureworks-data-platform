"""Workspace phase-one navigation and sample interactions."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app, serve_layout
from pages.workspace import layout, filter_saved_views, search_definitions


def walk(node):
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from walk(child)
    elif hasattr(node, "to_plotly_json"):
        yield node
        yield from walk(getattr(node, "children", []))


class WorkspaceTests(unittest.TestCase):
    def test_mock_layout_and_navigation(self):
        with patch(
            "google.cloud.bigquery.Client",
            side_effect=AssertionError("No warehouse reads in workspace preview"),
        ):
            page = layout()
        nodes = list(walk(page))
        ids = [n.id for n in nodes if getattr(n, "id", None)]
        self.assertEqual(len(ids), len(set(ids)))
        for section in (
            "summary",
            "freshness",
            "saved-views",
            "quality",
            "definitions",
            "quick-links",
        ):
            self.assertIn(f"workspace-{section}", ids)
        routes = {n.href for n in nodes if getattr(n, "href", "").startswith("/")}
        self.assertEqual(routes, {"/dashboard", "/monitoring", "/tables", "/settings"})
        shell = list(walk(serve_layout()))
        workspace_links = [n for n in shell if getattr(n, "href", None) == "/workspace"]
        self.assertEqual(len(workspace_links), 2)
        self.assertIn(
            "nav-workspace", [getattr(n, "id", None) for n in workspace_links]
        )

    def test_filter_and_definition_search(self):
        cards, count = filter_saved_views("marketing")
        self.assertEqual(len(cards), 1)
        self.assertEqual(count, "1 Sample View")
        self.assertEqual(len(filter_saved_views("untrusted")[0]), 3)
        found = search_definitions(" CHURN ")
        self.assertEqual(len(found), 1)
        self.assertIn("Customer Churn Rate", str(found[0]))
        self.assertIn("No matching", str(search_definitions("nonexistent")))
