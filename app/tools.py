# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

import xml.etree.ElementTree as ET
import csv
import os
import requests
from typing import List, Optional
from app.schemas import (
    FeedItem,
    FeedResponse,
    ParliamentBill,
    ParliamentResponse,
    SanctionsRow,
    SanctionsResponse,
)

# Helper functions for namespace handling
def find_local(element, tag_name):
    for child in element:
        local_name = child.tag.split("}")[-1]
        if local_name == tag_name:
            return child
    return None

def findall_local(element, tag_name):
    results = []
    for child in element:
        local_name = child.tag.split("}")[-1]
        if local_name == tag_name:
            results.append(child)
    return results

def parse_feed(url: str, limit: int = 10) -> List[FeedItem]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    
    items = []
    local_tag = root.tag.split("}")[-1]
    
    if local_tag == "feed": # Atom
        for entry in findall_local(root, "entry")[:limit]:
            title_elem = find_local(entry, "title")
            title = title_elem.text if (title_elem is not None and title_elem.text is not None) else ""
            
            link = ""
            for link_elem in findall_local(entry, "link"):
                rel = link_elem.attrib.get("rel", "")
                if rel in ("", "alternate", "self"):
                    link = link_elem.attrib.get("href", "")
                    if rel == "alternate":
                        break
            if link is None:
                link = ""
            
            summary_elem = find_local(entry, "summary")
            if summary_elem is None:
                summary_elem = find_local(entry, "content")
            description = summary_elem.text if (summary_elem is not None and summary_elem.text is not None) else None
            
            pub_date_elem = find_local(entry, "updated")
            if pub_date_elem is None:
                pub_date_elem = find_local(entry, "published")
            pub_date = pub_date_elem.text if (pub_date_elem is not None and pub_date_elem.text is not None) else ""
            
            items.append(FeedItem(
                title=title,
                link=link,
                pub_date=pub_date,
                description=description,
            ))
    else: # RSS
        channel = find_local(root, "channel")
        if channel is not None:
            for item in findall_local(channel, "item")[:limit]:
                title_elem = find_local(item, "title")
                title = title_elem.text if (title_elem is not None and title_elem.text is not None) else ""
                
                link_elem = find_local(item, "link")
                link = link_elem.text if (link_elem is not None and link_elem.text is not None) else ""
                
                description_elem = find_local(item, "description")
                description = description_elem.text if (description_elem is not None and description_elem.text is not None) else None
                
                pub_date_elem = find_local(item, "pubDate")
                pub_date = pub_date_elem.text if (pub_date_elem is not None and pub_date_elem.text is not None) else ""
                
                items.append(FeedItem(
                    title=title,
                    link=link,
                    pub_date=pub_date,
                    description=description,
                ))
    return items

def get_fca_feed(limit: int = 10) -> FeedResponse:
    """Fetches the latest news RSS feed from the Financial Conduct Authority (FCA).
    
    Args:
        limit: Maximum number of feed items to return (default: 10).
        
    Returns:
        FeedResponse containing the parsed feed items.
    """
    try:
        items = parse_feed("https://www.fca.org.uk/news/rss.xml", limit=limit)
        return FeedResponse(items=items)
    except Exception as e:
        print(f"Error fetching FCA feed: {e}")
        return FeedResponse(items=[])

def get_pra_feed(limit: int = 10) -> FeedResponse:
    """Fetches the latest publications RSS feed from the PRA / Bank of England.
    
    Args:
        limit: Maximum number of feed items to return (default: 10).
        
    Returns:
        FeedResponse containing the parsed feed items.
    """
    try:
        items = parse_feed("https://www.bankofengland.co.uk/rss/publications", limit=limit)
        return FeedResponse(items=items)
    except Exception as e:
        print(f"Error fetching PRA feed: {e}")
        return FeedResponse(items=[])

def get_hmt_feed(limit: int = 10) -> FeedResponse:
    """Fetches the latest Atom announcements feed from HM Treasury (HMT).
    
    Args:
        limit: Maximum number of feed items to return (default: 10).
        
    Returns:
        FeedResponse containing the parsed feed items.
    """
    try:
        items = parse_feed("https://www.gov.uk/government/organisations/hm-treasury.atom", limit=limit)
        return FeedResponse(items=items)
    except Exception as e:
        print(f"Error fetching HMT feed: {e}")
        return FeedResponse(items=[])

def get_legislation_feed(limit: int = 10) -> FeedResponse:
    """Fetches the latest statutory changes feed from UK Legislation (legislation.gov.uk).
    
    Args:
        limit: Maximum number of feed items to return (default: 10).
        
    Returns:
        FeedResponse containing the parsed feed items.
    """
    try:
        items = parse_feed("https://www.legislation.gov.uk/new/data.feed", limit=limit)
        return FeedResponse(items=items)
    except Exception as e:
        print(f"Error fetching legislation feed: {e}")
        return FeedResponse(items=[])

def query_parliament_bills(search_term: str, limit: int = 10) -> ParliamentResponse:
    """Queries the UK Parliament API for updates on legislative bills.
    
    Args:
        search_term: The search term or keyword to filter bills by (e.g. 'AI' or 'Digital').
        limit: Maximum number of bills to return (default: 10).
        
    Returns:
        ParliamentResponse containing the matching bills.
    """
    try:
        url = f"https://bills-api.parliament.uk/api/v1/Bills?searchTerm={search_term}&take={limit}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        bills = []
        for item in data.get("items", []):
            stage = item.get("currentStage") or {}
            stage_desc = stage.get("description") if stage else None
            bills.append(ParliamentBill(
                bill_id=item.get("billId"),
                title=item.get("shortTitle") or "",
                last_update=item.get("lastUpdate") or "",
                is_act=item.get("isAct") or False,
                stage=stage_desc
            ))
        return ParliamentResponse(items=bills)
    except Exception as e:
        print(f"Error querying UK Parliament Bills API: {e}")
        return ParliamentResponse(items=[])

def search_uk_sanctions_list(query: str) -> SanctionsResponse:
    """Downloads and searches the official daily UK Sanctions List (UKSL) CSV published by the FCDO.
    
    Args:
        query: The search term (e.g. name of person/entity, nationality, passport, unique ID).
        
    Returns:
        SanctionsResponse containing the matched sanctions entries.
    """
    csv_url = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv"
    local_path = "/tmp/UK-Sanctions-List.csv"
    
    try:
        # Download daily if not exists or cached
        if not os.path.exists(local_path):
            resp = requests.get(csv_url, timeout=30)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
                
        matches = []
        query_lower = query.lower()
        
        with open(local_path, mode="r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return SanctionsResponse(matches=[])
            
            header_line = lines[1]
            data_lines = lines[2:]
            
            reader = csv.DictReader([header_line] + data_lines)
            for row in reader:
                search_text = " ".join([
                    row.get("Unique ID", ""),
                    row.get("UN Reference Number", ""),
                    row.get("Name 6", ""),
                    row.get("Name 1", ""),
                    row.get("Name 2", ""),
                    row.get("Name 3", ""),
                    row.get("Name 4", ""),
                    row.get("Name 5", ""),
                    row.get("Regime Name", ""),
                    row.get("UK Statement of Reasons", ""),
                    row.get("Nationality(/ies)", ""),
                    row.get("Passport number", "")
                ]).lower()
                
                names_found = []
                for name_col in ["Name 1", "Name 2", "Name 3", "Name 4", "Name 5", "Name 6"]:
                    val = row.get(name_col, "").strip()
                    if val:
                        names_found.append(val)
                
                if query_lower in search_text:
                    cleaned_row = SanctionsRow(
                        unique_id=row.get("Unique ID", ""),
                        ofsi_group_id=row.get("OFSI Group ID", ""),
                        regime_name=row.get("Regime Name", ""),
                        names=names_found,
                        sanctions_imposed=row.get("Sanctions Imposed", ""),
                        uk_statement_of_reasons=row.get("UK Statement of Reasons", "")[:500],
                        date_designated=row.get("Date Designated", ""),
                        position=row.get("Position"),
                        dob=row.get("D.O.B"),
                        nationality=row.get("Nationality(/ies)"),
                    )
                    matches.append(cleaned_row)
                    if len(matches) >= 20:
                        break
                        
        return SanctionsResponse(matches=matches)
    except Exception as e:
        print(f"Error searching UK sanctions list: {e}")
        return SanctionsResponse(matches=[])
