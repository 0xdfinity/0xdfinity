#!/usr/bin/env python3
"""Rewrites the text between the latest-commits markers in README.md.

Lists the top 3 public repos the profile owner most recently committed to,
excluding the profile repo itself. Candidates come from his public push events
and his commit search; each repo is ranked by his newest commit in it.
"""
import html
import json
import os
import urllib.parse
import urllib.request

USER = "0xdfinity"
PROFILE_REPO = "0xdfinity/0xdfinity"
START = "<!--START_SECTION:latest-commits-->"
END = "<!--END_SECTION:latest-commits-->"
README = os.environ.get("README_PATH", "README.md")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
LIMIT = 3


def api_get(path_or_url):
    url = path_or_url if path_or_url.startswith("http") else "https://api.github.com/" + path_or_url
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "latest-commits-updater",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def candidate_repos():
    names = []
    try:
        for ev in api_get(f"users/{USER}/events/public?per_page=100"):
            if ev.get("type") == "PushEvent":
                names.append(ev["repo"]["name"])
    except Exception as exc:  # events are best effort
        print("events lookup skipped:", exc)
    query = urllib.parse.quote(f"author:{USER} is:public")
    for page in range(1, 6):
        try:
            data = api_get(f"search/commits?q={query}&sort=committer-date&order=desc&per_page=100&page={page}")
        except Exception as exc:
            print("commit search skipped:", exc)
            break
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            names.append(item["repository"]["full_name"])
        if len({n.lower() for n in names}) >= 25:
            break
    seen, out = set(), []
    for n in names:
        key = n.lower()
        if key not in seen and key != PROFILE_REPO.lower():
            seen.add(key)
            out.append(n)
    return out


def latest_commit(full):
    try:
        repo = api_get(f"repos/{full}")
    except Exception:
        return None
    if repo.get("private") or repo.get("visibility", "public") != "public":
        return None
    try:
        commits = api_get(f"repos/{full}/commits?author={USER}&per_page=1")
    except Exception:
        return None
    if not commits:
        return None
    c = commits[0]
    msg = c["commit"]["message"].splitlines()[0].strip() or "(no message)"
    if len(msg) > 80:
        msg = msg[:77] + "..."
    return {
        "name": repo["full_name"],
        "url": repo["html_url"],
        "msg": msg,
        "sha": c["sha"][:7],
        "date": c["commit"]["committer"]["date"][:10],
        "when": c["commit"]["committer"]["date"],
        "commit_url": c["html_url"],
    }


def top_repos():
    found = [r for r in (latest_commit(n) for n in candidate_repos()) if r]
    found.sort(key=lambda r: r["when"], reverse=True)
    return found[:LIMIT]


def clean(text):
    return text.replace("\u2014", ":").replace("\u2013", "-")


def render(repos):
    lines = []
    for r in repos:
        lines.append(
            f"- [{html.escape(r['name'])}]({r['url']}): "
            f"{html.escape(clean(r['msg']))} "
            f"([{r['sha']}]({r['commit_url']}), {r['date']})"
        )
    return "\n".join(lines)


def main():
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    if START not in text or END not in text:
        raise SystemExit("markers missing from README")
    repos = top_repos()
    if not repos:
        print("no public commits found; README unchanged")
        return
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new_text = head + START + "\n" + render(repos) + "\n" + END + tail
    if new_text == text:
        print("no change")
        return
    with open(README, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    print("README updated")


if __name__ == "__main__":
    main()
