# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

# Compatibility shim for pyOpenSSL to prevent ValueError context reuse errors
def _agent_designer_pyopenssl_compat():
    try:
        from OpenSSL import SSL
    except Exception:
        return
    if getattr(SSL.Context, "_agent_designer_compat_applied", False):
        return

    class _AlwaysFalseUsed:
        def __get__(self, obj, objtype=None):
            return False
        def __set__(self, obj, value):
            return

    SSL.Context._used = _AlwaysFalseUsed()
    SSL.Context._agent_designer_compat_applied = True

_agent_designer_pyopenssl_compat()


try:
    import google.adk.flows.llm_flows.contents as adk_contents
    from google.adk.events.event import Event
    import google.adk.sessions.vertex_ai_session_service as vertex_session
    import uuid
    import google.adk.models.llm_response as adk_llm_response
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    import re

    # Save original functions
    _orig_contains_empty_content = adk_contents._contains_empty_content
    _orig_get_contents = adk_contents._get_contents
    _orig_from_api_event = vertex_session._from_api_event
    _orig_append_event = vertex_session.VertexAiSessionService.append_event
    _orig_llm_response_create = LlmResponse.create

    def patched_contains_empty_content(event: Event) -> bool:
        if event.actions and event.actions.compaction:
            return False

        has_visible_parts = False
        if event.content and event.content.parts:
            has_visible_parts = any(not adk_contents._is_part_invisible(p) for p in event.content.parts)

        if has_visible_parts:
            return False

        return _orig_contains_empty_content(event)

    def patched_get_contents(
        current_branch,
        events,
        agent_name="",
        *,
        preserve_function_call_ids=False,
        isolation_scope=None,
        is_single_turn=False,
        user_content=None,
    ):
        # 1. Filter out events that are annulled by a rewind
        rewind_filtered_events = []
        i = len(events) - 1
        while i >= 0:
            event = events[i]
            if event.actions and event.actions.rewind_before_invocation_id:
                rewind_invocation_id = event.actions.rewind_before_invocation_id
                for j in range(0, i, 1):
                    if events[j].invocation_id == rewind_invocation_id:
                        i = j
                        break
            else:
                rewind_filtered_events.append(event)
            i -= 1
        rewind_filtered_events.reverse()

        # 2. Filter by branch and isolation scope so we only pair function calls and responses
        # that are visible in the same context.
        visible_events = [
            e for e in rewind_filtered_events
            if adk_contents._should_include_event_in_context(
                current_branch, e, isolation_scope=isolation_scope
            )
        ]

        # Pre-process the visible events list to repair missing roles and function call/response IDs
        for i, event in enumerate(visible_events):
            # 1. Repair missing content roles
            if event.content and not event.content.role:
                if any(p.function_response for p in event.content.parts or []):
                    event.content.role = "user"
                elif event.author == "user":
                    event.content.role = "user"
                else:
                    event.content.role = "model"

            # 2. Repair missing function call/response IDs
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_response:
                        resp = part.function_response
                        resp_id = resp.id
                        if not resp_id:
                            resp_id = f"adk-{uuid.uuid4()}"
                            resp.id = resp_id
                        
                        # Search backward in visible_events for the nearest matching function call event of the same name
                        for j in range(i - 1, -1, -1):
                            prev_event = visible_events[j]
                            if prev_event.content and prev_event.content.parts:
                                matched = False
                                for prev_part in prev_event.content.parts:
                                    if prev_part.function_call and prev_part.function_call.name == resp.name:
                                        if not prev_part.function_call.id or prev_part.function_call.id != resp_id:
                                            prev_part.function_call.id = resp_id
                                            matched = True
                                            break
                                if matched:
                                    break

        return _orig_get_contents(
            current_branch=current_branch,
            events=events,
            agent_name=agent_name,
            preserve_function_call_ids=preserve_function_call_ids,
            isolation_scope=isolation_scope,
            is_single_turn=is_single_turn,
            user_content=user_content,
        )

    def patched_from_api_event(api_event_obj) -> Event:
        event = _orig_from_api_event(api_event_obj)
        # Restore fields from custom_metadata if raw_event is missing
        raw_event_dict = vertex_session._get_raw_event(api_event_obj)
        if not raw_event_dict and event.custom_metadata:
            if "_isolation_scope" in event.custom_metadata:
                event.isolation_scope = event.custom_metadata["_isolation_scope"]
            if "_output" in event.custom_metadata:
                event.output = event.custom_metadata["_output"]
            if "_node_info" in event.custom_metadata:
                from google.adk.events.event import NodeInfo
                event.node_info = NodeInfo.model_validate(event.custom_metadata["_node_info"])
        return event

    async def patched_append_event(self, session, event: Event) -> Event:
        # Populate isolation_scope, output, and node_info into custom_metadata before serialize/append
        if not event.custom_metadata:
            event.custom_metadata = {}
        if event.isolation_scope:
            event.custom_metadata["_isolation_scope"] = event.isolation_scope
        if event.output is not None:
            event.custom_metadata["_output"] = event.output
        if event.node_info and event.node_info.path:
            event.custom_metadata["_node_info"] = event.node_info.model_dump(mode="json")
        
        return await _orig_append_event(self, session, event)

    def patched_llm_response_create(generate_content_response) -> LlmResponse:
        response = _orig_llm_response_create(generate_content_response)
        if response.error_code and str(response.error_code) == "MALFORMED_FUNCTION_CALL" and response.error_message:
            error_msg = response.error_message
            if "set_model_response" in error_msg:
                # Reconstruct delimiter safely
                ctrl_prefix = "<" + "ctrl"
                ctrl_suffix = "46" + ">"
                ctrl_tag = ctrl_prefix + ctrl_suffix
                
                # Strip outer container first
                container_match = re.search(r"set_model_response\s*([{(])(.*)", error_msg, re.DOTALL)
                if container_match:
                    bracket = container_match.group(1)
                    rest = container_match.group(2).strip()
                    closing = "}" if bracket == "{" else ")"
                    if rest.endswith(closing):
                        error_msg = rest[:-1].strip()
                
                # 1. Extract decision
                decision = None
                decision_match = re.search(
                    rf"decision\s*[:=]\s*(?:{ctrl_tag})?\s*['\"]?(continue|retry)['\"]?\s*(?:{ctrl_tag})?",
                    error_msg
                )
                if decision_match:
                    decision = decision_match.group(1)
                
                # 2. Extract feedback
                feedback = None
                # Method A: Structured match using control tags
                feedback_match = re.search(
                    rf"feedback\s*[:=]\s*{ctrl_tag}(.*?){ctrl_tag}",
                    error_msg,
                    re.DOTALL
                )
                if feedback_match:
                    feedback = feedback_match.group(1)
                else:
                    # Method B: Structured match using quotes
                    feedback_match = re.search(
                        r"feedback\s*[:=]\s*['\"](.*?)['\"]",
                        error_msg,
                        re.DOTALL
                    )
                    if feedback_match:
                        feedback = feedback_match.group(1)
                
                # Method C: Fallback to everything after "feedback" up to "followup_queries" or the end
                if feedback is None:
                    feedback_section_match = re.search(
                        r"feedback\s*[:=]\s*(.*)",
                        error_msg,
                        re.DOTALL
                    )
                    if feedback_section_match:
                        feedback_part = feedback_section_match.group(1).strip()
                        # Split by followup_queries if it is present downstream
                        if "followup_queries" in feedback_part:
                            feedback_part, _ = re.split(r"\bfollowup_queries\b", feedback_part, maxsplit=1)
                        # Clean up trailing syntax elements like commas, whitespace
                        feedback_part = re.sub(r"[\s,]+$", "", feedback_part).strip()
                        # Clean up prefix/suffix control tags
                        if feedback_part.startswith(ctrl_tag):
                            feedback_part = feedback_part[len(ctrl_tag):]
                        if feedback_part.endswith(ctrl_tag):
                            feedback_part = feedback_part[:-len(ctrl_tag)]
                        feedback_part = feedback_part.strip()
                        # Clean up surrounding quotes
                        if len(feedback_part) >= 2 and feedback_part[0] in ('"', "'") and feedback_part[-1] == feedback_part[0]:
                            feedback_part = feedback_part[1:-1]
                        feedback = feedback_part.strip()

                if feedback is not None:
                    feedback = feedback.strip()
                    if len(feedback) >= 2 and feedback[0] in ('"', "'") and feedback[-1] == feedback[0]:
                        feedback = feedback[1:-1]
                    feedback = feedback.strip()
                
                # 3. Extract followup_queries
                followup_queries = []
                queries_match = re.search(
                    r"followup_queries\s*[:=]\s*(.*)",
                    error_msg,
                    re.DOTALL
                )
                if queries_match:
                    queries_part = queries_match.group(1).strip()
                    # Clean trailing chars
                    queries_part = re.sub(r"[\s,]+$", "", queries_part).strip()
                    if ctrl_tag in queries_part:
                        followup_queries = re.findall(rf"{ctrl_tag}(.*?){ctrl_tag}", queries_part)
                    else:
                        followup_queries = re.findall(r"['\"](.*?)['\"]", queries_part)
                
                if decision is not None and feedback is not None:
                    fc_id = f"adk-{uuid.uuid4()}"
                    func_call = types.FunctionCall(
                        name="default_api:set_model_response",
                        args={
                            "decision": decision,
                            "feedback": feedback,
                            "followup_queries": followup_queries
                        },
                        id=fc_id
                    )
                    response.content = types.Content(
                        role="model",
                        parts=[types.Part(function_call=func_call)]
                    )
                    response.finish_reason = types.FinishReason.STOP
                    response.error_code = None
                    response.error_message = None
                    import logging
                    logging.info("Successfully patched MALFORMED_FUNCTION_CALL for set_model_response. Reconstructed function call ID: %s", fc_id)
        return response

    # Apply patches
    adk_contents._contains_empty_content = patched_contains_empty_content
    adk_contents._get_contents = patched_get_contents
    vertex_session._from_api_event = patched_from_api_event
    vertex_session.VertexAiSessionService.append_event = patched_append_event
    LlmResponse.create = patched_llm_response_create

except Exception as e:
    import logging
    logging.warning("Failed to apply ADK compatibility patches: %s", e)


import datetime
from typing import Any
import os
import pathlib
import google.auth
from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, JoinNode, node
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.events.event import Event
from google.adk.agents.context import Context
from google.genai import types
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.schemas import HorizonScanningRequest, SourceAnalysis, ComplianceBriefing, CriticDecision
from app.tools import (
    get_fca_feed,
    get_pra_feed,
    get_hmt_feed,
    query_parliament_bills,
    get_legislation_feed,
    search_uk_sanctions_list,
)
from google.adk.tools import google_search
from google.adk.tools.load_web_page import load_web_page

# Set GCP credentials/project
try:
    _, project_id = google.auth.default()
except Exception:
    project_id = None
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or "genaillentsearch"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

MODEL_NAME = "gemini-flash-latest"

# Load new skills
regulatory_analysis_skill = load_skill_from_dir(pathlib.Path(__file__).parent / 'skills' / 'regulatory-analysis')
sanctions_audit_skill = load_skill_from_dir(pathlib.Path(__file__).parent / 'skills' / 'sanctions-audit')
compliance_critic_skill = load_skill_from_dir(pathlib.Path(__file__).parent / 'skills' / 'compliance-critic')

# Instantiate SkillToolset objects
regulatory_analysis_toolset = SkillToolset(skills=[regulatory_analysis_skill])
sanctions_audit_toolset = SkillToolset(skills=[sanctions_audit_skill])
compliance_critic_toolset = SkillToolset(skills=[compliance_critic_skill])
sanctions_critic_toolset = SkillToolset(skills=[sanctions_audit_skill, compliance_critic_skill])

# 1. Splitter Agent to parse natural language queries
splitter_agent = LlmAgent(
    name="splitter_agent",
    model=MODEL_NAME,
    instruction=(
        "You are an expert parsing assistant. Analyze the user query regarding regulatory horizon scanning.\n"
        "Identify the target firm type/profile (e.g. Retail Wealth Management, Mid-Tier Digital Bank, or BNPL Fintech),\n"
        "any extra context (such as names to check in sanctions list, specific bills, or regulations like GDPR),\n"
        "and check if the user specifies a particular date or year they want the analysis to be evaluated as of (e.g. 'as of Dec 2025' or 'in 2024').\n"
        "Output a structured HorizonScanningRequest JSON object."
    ),
    output_schema=HorizonScanningRequest
)

@node
def set_state(ctx: Context, node_input: dict) -> Event:
    as_of_date = node_input.get("as_of_date")
    if not as_of_date:
        as_of_date = datetime.date.today().isoformat()
    ctx.state["firm_type"] = node_input.get("firm_type")
    ctx.state["extra_context"] = node_input.get("extra_context") or ""
    ctx.state["current_date"] = as_of_date
    return Event(output=node_input)


# QA Critic instruction template
CRITIC_INSTRUCTION = (
    "Today's date is {current_date}.\n"
    "You are a Senior Regulatory Quality Assurance Critic.\n"
    "Your task is to review the compliance analysis produced by the domain agent for the firm profile: {firm_type}.\n"
    "Carefully evaluate the analysis against these criteria:\n"
    "1. Accuracy: Are all regulatory updates, names, and enforcement actions correct based on today's date?\n"
    "2. Completeness: Did the agent miss any key operational requirements or regulatory changes mentioned in the source?\n"
    "3. Actionability & Relevance: Are the operational impacts concrete, specific, and tailored for a {firm_type}?\n"
    "\n"
    "Decide whether the analysis is sufficient to proceed:\n"
    "- If there are clear gaps, missing dates, or generic recommendations, set decision='retry' and suggest specific, constructive follow-up search queries, entities, or section numbers in `followup_queries` and detail the issues in `feedback`.\n"
    "- If the analysis is thorough, accurate, and tailored, set decision='continue' and describe your approval in `feedback`."
)

# Dynamic router node factory
def create_critic_router(prefix: str):
    @node(name=f"route_{prefix}")
    def route_node(node_input: CriticDecision, context: Context) -> Any:
        context.state[f"{prefix}_feedback"] = node_input.feedback
        context.state[f"{prefix}_followup_queries"] = node_input.followup_queries
        
        loop_key = f"{prefix}_loop_count"
        context.state[loop_key] = context.state.get(loop_key, 0) + 1
        
        # Limit loops to max 2 iterations
        if context.state[loop_key] >= 2:
            context.route = "continue"
        else:
            context.route = node_input.decision
            
        if context.route == "continue":
            return context.state.get(f"{prefix}_analysis")
        else:
            return node_input.feedback
    return route_node

route_fca = create_critic_router("fca")
route_pra = create_critic_router("pra")
route_hmt = create_critic_router("hmt")
route_parl = create_critic_router("parl")
route_leg = create_critic_router("leg")
route_sanctions = create_critic_router("sanctions")
route_google_search = create_critic_router("google_search")

# Instantiate QA Critics
fca_critic = LlmAgent(
    name="fca_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)
pra_critic = LlmAgent(
    name="pra_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)
hmt_critic = LlmAgent(
    name="hmt_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)
parl_critic = LlmAgent(
    name="parl_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)
leg_critic = LlmAgent(
    name="leg_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)
sanctions_critic = LlmAgent(
    name="sanctions_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[sanctions_critic_toolset],
    output_schema=CriticDecision
)
google_search_critic = LlmAgent(
    name="google_search_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    tools=[compliance_critic_toolset],
    output_schema=CriticDecision
)

# 2. Source-specific agents
fca_agent = LlmAgent(
    name="fca_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {fca_feedback?}\n"
        "Critic follow-up queries (if any): {fca_followup_queries?}\n"
        "You are an expert compliance agent specialized in FCA (Financial Conduct Authority) updates.\n"
        "Your task is to:\n"
        "1. Fetch the latest FCA news feed using `get_fca_feed`.\n"
        "2. For relevant entries, fetch the target web page contents using `load_web_page`.\n"
        "3. Evaluate how these updates impact the target firm type: {firm_type}. Extra Context: {extra_context}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[get_fca_feed, load_web_page, regulatory_analysis_toolset],
    output_schema=SourceAnalysis,
    output_key="fca_analysis"
)

pra_agent = LlmAgent(
    name="pra_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {pra_feedback?}\n"
        "Critic follow-up queries (if any): {pra_followup_queries?}\n"
        "You are an expert compliance agent specialized in PRA (Prudential Regulation Authority) / Bank of England updates.\n"
        "Your task is to:\n"
        "1. Fetch the latest PRA/BoE publications using `get_pra_feed`.\n"
        "2. Fetch full target page contents using `load_web_page`.\n"
        "3. Analyze their compliance impact on the target firm type: {firm_type}. Extra Context: {extra_context}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[get_pra_feed, load_web_page, regulatory_analysis_toolset],
    output_schema=SourceAnalysis,
    output_key="pra_analysis"
)

hmt_agent = LlmAgent(
    name="hmt_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {hmt_feedback?}\n"
        "Critic follow-up queries (if any): {hmt_followup_queries?}\n"
        "You are an expert compliance agent specialized in HM Treasury (HMT) policy changes.\n"
        "Your task is to:\n"
        "1. Monitor announcements feed using `get_hmt_feed`.\n"
        "2. Fetch target page contents using `load_web_page`.\n"
        "3. Evaluate the compliance impact on the target firm type: {firm_type}. Extra Context: {extra_context}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[get_hmt_feed, load_web_page, regulatory_analysis_toolset],
    output_schema=SourceAnalysis,
    output_key="hmt_analysis"
)

parl_agent = LlmAgent(
    name="parl_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {parl_feedback?}\n"
        "Critic follow-up queries (if any): {parl_followup_queries?}\n"
        "You are an expert compliance agent specialized in UK Parliament legislative updates.\n"
        "Your task is to:\n"
        "1. Search bills using `query_parliament_bills` (use {extra_context} if provided as search_term, or search general terms).\n"
        "2. Fetch target page contents using `load_web_page` for relevant bills.\n"
        "3. Evaluate impact on the target firm type: {firm_type}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[query_parliament_bills, load_web_page, regulatory_analysis_toolset],
    output_schema=SourceAnalysis,
    output_key="parl_analysis"
)

leg_agent = LlmAgent(
    name="leg_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {leg_feedback?}\n"
        "Critic follow-up queries (if any): {leg_followup_queries?}\n"
        "You are an expert compliance agent specialized in UK Legislation and statutory changes.\n"
        "Your task is to:\n"
        "1. Fetch new legislation feed using `get_legislation_feed`.\n"
        "2. Fetch target page contents using `load_web_page`.\n"
        "3. Evaluate compliance impact on the target firm type: {firm_type}. Extra Context: {extra_context}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[get_legislation_feed, load_web_page, regulatory_analysis_toolset],
    output_schema=SourceAnalysis,
    output_key="leg_analysis"
)

sanctions_agent = LlmAgent(
    name="sanctions_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {sanctions_feedback?}\n"
        "Critic follow-up queries (if any): {sanctions_followup_queries?}\n"
        "You are an expert compliance agent specialized in financial crime and sanctions monitoring.\n"
        "Your task is to:\n"
        "1. Query the UK Sanctions List using `search_uk_sanctions_list` (use {extra_context} or other entities specified in the request as search query).\n"
        "2. Identify any designated entities, unique IDs, dates designated, and statement of reasons.\n"
        "3. Evaluate compliance and operational impact on the target firm type: {firm_type}.\n"
        "Generate a structured SourceAnalysis output."
    ),
    tools=[search_uk_sanctions_list, sanctions_audit_toolset],
    output_schema=SourceAnalysis,
    output_key="sanctions_analysis"
)

# Isolated Google Search agent to avoid mixing search grounding with custom tools in AFC
google_search_agent = LlmAgent(
    name="google_search_agent",
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        "Critic feedback (if any): {google_search_feedback?}\n"
        "Critic follow-up queries (if any): {google_search_followup_queries?}\n"
        "You are a dedicated research agent. Use the `google_search` tool (Google Search Grounding) to:\n"
        "1. Look up historical regulatory rules, context, or documents for {firm_type} that are not covered by the current RSS feeds.\n"
        "2. Search for any specific topics mentioned in the extra context: {extra_context}.\n"
        "Provide a detailed text report of your findings."
    ),
    tools=[google_search],
    output_key="google_search_analysis"
)

# Synthesis agent fanning in the results and building the final structured briefing
# Load the horizon-scanning skill
horizon_scanning_skill = load_skill_from_dir(
    pathlib.Path(__file__).parent / 'skills' / 'horizon-scanning'
)
synthesis_skill_toolset = SkillToolset(skills=[horizon_scanning_skill])

# Synthesis agent fanning in the results and building the final structured briefing
synthesis_agent = LlmAgent(
    name='synthesis_agent',
    model=MODEL_NAME,
    instruction=(
        "Today's date is {current_date}.\n"
        'You are the Head of Compliance and Risk Officer.\n'
        'You are compiling and synthesizing the analysis from individual source-specific compliance agents.\n'
        'Your task is to:\n'
        '1. Carefully read and cross-reference all parallel findings from the input dictionary (keys: route_fca, route_pra, route_hmt, route_parl, route_leg, route_sanctions, route_google_search).\n'
        '2. Highlight overlaps or contradictions between them (e.g., GDPR data breach notifications vs BoE operational resilience requirements).\n'
        '3. Group emerging compliance risks into High, Medium, and Low urgency categories.\n'
        '4. Formulate a final compliance briefing tailored specifically to the target firm profile: {firm_type}.\n'
        'Output a detailed, professional, and nicely formatted Markdown report. The report must contain these sections:\n'
        '# Executive Summary\n'
        '# Urgency Risk Categorization (detailing High, Medium, and Low risks)\n'
        '# Overlaps and Contradictions\n'
        '# Operational Impact Assessment (tailored to the target firm type: {firm_type})'
    ),
    tools=[synthesis_skill_toolset]
)

join_node = JoinNode(name="join_node")

root_agent = Workflow(
    name='root_agent',
    edges=[
        ("START", splitter_agent),
        (splitter_agent, set_state),
        
        # FCA loop branch
        (set_state, fca_agent),
        (fca_agent, fca_critic),
        (fca_critic, route_fca),
        (route_fca, {"retry": fca_agent, "continue": join_node}),
        
        # PRA loop branch
        (set_state, pra_agent),
        (pra_agent, pra_critic),
        (pra_critic, route_pra),
        (route_pra, {"retry": pra_agent, "continue": join_node}),
        
        # HMT loop branch
        (set_state, hmt_agent),
        (hmt_agent, hmt_critic),
        (hmt_critic, route_hmt),
        (route_hmt, {"retry": hmt_agent, "continue": join_node}),
        
        # Parliament loop branch
        (set_state, parl_agent),
        (parl_agent, parl_critic),
        (parl_critic, route_parl),
        (route_parl, {"retry": parl_agent, "continue": join_node}),
        
        # Legislation loop branch
        (set_state, leg_agent),
        (leg_agent, leg_critic),
        (leg_critic, route_leg),
        (route_leg, {"retry": leg_agent, "continue": join_node}),
        
        # Sanctions loop branch
        (set_state, sanctions_agent),
        (sanctions_agent, sanctions_critic),
        (sanctions_critic, route_sanctions),
        (route_sanctions, {"retry": sanctions_agent, "continue": join_node}),
        
        # Google Search loop branch
        (set_state, google_search_agent),
        (google_search_agent, google_search_critic),
        (google_search_critic, route_google_search),
        (route_google_search, {"retry": google_search_agent, "continue": join_node}),
        
        (join_node, synthesis_agent)
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
