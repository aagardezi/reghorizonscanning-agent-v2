import pytest
from unittest.mock import MagicMock
from app.agent import set_state, route_synthesis, skip_synthesis, create_critic_router
from google.adk.events.event import Event
from google.adk.agents.context import Context
from app.schemas import CriticDecision

def create_mock_context(state_dict=None):
    if state_dict is None:
        state_dict = {}
    mock_inv_ctx = MagicMock()
    mock_inv_ctx.session.state = state_dict
    mock_inv_ctx._state_schema = None
    return Context(mock_inv_ctx)

def test_set_state_initialization():
    ctx = create_mock_context()
    input_data = {"firm_type": "Mid-Tier Digital Bank", "as_of_date": "2026-06-29"}
    # Call underlying function
    event = set_state._func(ctx, input_data)
    
    assert ctx.state["firm_type"] == "Mid-Tier Digital Bank"
    assert ctx.state["current_date"] == "2026-06-29"
    
    prefixes = ["fca", "pra", "hmt", "parl", "leg", "sanctions", "google_search"]
    for prefix in prefixes:
        assert ctx.state[f"{prefix}_verified"] is False

def test_router_node_factory():
    # Test setting verified to True on continue
    route_fca = create_critic_router("fca")
    ctx = create_mock_context({"fca_verified": False})
    
    decision_continue = CriticDecision(decision="continue", feedback="Looks good", followup_queries=[])
    # Call underlying function
    res = route_fca._func(decision_continue, ctx)
    assert ctx.state["fca_verified"] is True
    assert ctx.route == "continue"

    # Test setting verified to False on retry
    ctx = create_mock_context({"fca_verified": True, "fca_loop_count": 0})
    decision_retry = CriticDecision(decision="retry", feedback="Need details", followup_queries=["search X"])
    # Call underlying function
    res = route_fca._func(decision_retry, ctx)
    assert ctx.state["fca_verified"] is False
    assert ctx.route == "retry"

def test_route_synthesis():
    # 1. Test when not all are verified
    ctx = create_mock_context({
        "fca_verified": True,
        "pra_verified": True,
        "hmt_verified": False, # one is False
        "parl_verified": True,
        "leg_verified": True,
        "sanctions_verified": True,
        "google_search_verified": True
    })
    
    input_data = {"some": "data"}
    # Call underlying function
    res = route_synthesis._func(input_data, ctx)
    assert ctx.route == "skip"
    assert "skipped" in res

    # 2. Test when all are verified
    ctx = create_mock_context({
        "fca_verified": True,
        "pra_verified": True,
        "hmt_verified": True,
        "parl_verified": True,
        "leg_verified": True,
        "sanctions_verified": True,
        "google_search_verified": True
    })
    
    # Call underlying function
    res = route_synthesis._func(input_data, ctx)
    assert ctx.route == "execute"
    assert res == input_data

def test_skip_synthesis():
    ctx = create_mock_context()
    # Call underlying function
    res = skip_synthesis._func("skipped path message", ctx)
    assert res is None
