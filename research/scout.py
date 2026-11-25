"""Find recent numerical drug-response and modelling papers for portfolio reviewers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html import unescape
import json
import re
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from workstead.gh import tls_context

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
AREAS = {
    "Cancer drug response": '(TITLE_ABS:organoid OR TITLE_ABS:"cell line") AND (TITLE_ABS:"drug response" OR TITLE_ABS:"drug sensitivity") AND TITLE_ABS:cancer',
    "Tumour dynamics and resistance": '(TITLE:tumor OR TITLE:tumour OR TITLE:cancer) AND (TITLE_ABS:"mathematical model" OR TITLE_ABS:simulation) AND (TITLE_ABS:resistance OR TITLE_ABS:treatment)',
    "Reproducible therapeutic modelling": '(TITLE_ABS:"dose response" OR TITLE_ABS:"drug response") AND (TITLE_ABS:benchmark OR TITLE_ABS:dataset) AND (TITLE_ABS:cancer OR TITLE_ABS:organoid)',
}


def papers_for(query, today, opener=urlopen):
    start = today - timedelta(days=90)
    params = urlencode({
        "query": (
            f"SRC:MED AND OPEN_ACCESS:y AND FIRST_PDATE:[{start} TO {today}] AND ({query}) "
            'NOT (PUB_TYPE:review OR PUB_TYPE:editorial OR PUB_TYPE:"retracted publication" OR TITLE:protocol) sort_date:y'
        ),
        "format": "json",
        "pageSize": 6,
    })
    with opener(f"{API}?{params}", timeout=12, context=tls_context()) as response:
        papers = json.load(response)["resultList"]["result"]
    return [paper for paper in papers
            if paper.get("source") == "MED" and re.fullmatch(r"[0-9]+", paper.get("id", ""))
            and paper.get("title") and str(paper.get("isRetracted", "")).upper() != "Y"]


def shortlist(today):
    def search(query):
        for attempt in range(2):
            try:
                return papers_for(query, today), True
            except (URLError, TimeoutError):
                if attempt == 0:
                    continue
            except (ValueError, KeyError, TypeError):
                break
        return [], False

    with ThreadPoolExecutor(max_workers=len(AREAS)) as workers:
        results = list(workers.map(search, AREAS.values()))

    if not any(ok for _, ok in results):
        return None
    lines = ["### New evidence to look at", "",
             "These are leads from the last 90 days. Check the population, methods and what changed for patients before recommending a new question.", ""]
    seen = set()
    for area, (papers, ok) in zip(AREAS, results):
        selected = []
        for paper in papers:
            identifier = paper["id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            title = " ".join(unescape(paper["title"]).split())[:240]
            # Escape Markdown and HTML from the bibliographic record.
            title = re.sub(r"([\\`*_{\[\]<>}|@])", r"\\\1", title)
            selected.append(f"  - [PubMed {identifier}](https://pubmed.ncbi.nlm.nih.gov/{identifier}/) · {title}")
            if len(selected) == 2:
                break
        if selected:
            lines.extend([f"- **{area}**", *selected])
        elif not ok:
            lines.append(f"- **{area}** · Search temporarily unavailable.")
    if all(not papers and ok for papers, ok in results):
        lines.append("No matching articles this week.")
    return "\n".join(lines)
