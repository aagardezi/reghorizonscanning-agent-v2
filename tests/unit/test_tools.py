# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

import unittest
from unittest.mock import patch, MagicMock
from app.tools import parse_feed, query_parliament_bills, search_uk_sanctions_list

def test_parse_feed_rss():
    mock_xml = """<rss><channel>
        <item>
            <title>FCA Update 1</title>
            <link>https://fca.org.uk/1</link>
            <description>FCA Desc 1</description>
            <pubDate>Mon, 22 Jun 2026 12:00:00 GMT</pubDate>
        </item>
    </channel></rss>"""
    with patch("requests.get") as mock_get:
        mock_get.return_value.content = mock_xml.encode("utf-8")
        mock_get.return_value.status_code = 200
        res = parse_feed("https://mockurl.com/rss")
        assert len(res) == 1
        assert res[0].title == "FCA Update 1"
        assert res[0].link == "https://fca.org.uk/1"

def test_parse_feed_atom():
    mock_xml = """<feed xmlns=\"http://www.w3.org/2005/Atom\">
        <entry>
            <title>HMT Announcement 1</title>
            <link href=\"https://hmt.gov.uk/1\"/>
            <summary>HMT Summary 1</summary>
            <updated>2026-06-22T12:00:00Z</updated>
        </entry>
    </feed>"""
    with patch("requests.get") as mock_get:
        mock_get.return_value.content = mock_xml.encode("utf-8")
        mock_get.return_value.status_code = 200
        res = parse_feed("https://mockurl.com/atom")
        assert len(res) == 1
        assert res[0].title == "HMT Announcement 1"
        assert res[0].link == "https://hmt.gov.uk/1"

def test_fetch_parliament_bills():
    mock_json = {
        "items": [
            {"billId": 123, "shortTitle": "AI Regulation Bill", "lastUpdate": "2026-06-22T12:00:00Z", "isAct": False}
        ]
    }
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_json
        mock_get.return_value.status_code = 200
        res = query_parliament_bills("AI")
        assert len(res.items) == 1
        assert res.items[0].title == "AI Regulation Bill"

def test_search_uk_sanctions_list():
    mock_csv = "Report Date: 24-Jun-2026\nLast Updated,Unique ID,OFSI Group ID,UN Reference Number,Name 6,Name 1,Name 2,Name 3,Name 4,Name 5,Name type,Alias strength,Title,Name non-latin script,Non-latin script type,Non-latin script language,Regime Name,Designation Type,Designation source,Sanctions Imposed,Other Information,UK Statement of Reasons,Address Line 1,Address Line 2,Address Line 3,Address Line 4,Address Line 5,Address Line 6,Address Postal Code,Address Country,Phone number,Website,Email address,Date Designated,D.O.B,Nationality(/ies),National Identifier number,National Identifier additional information,Passport number,Passport additional information,Position,Gender,Town of birth,Country of birth,Type of entity,Subsidiaries,Parent company,Business registration number (s),IMO number,Current owner/operator (s),Previous owner/operator (s),Current believed flag of ship,Previous flags,Type of ship,Tonnage of ship,Length of ship,Year Built,Hull identification number (HIN)\n16/04/2026,AFG0001,12703,TAe.010,HAJI KHAIRULLAH HAJI SATTAR MONEY EXCHANGE,,,,,,Primary Name,,,حاجی خيرالله و حاجی ستار صرافی,,,The Afghanistan (Sanctions) (EU Exit) Regulations 2020,Entity,UN,Asset freeze,Afghan Money Service Provider License Number: 044., ,Branch Office 10,,,,,,,,,,,,,,29/06/2012,,,,,,,,,,,,,,,,,,,,,,,,\n"
    with patch("os.path.exists") as mock_exists, \
         patch("builtins.open", unittest.mock.mock_open(read_data=mock_csv)):
        mock_exists.return_value = True
        res = search_uk_sanctions_list("HAJI KHAIRULLAH")
        assert len(res.matches) == 1
        assert any("HAJI KHAIRULLAH" in name for name in res.matches[0].names)
