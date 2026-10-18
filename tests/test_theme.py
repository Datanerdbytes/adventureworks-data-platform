"""Offline theme contrast and pre-paint integration checks."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from theme import DARK_TOKENS, theme_script


def luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class ThemeTests(unittest.TestCase):
    def test_settings_hydration_preserves_theme_and_defaults_to_light(self):
        from pages.settings import hydrate_all

        for theme in ("light", "dark", "system"):
            self.assertEqual(hydrate_all("/settings", {"theme": theme})[0], theme)
        self.assertEqual(hydrate_all("/settings", {"pageSize": 20})[0], "light")
        self.assertEqual(hydrate_all("/settings", None)[0], "light")

    def test_switches_hydrate_legacy_preferences_without_changing_sidebar_on_load(self):
        from pages.settings import hydrate_all, hydrate_sidebar, toggle_sidebar
        from dash.exceptions import PreventUpdate

        result = hydrate_all(
            "/settings", {"pipelineAlerts": "off", "includeFilters": "on"}
        )
        self.assertIs(result[7], False)
        self.assertIs(result[10], True)
        self.assertIs(hydrate_sidebar("/settings", True), True)
        self.assertIs(hydrate_sidebar("/settings", False), False)
        for value, current in ((None, True), (False, False), (True, True)):
            with self.assertRaises(PreventUpdate):
                toggle_sidebar(value, current)
        self.assertIs(toggle_sidebar(True, False), True)
        self.assertIs(toggle_sidebar(False, True), False)

    def test_dark_text_and_controls_meet_contrast_thresholds(self):
        for surface in ("background", "surface", "surface-raised", "surface-overlay"):
            for text in ("text", "muted", "primary", "teal"):
                with self.subTest(surface=surface, text=text):
                    self.assertGreaterEqual(
                        contrast(DARK_TOKENS[text], DARK_TOKENS[surface]), 4.5
                    )
            self.assertGreaterEqual(
                contrast(DARK_TOKENS["control-border"], DARK_TOKENS[surface]), 3
            )
        self.assertGreaterEqual(
            contrast(DARK_TOKENS["on-primary"], DARK_TOKENS["primary"]), 4.5
        )
        self.assertLess(
            luminance(DARK_TOKENS["surface"]), luminance(DARK_TOKENS["surface-raised"])
        )
        self.assertLess(
            luminance(DARK_TOKENS["surface-raised"]),
            luminance(DARK_TOKENS["surface-overlay"]),
        )

    def test_all_page_shells_apply_theme_before_stylesheets(self):
        from app import app

        self.assertLess(
            app.index_string.index(theme_script()),
            app.index_string.index('<link rel="stylesheet"'),
        )
        for page in ("auth", "landing"):
            source = (
                Path(__file__).resolve().parents[1]
                / "my-dash-app"
                / "templates"
                / f"{page}.html"
            ).read_text()
            self.assertLess(
                source.index('{% include "theme-script.html" %}'),
                source.index('<link rel="stylesheet"'),
            )
