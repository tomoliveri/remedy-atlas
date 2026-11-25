const repo = "tomoliveri/remedy-atlas";
const issueUrl = `https://github.com/${repo}/issues/`;
const states = ["done", "ready", "running", "review", "pending", "failed", "cancelled", "held", "triage", "split"];

function metadata(issue) {
  const match = issue.body?.match(/<!--\s*ws:meta\s+(\{.*?\})\s*-->/s);
  try {
    return JSON.parse(match?.[1] ?? "{}") ?? {};
  } catch {
    return {};
  }
}

export function summarize(issues) {
  const jobs = new Map();
  const result = Object.create(null);
  for (const issue of issues) {
    if (issue.pull_request || !issue.labels.some(({name}) => name === "ws:job")) continue;
    const track = issue.body?.match(/<!-- atlas:track ([a-z0-9-]+) -->/)?.[1];
    if (!track) continue;
    jobs.set(issue.number, track);
    const summary = result[track] ??= {jobs: [], tasks: []};
    summary.jobs.push({url: issueUrl + issue.number, number: issue.number,
      state: states.find(state => issue.labels.some(({name}) => name === `ws:${state}`)) ?? "new"});
  }
  for (const issue of issues) {
    if (issue.pull_request || jobs.has(issue.number) || !issue.labels.some(({name}) => name === "ws:task")) continue;
    const track = jobs.get(metadata(issue).job);
    if (!track) continue;
    const state = states.find(status => issue.labels.some(({name}) => name === `ws:${status}`)) ?? "new";
    result[track].tasks.push({url: issueUrl + issue.number, title: issue.title, state});
  }
  return result;
}

export async function listIssues(fetcher = fetch) {
  const issues = [];
  for (let page = 1; page <= 10; page++) {
    const url = `https://api.github.com/repos/${repo}/issues?state=all&per_page=100&page=${page}`;
    const response = await fetcher(url, {headers: {
      "User-Agent": "Remedy-Atlas", "Accept": "application/vnd.github+json",
    }});
    if (!response.ok) throw new Error(`GitHub issues returned ${response.status}`);
    issues.push(...await response.json());
    if (!response.headers.get("Link")?.includes('rel="next"')) return issues;
  }
  throw new Error("GitHub issue feed exceeds the dashboard page limit");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/progress") return env.ASSETS.fetch(request);
    if (request.method !== "GET") return new Response(null, {status: 405, headers: {Allow: "GET"}});

    url.search = "";
    const cache = caches.default;
    const cached = await cache.match(url.toString());
    if (cached) return cached;
    try {
      const issues = await listIssues();
      const response = Response.json({updatedAt: new Date().toISOString(), tracks: summarize(issues)}, {
        headers: {"Cache-Control": "public, max-age=60"},
      });
      ctx.waitUntil(cache.put(url.toString(), response.clone()));
      return response;
    } catch (error) {
      console.error(error.message);
      return Response.json({error: "Live GitHub progress is temporarily unavailable."}, {
        status: 503, headers: {"Cache-Control": "no-store"},
      });
    }
  },
};
