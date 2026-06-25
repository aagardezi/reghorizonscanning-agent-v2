# Data Sources for horizon scanning

## Financial Conduct Authority (FCA)
FCA News & Speeches: https://www.fca.org.uk/news/rss.xml
FCA Regulatory Handbook Updates: https://www.handbook.fca.org.uk/handbook/rss

## Prudential Regulation Authority (PRA) / Bank of England
PRA News & Publications: https://www.bankofengland.co.uk/rss/publications
PRA Regulatory Digest: https://www.bankofengland.co.uk/rss/regulatory-digest

BOA Datasets: https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp?Travel=NIxAZxSUx&FromSeries=1&ToSeries=50&DAT=RNG&FD=1&FM=Jan&FY=2012&TD=13&TM=Nov&TY=2027&FNY=Y&CSVF=TT&html.x=66&html.y=26&SeriesCodes=IUMZICQ,IUMBV34,IUMZICR,IUMB482,IUM2WTL,IUMBV37,IUMBV42,IUM5WTL,IUMBV45,IUMBV48,IUMB479,IUM2WDT,IUMBV24,IUMTLMV,IUMZID4,IUMBX67,IUMHPTL,IUMCCTL,IUMODTL,IUMB6VJ,IUMB6VK,IUMB6VL,IUMB6VM,IUMB6VN,IUMZID2,IUMWTFA,IUMB6RH,IUMB6RI&UsingCodes=Y&Filter=N&title=Quoted%20Rates&VPD=Y

## HM Treasury (HMT)
HMT Announcements & Consultations: https://www.gov.uk/government/organisations/hm-treasury.atom

## UK Parliament
All apis are unauthenticated and the details are avaiable on the developer portal: https://developer.parliament.uk/ use this portal to build a library that calls the apis and can then access the data as required

## UK Legislation (The Statute Book)
API Base URL: https://www.legislation.gov.uk/

How to use it: This is a remarkably developer-friendly REST API run by the National Archives. You don't need a developer account or an API key. You can append /data.xml or /data.feed to any legislation URL on the site to return the structured data directly into your agent.

Legislation api details: https://legislation.github.io/data-documentation/api/overview.html

## Office of Financial Sanctions Implementation (OFSI)
Sanctions Update Feed (Atom/RSS): https://www.gov.uk/government/collections/financial-sanctions-regime-specific-consolidated-lists-and-releases.atom

Because sanctions tracking needs to be foolproof, instead of purely scraping the feed, your agent tool should download and parse the OFSI Consolidated Sanctions List (available in JSON/CSV format) updated daily via https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets


# Testing
An effective horizon scanning agent for UK financial institutions shouldn't just act like a search engine; it should connect the dots between raw regulatory text and the actual operational impact on a firm.

Depending on whether your team wants high-level strategic updates or tactical compliance action points, here are the main categories and specific examples of prompts you can use to train and test your Gemini-powered agent:

---

## 1. Direct Impact & Actionability Prompts

These prompts test the agent’s ability to map a complex regulatory update to specific business lines.

* > "Summarize the FCA's Policy Statement published this morning on the Consumer Duty. What are the top three concrete changes a **retail wealth management firm** needs to implement before next quarter?"


* > "Scan the latest PRA consultations. Are there any upcoming revisions to capital adequacy or liquidity requirements that will affect **mid-tier digital banks** in the UK?"


* > "We are a **Fintech firm launching a buy-now-pay-later (BNPL) product**. Search the latest HM Treasury announcements to see if draft legislation has advanced regarding the regulation of unregulated credit."



---

## 2. Cross-Reference & Contradiction Alerts

These prompts evaluate if the agent can cross-reference multiple data sources (e.g., comparing a government bill with an FCA rulebook) to spot upcoming compliance bottlenecks.

* > "Cross-reference the newly introduced UK Parliament Artificial Intelligence Bill with existing FCA guidance on algorithmic trading. Are there conflicting requirements regarding accountability, or does one authority defer to the other?"


* > "Look at the latest information security updates from the ICO regarding UK GDPR and compare them with the operational resilience rules issued by the Bank of England. Do we have overlapping reporting deadlines if a data breach occurs?"



---

## 3. Financial Crime & Sanctions Triggers

These prompts require rapid, absolute precision using the data feeds from OFSI and Companies House.

* > "Analyze the OFSI sanctions list update from today. Highlight any newly designated entities or individuals that intersect with our standard sector exposure in maritime trade finance."


* > "Are there any newly flagged warning signs or advisory notices published by the National Crime Agency (NCA) regarding money laundering vectors involving UK-registered shell companies this month?"



---

## 4. Trend & Sentiment Analysis

These prompts leverage Gemini's large context window to look over months of data and identify where the regulatory wind is blowing.

* > "Review all FCA and PRA speeches given over the last six months. Map the frequency of keywords related to 'Greenwashing' and 'ESG disclosure'. Is enforcement action expected to tighten, and what specific sectors are being singled out?"


* > "Based on the discussion papers released by the Bank of England over the last year, compile a timeline showing their projected roadmap for the Digital Pound (Central Bank Digital Currency) and note when pilot phases are expected to impact commercial banking infrastructure."



---

## 5. Tailored Executive Briefings

These prompts ask the agent to synthesize massive amounts of scattered data into a clean, concise, human-ready format.

* > "Create a 500-word Executive Briefing for our Chief Risk Officer detailing all regulatory horizon risks introduced across the UK financial sector in the last 7 days. Group them by urgency: High, Medium, and Low."
