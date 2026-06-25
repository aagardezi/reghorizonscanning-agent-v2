# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from pydantic import BaseModel, Field
from typing import List, Optional

class FeedItem(BaseModel):
    title: str = Field(description="Title of the news or publication item")
    link: str = Field(description="Link to the target web page")
    pub_date: str = Field(description="Published date of the item")
    description: Optional[str] = Field(default=None, description="Short summary/description of the item")

class FeedResponse(BaseModel):
    items: List[FeedItem] = Field(description="List of feed items")

class ParliamentBill(BaseModel):
    bill_id: int = Field(description="Internal ID of the bill")
    title: str = Field(description="Title of the bill")
    last_update: str = Field(description="Last update timestamp")
    is_act: bool = Field(description="Whether the bill has become an Act of Parliament")
    stage: Optional[str] = Field(default=None, description="Current stage description of the bill")

class ParliamentResponse(BaseModel):
    items: List[ParliamentBill] = Field(description="List of matching bills")

class SanctionsRow(BaseModel):
    unique_id: str = Field(description="Unique ID of the sanctioned individual or entity")
    ofsi_group_id: str = Field(description="OFSI Group ID")
    regime_name: str = Field(description="Sanction regime name")
    names: List[str] = Field(description="List of names/aliases associated with the entity")
    sanctions_imposed: str = Field(description="Details of sanctions imposed")
    uk_statement_of_reasons: str = Field(description="Official UK statement of reasons")
    date_designated: str = Field(description="Date designated")
    position: Optional[str] = Field(default=None, description="Position held by the entity")
    dob: Optional[str] = Field(default=None, description="Date of birth")
    nationality: Optional[str] = Field(default=None, description="Nationality of the individual")

class SanctionsResponse(BaseModel):
    matches: List[SanctionsRow] = Field(description="List of matching sanctioned entities")

class FirmProfile(BaseModel):
    firm_type: str = Field(description="Type of the firm (e.g. Retail Wealth Management, Mid-Tier Digital Bank, BNPL Fintech)")
    description: Optional[str] = Field(default=None, description="Optional brief details about the firm profile")

class SynthesisInput(BaseModel):
    fca_analysis: Optional[str] = Field(default=None)
    pra_analysis: Optional[str] = Field(default=None)
    hmt_analysis: Optional[str] = Field(default=None)
    parliament_analysis: Optional[str] = Field(default=None)
    legislation_analysis: Optional[str] = Field(default=None)
    sanctions_analysis: Optional[str] = Field(default=None)
    google_search_grounding: Optional[str] = Field(default=None)

class SourceAnalysis(BaseModel):
    source_name: str = Field(description="Name of the source analyzed (e.g. FCA, PRA, HMT, Parliament, Legislation, Sanctions, Google Search)")
    summary: str = Field(description="Concise summary of updates found")
    operational_impact: str = Field(description="Operational impact assessment for the target firm profile")
    detected_risks: List[str] = Field(description="List of specific risks identified")

class ComplianceBriefing(BaseModel):
    summary: str = Field(description="Executive summary of major regulatory changes")
    high_urgency_risks: List[str] = Field(description="Emerging risks requiring immediate attention (High Urgency)")
    medium_urgency_risks: List[str] = Field(description="Emerging risks requiring near-term attention (Medium Urgency)")
    low_urgency_risks: List[str] = Field(description="Emerging risks of low urgency / monitoring status")
    overlaps_and_contradictions: List[str] = Field(description="Alerts regarding overlapping or conflicting rules (e.g., GDPR notifications vs BoE operational resilience)")
    operational_impact_assessment: str = Field(description="Assessment of operational impact tailored specifically to the target firm profile")

class HorizonScanningRequest(BaseModel):
    firm_type: str = Field(description="The firm profile (e.g. Retail Wealth Management, Mid-Tier Digital Bank, BNPL Fintech)")
    extra_context: Optional[str] = Field(default=None, description="Optional extra context or query detail (e.g. searching for sanctions names or specific topics)")
