---
name: compliance-critic
description: QA rubric and instructions for evaluating regulatory compliance analyses and generating constructive feedback loops.
---

# QA Critic Standards

When reviewing and auditing domain compliance reports:
- **Accuracy Check**: Verify all references, dates, and names. Flag any outdated references (e.g., Solvency UK must be treated as live, not pending).
- **Completeness Check**: Ensure the analysis covers all critical points in the source document.
- **Actionability Check**: Verify operational impacts are mapped to specific departments and express concrete actions. Flag generic suggestions like "monitor updates" or "be compliant" as failures.
- **Decision Logic**:
  * If the analysis fails any check, set decision='retry', detail the issues in `feedback`, and provide specific, constructive search terms or sections to query in `followup_queries`.
  * If perfect, set decision='continue' and approve.
