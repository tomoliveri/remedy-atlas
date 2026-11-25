import {test} from "node:test";
import assert from "node:assert/strict";
import {listIssues, summarize} from "./worker.mjs";
import {roadmapStatus} from "../public/roadmap.mjs";

test("roadmap checks off a reviewed milestone only after all its jobs are done", () => {
  const status = (...states) => roadmapStatus("Active", {jobs: states.map(state => ({state}))});
  assert.equal(status("done", "done").complete, true);
  assert.equal(status("done", "ready").label, "Ready to claim");
  assert.equal(status("done", "failed").label, "Review needs follow-up");
  assert.equal(status("done", "cancelled").complete, false);
  assert.equal(roadmapStatus("On hold").label, "On hold");
});

test("jobs group reviewed, withdrawn and pending tasks using Workstead metadata", () => {
  const issue = (number, body, ...labels) => ({number, body, title: "Evidence task",
    labels: labels.map(name => ({name}))});
  const summary = summarize([
    issue(1, "<!-- atlas:track ndm -->", "ws:job", "ws:task", "ws:split"),
    issue(2, '<!-- ws:meta {"job":1} -->', "ws:task", "ws:done"),
    issue(3, '<!-- ws:meta {"job":1} -->', "ws:task", "ws:cancelled"),
    issue(4, '<!-- ws:meta {"job":99} -->', "ws:task", "ws:ready"),
    issue(5, '<!-- ws:meta {"job":1} -->', "ws:task", "ws:pending"),
    issue(6, "<!-- ws:meta {invalid} -->", "ws:task", "ws:ready"),
  ]);
  assert.deepEqual(Object.keys(summary), ["ndm"]);
  assert.deepEqual(summary.ndm.tasks.map(task => task.state), ["done", "cancelled", "pending"]);
  assert.equal(summary.ndm.jobs[0].state, "split");
});

test("GitHub pagination and upstream errors", async () => {
  const items = await listIssues(async url => new Response(JSON.stringify([url.slice(-1)]), {
    headers: url.endsWith("1") ? {Link: '<https://example.com>; rel="next"'} : {},
  }));
  assert.deepEqual(items, ["1", "2"]);
  await assert.rejects(listIssues(async () => new Response(null, {status: 429})), /429/);
});
