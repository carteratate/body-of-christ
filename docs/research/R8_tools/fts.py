"""Internet Archive full-text search. usage: fts.py 'query' [maxyear] [n]"""
import json, sys, time, urllib.parse, urllib.request
def fts(q, n=100, tries=4):
    url = ("https://archive.org/services/search/beta/page_production/?" +
           urllib.parse.urlencode(dict(user_query=q, service_backend="fts", hits_per_page=n, page_type="search_results")))
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "TheoCorpus-research/1.0 (carteratatect research)"}), timeout=60))
            r = d["response"]
            if r.get("error"): raise RuntimeError(r["error"]["message"][:200])
            return r["body"]["hits"]
        except Exception as e:
            err = e; time.sleep(3 * (i + 1))
    raise err
def year(f):
    y = f.get("year")
    if y: return int(y)
    dt = f.get("date") or ""
    return int(dt[:4]) if dt[:4].isdigit() else None
if __name__ == "__main__":
    q = sys.argv[1]; maxy = int(sys.argv[2]) if len(sys.argv) > 2 else 9999; n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    h = fts(q, n)
    print(f"total={h['total']} returned={h['returned']}")
    rows = []
    for x in h["hits"]:
        f = x["fields"]; y = year(f)
        rows.append((y if y else 9999, f["identifier"], (f.get("title") or "")[:70], f.get("page_num"), " … ".join((x.get("highlight") or {}).get("text") or [])[:220]))
    for r in sorted(rows):
        if r[0] <= maxy or r[0] == 9999:
            print(r[0] if r[0] != 9999 else "????", r[1], "|", r[2], "| p", r[3], "|", r[4].replace("\n", " "))
