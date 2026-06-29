import pytest
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types
import google.adk.flows.llm_flows.contents as adk_contents
import app.agent

def test_patched_get_contents_filtering():
    e1 = Event(
        invocation_id="inv-1",
        author="user",
        branch="main",
        content=types.Content(role="user", parts=[types.Part(text="hello")]),
    )
    e2 = Event(
        invocation_id="inv-2",
        author="agent1",
        branch="main.sub1",
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="tool_a", id="id-a"))]
        )
    )
    e3 = Event(
        invocation_id="inv-3",
        author="agent2",
        branch="main.sub2",
        content=types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="tool_a"))]
        )
    )
    e4 = Event(
        invocation_id="inv-4",
        author="agent1",
        branch="main.sub1",
        content=types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="tool_a"))]
        )
    )
    events = [e1, e2, e3, e4]
    contents = adk_contents._get_contents(
        current_branch="main.sub1",
        events=events,
        agent_name="agent1",
        preserve_function_call_ids=True,
    )
    assert e4.content.parts[0].function_response.id == e2.content.parts[0].function_call.id
    assert e3.content.parts[0].function_response.id is None

def test_patched_get_contents_isolation_scope():
    e1 = Event(
        invocation_id="inv-1",
        author="agent1",
        branch="main",
        isolation_scope="scope-a",
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="tool_a", id="id-a"))]
        )
    )
    e2 = Event(
        invocation_id="inv-2",
        author="agent1",
        branch="main",
        isolation_scope="scope-b",
        content=types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="tool_a"))]
        )
    )
    events = [e1, e2]
    contents = adk_contents._get_contents(
        current_branch="main",
        events=events,
        agent_name="agent1",
        preserve_function_call_ids=True,
        isolation_scope="scope-a",
    )
    assert e2.content.parts[0].function_response.id is None

def test_patched_get_contents_rewind():
    e1 = Event(
        invocation_id="inv-1",
        author="agent1",
        branch="main",
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="tool_a", id="id-a"))]
        )
    )
    e2 = Event(
        invocation_id="inv-2",
        author="agent1",
        branch="main",
        content=types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="tool_a"))]
        )
    )
    e3 = Event(
        invocation_id="inv-3",
        author="agent1",
        branch="main",
        actions=EventActions(rewind_before_invocation_id="inv-2")
    )
    events = [e1, e2, e3]
    contents = adk_contents._get_contents(
        current_branch="main",
        events=events,
        agent_name="agent1",
        preserve_function_call_ids=True,
    )
    assert e2.content.parts[0].function_response.id is None
