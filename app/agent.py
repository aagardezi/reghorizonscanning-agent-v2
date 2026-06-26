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
    output_schema=CriticDecision
)
pra_critic = LlmAgent(
    name="pra_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    output_schema=CriticDecision
)
hmt_critic = LlmAgent(
    name="hmt_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    output_schema=CriticDecision
)
parl_critic = LlmAgent(
    name="parl_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    output_schema=CriticDecision
)
leg_critic = LlmAgent(
    name="leg_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    output_schema=CriticDecision
)
sanctions_critic = LlmAgent(
    name="sanctions_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
    output_schema=CriticDecision
)
google_search_critic = LlmAgent(
    name="google_search_critic",
    model=MODEL_NAME,
    instruction=CRITIC_INSTRUCTION,
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
    tools=[get_fca_feed, load_web_page],
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
    tools=[get_pra_feed, load_web_page],
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
    tools=[get_hmt_feed, load_web_page],
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
    tools=[query_parliament_bills, load_web_page],
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
    tools=[get_legislation_feed, load_web_page],
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
    tools=[search_uk_sanctions_list],
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
        '1. Carefully read and cross-reference all parallel findings (FCA, PRA, HMT, Parliament, Legislation, Sanctions, Google Search) in the input.\n'
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
