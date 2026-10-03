from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_schedule_is_primary_and_fixture_opens_projection():
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()

    assert not app.exception
    assert app.radio[0].options == [
        "Schedule", "Teams", "Rankings", "Compare", "Methodology"
    ]
    assert app.radio[0].value == "Schedule"
    assert any("234 matches shown" in caption.value for caption in app.caption)

    fixture_selector = next(item for item in app.selectbox if item.label == "Open a fixture")
    fixture_selector.set_value(fixture_selector.options[2]).run()
    assert not app.exception
    assert any(header.value == "St. Lawrence University at Hobart College" for header in app.header)
    assert any(subheader.value == "Expected individual matchups" for subheader in app.subheader)
    assert any(metric.label == "Lineup confidence" for metric in app.metric)


def test_team_compare_and_methodology_pages_render():
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()
    app.radio[0].set_value("Teams").run()
    assert not app.exception
    assert any(subheader.value == "2026–27 roster" for subheader in app.subheader)

    app.radio[0].set_value("Compare").run()
    assert not app.exception
    assert any(subheader.value == "Expected individual matchups" for subheader in app.subheader)

    app.radio[0].set_value("Methodology").run()
    assert not app.exception
    page_text = " ".join(item.value for item in [*app.markdown, *app.text])
    assert "rating_date < match_date" in page_text
    assert "Preseason projection" in page_text


def test_global_player_autocomplete_finds_current_roster_player():
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()
    app.text_input[0].set_value("Raven").run()
    matches = next(item for item in app.selectbox if item.label == "Matching players")
    label = "Charlie Raven — Hamilton College, Men (2026-27)"
    assert label in matches.options
    matches.set_value(label).run()
    assert not app.exception
    assert app.title[0].value == "Raven, Charlie"
    assert any(metric.label == "Current rating" for metric in app.metric)


def test_empty_player_search_does_not_select_or_load_a_player():
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()

    assert not app.exception
    assert not any(item.label == "Matching players" for item in app.selectbox)
    assert app.title[0].value == "2026–27 Schedule"
