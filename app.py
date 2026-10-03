from datetime import date
from pathlib import Path
import sys

import joblib
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.analytics import (
    available_seasons, division_rankings, head_to_head, head_to_head_history,
    player_profile, player_search, program_elos, scheduled_matches,
    season_by_season_summary, season_history, strength_of_schedule, team_summary,
)
from college_squash.database import connect_database
from college_squash.preseason import (
    CURRENT_SEASON, current_roster, current_team_names, predict_preseason_matchup,
    preseason_lineup,
)


DATABASE_PATH = PROJECT_ROOT / "data/college_squash.db"
PLAYER_MODEL_PATH = PROJECT_ROOT / "data/preseason_player_model.joblib"
LATEST_COMPLETE_SEASON = "2025-26"
PAGES = ["Schedule", "Teams", "Rankings", "Compare", "Methodology"]


st.set_page_config(page_title="College Squash Analytics", page_icon="◫", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1160px; padding-top: 1.2rem; padding-bottom: 3rem;}
h1 {font-size: 1.9rem !important; margin-bottom: .2rem !important;}
h2 {font-size: 1.3rem !important; margin-top: 1.35rem !important;}
h3 {font-size: 1.05rem !important;}
[data-testid="stMetric"] {border-top: 1px solid rgba(128,128,128,.3); padding-top: .5rem;}
[data-testid="stMetricValue"] {font-size: 1.3rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def schedule_data(gender=None, team=None, start=None, end=None):
    with connect_database(DATABASE_PATH) as connection:
        return scheduled_matches(connection, gender, team, start, end)


@st.cache_data(show_spinner=False)
def ranking_data(gender, season):
    with connect_database(DATABASE_PATH) as connection:
        rankings = division_rankings(connection, gender, season)
        rankings["elo"] = rankings["team"].map(program_elos(connection, gender, season))
    return rankings


@st.cache_resource(show_spinner=False)
def player_model():
    return joblib.load(PLAYER_MODEL_PATH)


def schedule_table(frame, team=None):
    if frame.empty:
        return pd.DataFrame(columns=["Date", "Time", "Matchup", "Venue", "Status"])
    display = frame.copy()
    display["Date"] = pd.to_datetime(display["match_date"]).dt.strftime("%a, %b %-d")
    display["Time"] = display["match_time"].fillna("TBD")
    display["Venue"] = display["venue_name"].fillna("—")
    display["Matchup"] = display["away_team"] + " at " + display["home_team"]
    if team:
        display["Opponent"] = display.apply(
            lambda row: row["away_team"] if row["home_team"] == team else row["home_team"], axis=1)
        return display[["Date", "Time", "Opponent", "Venue", "status"]].rename(
            columns={"status": "Status"})
    display["Division"] = display["gender"].str.title()
    return display[["Date", "Division", "Time", "Matchup", "Venue", "status"]].rename(
        columns={"status": "Status"})


def fixture_labels(frame):
    return {
        f"{pd.Timestamp(row.match_date):%b %-d} · {row.away_team} at {row.home_team} · {row.source_match_id}":
        int(row.source_match_id)
        for row in frame.itertuples()
    }


def team_context(connection, team, gender):
    try:
        summary = team_summary(connection, team, gender, LATEST_COMPLETE_SEASON)
        sos = strength_of_schedule(connection, team, gender, LATEST_COMPLETE_SEASON)
        elo = program_elos(connection, gender, LATEST_COMPLETE_SEASON).get(team)
        return summary, sos, elo
    except ValueError:
        return None, None, None


def render_pairings(result, team_one, team_two):
    pairings = result["pairings"].copy()
    pairings["A rating"] = pairings["team_one_rating"].map(lambda value: f"{value:.2f}")
    pairings["A win probability"] = pairings["team_one_probability"].map(lambda value: f"{value:.1%}")
    pairings["B rating"] = pairings["team_two_rating"].map(lambda value: f"{value:.2f}")
    pairings["Rating date"] = pairings["team_one_rating_date"]
    display = pairings[["position", "team_one_player", "A rating", "A win probability",
                        "team_two_player", "B rating", "Rating date"]].rename(columns={
        "position": "Pos", "team_one_player": team_one, "team_two_player": team_two,
    })
    st.dataframe(display, hide_index=True, width="stretch")


def render_projection(connection, team_one, team_two, gender):
    result = predict_preseason_matchup(
        connection, player_model(), team_one, team_two, gender)
    if result is None:
        st.info("Preseason projection unavailable — one or both official rosters have fewer than nine rated players.")
        return
    st.subheader("Expected individual matchups")
    st.markdown("**Preseason projection**")
    st.caption("Projected from the official 2026–27 roster, roster ratings available on the displayed date, and previous varsity lineup history. Actual lineup may differ.")
    render_pairings(result, team_one, team_two)
    metrics = st.columns(4)
    metrics[0].metric(f"Expected wins · {team_one}", f"{result['team_one_expected_wins']:.1f}")
    metrics[1].metric(f"Expected wins · {team_two}", f"{result['team_two_expected_wins']:.1f}")
    metrics[2].metric(f"Win probability · {team_one}", f"{result['team_one_probability']:.1%}")
    metrics[3].metric("Lineup confidence", f"{result['lineup_confidence']:.0%}")
    st.caption("Lineup confidence summarizes rating coverage and how many projected players appeared in 2025–26; it is not the probability that all nine positions are exactly correct.")


def render_team_comparison(connection, team_one, team_two, gender):
    contexts = [team_context(connection, team, gender) for team in (team_one, team_two)]
    rows = []
    labels = ["2025–26 record", "Win percentage", "Project Elo", "Schedule strength", "Average margin"]
    for label_index, label in enumerate(labels):
        values = []
        for summary, sos, elo in contexts:
            if summary is None:
                values.append("—")
            else:
                values.append([
                    f"{summary['wins']}–{summary['losses']}", f"{summary['win_percentage']:.1%}",
                    f"{elo:.0f}", f"{sos:.1%}", f"{summary['average_margin']:+.2f}",
                ][label_index])
        rows.append({"Metric": label, team_one: values[0], team_two: values[1]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_historical_meetings(connection, team_one, team_two, gender):
    try:
        record = head_to_head(connection, team_one, team_two, gender)
        meetings = head_to_head_history(connection, team_one, team_two, gender)
    except ValueError:
        st.write("Historical head-to-head is unavailable for an outside-division opponent.")
        return
    st.metric(f"Historical record · {team_one}", f"{record['team_one_wins']}–{record['team_two_wins']}")
    if meetings.empty:
        st.write("No verified meetings in the available coverage.")
        return
    display = meetings.copy()
    display["Date"] = display["date"].dt.strftime("%b %-d, %Y")
    display["Score"] = display["team_score"].astype(str) + "–" + display["opponent_score"].astype(str)
    st.dataframe(display[["season", "Date", "result", "Score", "venue_name"]].rename(columns={
        "season": "Season", "result": "Result", "venue_name": "Venue"}),
        hide_index=True, width="stretch")


def render_fixture(connection, fixture):
    st.divider()
    st.header(f"{fixture['away_team']} at {fixture['home_team']}")
    details = f"{pd.Timestamp(fixture['match_date']):%A, %B %-d, %Y}"
    if fixture["match_time"]:
        details += f" · {fixture['match_time']}"
    details += f" · {fixture['venue_name'] or 'Location TBD'}"
    st.caption(details)
    render_projection(connection, fixture["away_team"], fixture["home_team"], fixture["gender"])
    st.subheader("Team context")
    render_team_comparison(connection, fixture["away_team"], fixture["home_team"], fixture["gender"])
    st.subheader("Historical meetings")
    render_historical_meetings(connection, fixture["away_team"], fixture["home_team"], fixture["gender"])


def schedule_page(connection):
    st.title("2026–27 Schedule")
    st.caption("Official varsity fixtures · select any match for a preseason matchup view")
    gender = st.segmented_control("Division", ["men", "women"], default="men", format_func=str.title)
    division_schedule = schedule_data(gender)
    teams = sorted(set(division_schedule["home_team"]) | set(division_schedule["away_team"]))
    team = st.selectbox("Team", ["All teams", *teams])
    min_date = pd.to_datetime(division_schedule["match_date"]).min().date()
    max_date = pd.to_datetime(division_schedule["match_date"]).max().date()
    dates = st.date_input("Date range", (min_date, max_date), min_value=min_date, max_value=max_date)
    start, end = dates if isinstance(dates, tuple) and len(dates) == 2 else (min_date, max_date)
    status = st.selectbox("Status", ["Upcoming", "Completed", "All"])
    filtered = schedule_data(gender, None if team == "All teams" else team, start, end)
    if status == "Completed":
        filtered = filtered.iloc[0:0]
    labels = fixture_labels(filtered)
    selection = st.selectbox("Open a fixture", ["Choose a match", *labels])
    st.caption(f"{len(filtered):,} matches shown · all scheduled fixtures remain separate from completed results")
    st.dataframe(schedule_table(filtered), hide_index=True, width="stretch", height=610)
    if selection != "Choose a match":
        fixture = filtered.loc[filtered["source_match_id"] == labels[selection]].iloc[0]
        render_fixture(connection, fixture)


def roster_table(connection, team, gender):
    roster = current_roster(connection, team, gender)
    lineup, confidence = preseason_lineup(connection, team, gender)
    likely_positions = {} if lineup is None else dict(zip(lineup["player_id"], lineup["position"]))
    roster["Likely position"] = roster["player_id"].map(likely_positions).fillna("Reserve / uncertain")
    roster["Rating"] = roster["current_rating"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "—")
    roster["Record"] = roster["career_wins"].astype(str) + "–" + (roster["career_matches"] - roster["career_wins"]).astype(str)
    display = roster[["display_name", "Rating", "rating_date", "Likely position", "Record"]].rename(columns={
        "display_name": "Player", "rating_date": "Rating date", "Record": "Verified college record"})
    st.dataframe(display, hide_index=True, width="stretch")
    if lineup is not None:
        st.caption(f"Preseason lineup evidence score: {confidence:.0%}. Positions are projected, not confirmed.")
    return roster


def team_page(connection):
    st.title("Teams")
    gender = st.segmented_control("Division", ["men", "women"], default="men", format_func=str.title,
                                  key="profile_gender")
    teams = current_team_names(connection, gender)
    default = "Harvard University" if "Harvard University" in teams else teams[0]
    team = st.selectbox("Team", teams, index=teams.index(default), key="profile_team")
    st.header(team)
    st.caption(f"{gender.title()} · official {CURRENT_SEASON} roster")
    prior, sos, elo = team_context(connection, team, gender)
    historical = team_summary(connection, team, gender) if prior else None
    metrics = st.columns(5)
    metrics[0].metric("2025–26 record", f"{prior['wins']}–{prior['losses']}" if prior else "—")
    metrics[1].metric("Project Elo", f"{elo:.0f}" if elo else "—")
    metrics[2].metric("Schedule strength", f"{sos:.1%}" if sos is not None else "—")
    metrics[3].metric("Average margin", f"{prior['average_margin']:+.2f}" if prior else "—")
    metrics[4].metric("Historical record", f"{historical['wins']}–{historical['losses']}" if historical else "—")

    st.subheader("2026–27 roster")
    roster = roster_table(connection, team, gender)
    player_labels = {
        f"{row.display_name} · {row.current_rating:.2f}": int(row.player_id)
        for row in roster.itertuples() if pd.notna(row.current_rating)
    }
    selected_player = st.selectbox("Open a roster player", ["Choose a player", *player_labels])
    if selected_player != "Choose a player":
        player_detail(connection, player_labels[selected_player])
        return
    st.subheader("Upcoming matches")
    fixtures = schedule_data(gender, team)
    labels = fixture_labels(fixtures)
    selected = st.selectbox("Open a team fixture", ["Choose a match", *labels])
    st.dataframe(schedule_table(fixtures, team), hide_index=True, width="stretch")
    if selected != "Choose a match":
        render_fixture(connection, fixtures.loc[fixtures["source_match_id"] == labels[selected]].iloc[0])

    st.subheader("Historical results")
    seasons = available_seasons(connection, gender)
    season = st.selectbox("Season", seasons, index=0)
    history = season_history(connection, team, gender, season).sort_values("date", ascending=False)
    history["Date"] = history["date"].dt.strftime("%b %-d, %Y")
    history["Score"] = history["team_score"].astype(str) + "–" + history["opponent_score"].astype(str)
    st.dataframe(history[["Date", "opponent", "result", "Score", "venue_name"]].rename(columns={
        "opponent": "Opponent", "result": "Result", "venue_name": "Venue"}),
        hide_index=True, width="stretch")
    st.subheader("Season-by-season performance")
    seasons_table = season_by_season_summary(connection, team, gender).copy()
    seasons_table["Record"] = seasons_table["wins"].astype(str) + "–" + seasons_table["losses"].astype(str)
    seasons_table["Win %"] = seasons_table["win_percentage"].map(lambda value: f"{value:.1%}")
    seasons_table["Margin"] = seasons_table["average_margin"].map(lambda value: f"{value:+.2f}")
    seasons_table["SOS"] = seasons_table["strength_of_schedule"].map(lambda value: f"{value:.1%}")
    st.dataframe(seasons_table[["season", "Record", "Win %", "Margin", "SOS"]].rename(
        columns={"season": "Season"}), hide_index=True, width="stretch")


def player_detail(connection, player_id):
    player, memberships, matches, ratings = player_profile(connection, player_id)
    current = connection.execute(
        """SELECT team_name, gender, current_rating, rating_date
           FROM current_roster_players WHERE player_id=? LIMIT 1""", (int(player_id),)
    ).fetchone()
    st.title(player["display_name"])
    if current:
        st.caption(f"{current['team_name']} · {current['gender'].title()} · official {CURRENT_SEASON} roster")
    elif not memberships.empty:
        latest = memberships.iloc[0]
        st.caption(f"Latest verified roster: {latest['team']} · {latest['season']} · {latest['gender'].title()}")
    wins = int((matches["result"] == "W").sum()) if not matches.empty else 0
    metrics = st.columns(4)
    metrics[0].metric("Verified record", f"{wins}–{len(matches)-wins}")
    metrics[1].metric("Verified matches", len(matches))
    metrics[2].metric("Average position", f"{matches['position'].mean():.1f}" if not matches.empty else "—")
    if current:
        metrics[3].metric("Current rating", f"{current['current_rating']:.2f}")
        st.caption(f"Rating snapshot: {current['rating_date']}")
    elif not ratings.empty:
        metrics[3].metric("Latest historical rating", f"{ratings.iloc[-1]['rating']:.2f}")
    if not ratings.empty:
        st.subheader("Rating history")
        st.line_chart(ratings.rename(columns={"date": "Date", "rating": "Rating"}),
                      x="Date", y="Rating", x_label="Rating date", y_label="Official rating")
    if not matches.empty:
        st.subheader("Lineup position history")
        positions = matches.sort_values("date").rename(columns={"date": "Date", "position": "Position"})
        st.line_chart(positions, x="Date", y="Position", x_label="Match date", y_label="Lineup position")
        st.subheader("Recent individual matches")
        display = matches.head(25).copy()
        display["Date"] = display["date"].dt.strftime("%b %-d, %Y")
        st.dataframe(display[["Date", "season", "position", "opponent", "result", "score"]].rename(columns={
            "season": "Season", "position": "Position", "opponent": "Opponent",
            "result": "Result", "score": "Score"}), hide_index=True, width="stretch")
    st.caption("The record reflects verified CSA scorecards in this project and may not be the player’s complete career.")


def rankings_page(connection):
    st.title("Project Rankings")
    gender = st.segmented_control("Division", ["men", "women"], default="men", format_func=str.title,
                                  key="rank_gender")
    season = st.selectbox("Season", available_seasons(connection, gender))
    rankings = ranking_data(gender, season).copy()
    rankings["Record"] = rankings["wins"].astype(str) + "–" + rankings["losses"].astype(str)
    rankings["Elo"] = rankings["elo"].map(lambda value: f"{value:.0f}")
    rankings["SOS"] = rankings["strength_of_schedule"].map(lambda value: f"{value:.1%}")
    rankings["Margin"] = rankings["average_margin"].map(lambda value: f"{value:+.2f}")
    st.dataframe(rankings[["rank", "team", "Record", "Elo", "SOS", "Margin", "recent_form"]].rename(columns={
        "rank": "Rank", "team": "Team", "recent_form": "Recent form"}),
        hide_index=True, width="stretch", height=650)
    team = st.selectbox("Open team profile", rankings["team"].tolist())
    if st.button("View team profile"):
        st.session_state["navigation"] = "Teams"
        st.session_state["profile_gender"] = gender
        st.session_state["profile_team"] = team
        st.rerun()
    st.info("Project rankings are not official CSA rankings. Rank uses win percentage, then SOS, then average margin; Elo is displayed separately.")


def compare_page(connection):
    st.title("Compare Teams")
    gender = st.segmented_control("Division", ["men", "women"], default="men", format_func=str.title,
                                  key="compare_gender")
    teams = current_team_names(connection, gender)
    left, right = st.columns(2)
    with left:
        team_one = st.selectbox("Team A", teams, index=0)
    with right:
        team_two = st.selectbox("Team B", teams, index=1, key="compare_b")
    if team_one == team_two:
        st.warning("Choose two different teams.")
        return
    render_projection(connection, team_one, team_two, gender)
    st.subheader("Team summary")
    render_team_comparison(connection, team_one, team_two, gender)
    st.subheader("Historical meetings")
    render_historical_meetings(connection, team_one, team_two, gender)


def methodology_page():
    st.title("Methodology")
    st.write("This independent project uses public CSA / Club Locker schedules, scorecards, rosters, and rating histories. Source identifiers and URLs are retained; malformed or unavailable data is excluded rather than invented.")
    st.subheader("Preseason projection")
    st.write("A player is eligible only when listed on the official 2026–27 roster. The nine highest current roster ratings form the preseason order. Prior 2025–26 appearances affect the displayed lineup-confidence score, but cannot make an absent player eligible. This is explicitly a projection, not a confirmed lineup.")
    st.subheader("Ratings and probabilities")
    st.write("The individual model is the unchanged, validated logistic regression using official rating difference and lineup position. The preseason artifact is fit through 2025–26. Current roster ratings are timestamped at collection; historical predictions continue to enforce `rating_date < match_date`. Nine individual probabilities are combined exactly to estimate expected wins and the chance of winning at least five positions.")
    st.subheader("Prediction modes")
    st.markdown("- **Verified lineup:** exact pairings are known.\n- **Current-season projected lineup:** earlier same-season scorecards meet the validated evidence rule.\n- **Preseason projection:** current roster and current ratings, with prior lineup history used only as supporting evidence.\n- **Team-only:** fallback when a nine-player lineup cannot be formed.")
    st.subheader("Validation and limitations")
    st.write("On the untouched 2025–26 season, the team model achieved 78.4% accuracy, the fully covered verified-lineup model 89.6%, and the projected-lineup backtest 85.6%. Those samples differ and are not directly interchangeable. Preseason participation and exact order remain uncertain, roster ratings can change, historical feeds have gaps, and these are project estimates rather than official forecasts.")


def global_player_search(connection):
    st.sidebar.divider()
    query = st.sidebar.text_input("Find a player", placeholder="Type at least 2 letters")
    if len(query.strip()) < 2:
        return None
    results = player_search(connection, query.strip(), 30)
    if results.empty:
        st.sidebar.caption("No matching current or historical player")
        return None
    labels = {}
    for player in results.to_dict("records"):
        label = player_search_label(player)
        # Preserve access to both records if the visible context is identical.
        if label in labels:
            label = f"{label} · {player['player_id']}"
        labels[label] = int(player["player_id"])
    selected = st.sidebar.selectbox("Matching players", ["Choose a player", *labels])
    return labels.get(selected)


def player_search_label(player):
    """Build a readable search label without requiring optional context fields."""
    display_name = player.get("display_name") or "Unknown player"
    if "," in display_name:
        last_name, first_names = (part.strip() for part in display_name.split(",", 1))
        display_name = " ".join(part for part in (first_names, last_name) if part)

    team_name = player.get("canonical_team_name") or "Team unavailable"
    gender = str(player.get("gender") or "Division unavailable").title()
    season = player.get("season") or "Season unavailable"
    return f"{display_name} — {team_name}, {gender} ({season})"


def main():
    if not DATABASE_PATH.exists() or not PLAYER_MODEL_PATH.exists():
        st.error("Required database or preseason model artifact is missing.")
        st.stop()
    with connect_database(DATABASE_PATH) as connection:
        page = st.sidebar.radio("Navigate", PAGES, key="navigation")
        st.sidebar.caption("2026–27 · preseason projections")
        selected_player = global_player_search(connection)
        if selected_player:
            player_detail(connection, selected_player)
        elif page == "Schedule":
            schedule_page(connection)
        elif page == "Teams":
            team_page(connection)
        elif page == "Rankings":
            rankings_page(connection)
        elif page == "Compare":
            compare_page(connection)
        else:
            methodology_page()


if __name__ == "__main__":
    main()
