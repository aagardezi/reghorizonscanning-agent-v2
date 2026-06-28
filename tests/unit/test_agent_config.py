# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

from app.agent import (
    fca_agent, pra_agent, hmt_agent, parl_agent, leg_agent,
    sanctions_agent, fca_critic, pra_critic, hmt_critic, parl_critic,
    leg_critic, sanctions_critic, google_search_critic
)
from google.adk.tools.skill_toolset import SkillToolset

def test_agent_skills():
    # Helper to check if a toolset contains a skill with a specific name
    def has_skill(agent, skill_name):
        for tool in agent.tools:
            if isinstance(tool, SkillToolset):
                for skill in tool.skills:
                    if skill.name == skill_name:
                        return True
        return False

    # Domain-specific scanning agents should have regulatory-analysis skill
    assert has_skill(fca_agent, "regulatory-analysis"), "fca_agent missing regulatory-analysis"
    assert has_skill(pra_agent, "regulatory-analysis"), "pra_agent missing regulatory-analysis"
    assert has_skill(hmt_agent, "regulatory-analysis"), "hmt_agent missing regulatory-analysis"
    assert has_skill(parl_agent, "regulatory-analysis"), "parl_agent missing regulatory-analysis"
    assert has_skill(leg_agent, "regulatory-analysis"), "leg_agent missing regulatory-analysis"

    # sanctions_agent should have sanctions-audit skill
    assert has_skill(sanctions_agent, "sanctions-audit"), "sanctions_agent missing sanctions-audit"

    # sanctions_critic should have sanctions-audit and compliance-critic
    assert has_skill(sanctions_critic, "sanctions-audit"), "sanctions_critic missing sanctions-audit"
    assert has_skill(sanctions_critic, "compliance-critic"), "sanctions_critic missing compliance-critic"

    # All other critics should have compliance-critic
    assert has_skill(fca_critic, "compliance-critic"), "fca_critic missing compliance-critic"
    assert has_skill(pra_critic, "compliance-critic"), "pra_critic missing compliance-critic"
    assert has_skill(hmt_critic, "compliance-critic"), "hmt_critic missing compliance-critic"
    assert has_skill(parl_critic, "compliance-critic"), "parl_critic missing compliance-critic"
    assert has_skill(leg_critic, "compliance-critic"), "leg_critic missing compliance-critic"
    assert has_skill(google_search_critic, "compliance-critic"), "google_search_critic missing compliance-critic"
