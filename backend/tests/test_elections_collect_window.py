from datetime import date

from algent_backend.elections import polls
from algent_backend.elections.collect import current


def test_past_election_titles_are_not_current():
    today = date(2026, 10, 31)
    assert current("2026 Israeli legislative election", today) and current("2025 Bulgarian election", today) and current("2027 French election", today)
    assert not current("2022 Israeli legislative election", today) and not current("2008 United States presidential election", today)


def test_bloc_columns_are_not_parties():
    assert all(polls._OTHER.match(x) for x in ("Gov.", "Opp.", "Total", "Govt"))
    assert not polls._OTHER.match("Government of National Unity") and not polls._OTHER.match("Likud")
