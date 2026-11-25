export function roadmapStatus(phase, issueData) {
  const jobs = issueData?.jobs ?? [];
  const tasks = issueData?.tasks ?? [];
  if (jobs.length && jobs.every(job => job.state === "done")) {
    return {label: "Evidence milestone complete", complete: true};
  }

  let label = phase;
  if (jobs.length) {
    const states = [...jobs, ...tasks].map(item => item.state);
    if (phase === "On hold") label = phase;
    else if (states.some(state => state === "running" || state === "review")) label = "Review underway";
    else if (states.includes("ready")) label = "Ready to claim";
    else if (jobs.every(job => ["done", "failed", "cancelled"].includes(job.state))) label = "Review needs follow-up";
    else label = "In the research queue";
  }
  return {label, complete: false};
}
