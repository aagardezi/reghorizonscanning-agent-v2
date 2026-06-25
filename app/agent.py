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

import os
import google.auth
from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, JoinNode, node
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.events.event import Event
from google.adk.agents.context import Context
from google.genai import types

from app.schemas import HorizonScanningRequest, SourceAnalysis, ComplianceBriefing
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
        "Identify the target firm type/profile (e.g. Retail Wealth Management, Mid-Tier Digital Bank, or BNPL Fintech) "
        "and any extra context (such as names to check in sanctions list, specific bills, or regulations like GDPR).\n"
        "Output a structured HorizonScanningRequest JSON object."
    ),
    output_schema=HorizonScanningRequest
)

@node
def set_state(ctx: Context, node_input: dict) -> Event:
    return Event(
        output=node_input,
        state={
            "firm_type": node_input.get("firm_type"),
            "extra_context": node_input.get("extra_context") or ""
        }
    )

# 2. Source-specific agents
fca_agent = LlmAgent(
    name="fca_agent",
    model=MODEL_NAME,
    instruction=(
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
        "You are a dedicated research agent. Use the `google_search` tool (Google Search Grounding) to:\n"
        "1. Look up historical regulatory rules, context, or documents for {firm_type} that are not covered by the current RSS feeds.\n"
        "2. Search for any specific topics mentioned in the extra context: {extra_context}.\n"
        "Provide a detailed text report of your findings."
    ),
    tools=[google_search]
)

# Synthesis agent fanning in the results and building the final structured briefing
synthesis_agent = LlmAgent(
    name="synthesis_agent",
    model=MODEL_NAME,
    instruction=(
        "You are the Head of Compliance and Risk Officer.\n"
        "You are compiling and synthesizing the analysis from individual source-specific compliance agents.\n"
        "Your task is to:\n"
        "1. Carefully read and cross-reference all parallel findings (FCA, PRA, HMT, Parliament, Legislation, Sanctions, Google Search) in the input.\n"
        "2. Highlight overlaps or contradictions between them (e.g., GDPR data breach notifications vs BoE operational resilience requirements).\n"
        "3. Group emerging compliance risks into High, Medium, and Low urgency categories.\n"
        "4. Formulate a final structured compliance briefing tailored specifically to the target firm profile: {firm_type}.\n"
        "Ensure your output strictly conforms to the ComplianceBriefing schema."
    ),
    output_schema=ComplianceBriefing
)

join_node = JoinNode(name="join_node")

root_agent = Workflow(
    name="root_agent",
    output_schema=ComplianceBriefing,
    edges=[
        ("START", splitter_agent),
        (splitter_agent, set_state),
        (set_state, (fca_agent, pra_agent, hmt_agent, parl_agent, leg_agent, sanctions_agent, google_search_agent)),
        ((fca_agent, pra_agent, hmt_agent, parl_agent, leg_agent, sanctions_agent, google_search_agent), join_node),
        (join_node, synthesis_agent)
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
