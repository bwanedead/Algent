

def test_read_depth_is_a_soft_bound_the_planner_judges_per_story() -> None:
    """Length decided where the shape is known, not discovered after the words exist.

    Minutes rather than words or sections: it is the unit the reader actually spends, and it
    stays soft. Unset (0) must render nothing — nothing downstream may invent a number.
    """
    from algent_backend.agent_system.agents.editorial.briefing import render_treatment
    from algent_backend.agent_system.agents.editorial.treatment import EditorialTreatment

    judged = render_treatment(EditorialTreatment(
        id="t1", title="X", read_minutes=4, read_minutes_why="one clean finding, one real caveat",
    ))
    assert "~4 min" in judged and "760-1000 words" in judged
    assert "one clean finding, one real caveat" in judged
    # Coming in under is a good outcome, not a shortfall — the drafter must be told so, or a
    # bound becomes a quota and the piece gets padded up to it.
    assert "STOP" in judged and "Default landing" in judged
    assert "Default landing" in judged and "1100 words" in judged

    generous = render_treatment(EditorialTreatment(
        id="t1b", title="X", read_minutes=10, read_minutes_why="everything is load-bearing",
    ))
    assert "1500 words" in generous
    assert "1750" not in generous and "2500" not in generous

    unjudged = render_treatment(EditorialTreatment(id="t2", title="X"))
    assert "How deep a read" not in unjudged
