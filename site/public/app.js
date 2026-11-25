const grid = document.querySelector("#tracks");
const feed = document.querySelector("#feed");
const filters = [...document.querySelectorAll("[data-filter]")];

let tracks = [];
let snapshot;
let filter = "All";

function element(tag, label, className) {
  const node = document.createElement(tag);
  node.textContent = label;
  if (className) node.className = className;
  return node;
}

function link(label, href) {
  const node = element("a", label);
  node.href = href;
  return node;
}

function card(track) {
  const issueData = snapshot?.tracks[track.id];
  const tasks = issueData?.tasks ?? [];
  const done = tasks.filter(task => task.state === "done").length;
  const remaining = tasks.filter(task => !["done", "split", "cancelled", "failed"].includes(task.state)).length;
  const underway = tasks.filter(task => ["running", "review"].includes(task.state)).length;

  const article = element("article", "", "card");
  const top = element("div", "", "card-top");
  const phase = trackPhase(track);
  top.append(element("p", track.area, "category"), element("span", phase, `phase ${phase.toLowerCase().replace(" ", "-")}`));
  const burden = element("div", "", "burden");
  burden.append(element("p", track.burden.label, "metric-label"),
    element("strong", track.burden.value), link("Source", track.burden.source));
  const gap = element("p", track.gap, "secondary");

  const queue = element("div", "", "queue");
  queue.append(element("p", track.next, "next"));
  if (issueData) {
    queue.append(element("p", tasks.length ? `${done} reviewed and closed · ${remaining} open · ${underway} underway` :
      "Planning activity in the public queue", "queue-summary"));
    const details = element("details", "", "queue-details");
    details.append(element("summary", "View queue activity"));
    const list = element("ul", "");
    for (const job of issueData.jobs) {
      const item = element("li", "");
      item.append(link(`Job #${job.number}`, job.url), document.createTextNode(` · ${job.state}`));
      list.append(item);
    }
    for (const task of tasks) {
      const item = element("li", "");
      item.append(link(task.title, task.url), document.createTextNode(` · ${task.state}`));
      list.append(item);
    }
    details.append(list);
    queue.append(details);
  }
  article.append(top, element("h3", track.name), element("p", track.question), burden, gap, queue);
  return article;
}

function trackPhase(track) {
  const jobs = snapshot?.tracks[track.id]?.jobs ?? [];
  if (jobs.length && jobs.every(job => job.state === "done")) return "Reviewed";
  return track.phase === "Queued" && jobs.length ? "Active" : track.phase;
}

function render() {
  const open = new Set([...grid.querySelectorAll("details[open]")].map(node =>
    `${node.closest("article").id}:${node.className}`));
  const active = document.activeElement;
  // Leave keyboard focus and the expanded links in place until focus leaves the queue.
  if (grid.contains(active) && active.matches("a, summary")) return;
  grid.replaceChildren(...tracks.filter(track => filter === "All" || trackPhase(track) === filter).map(track => {
    const node = card(track);
    node.id = track.id;
    for (const details of node.querySelectorAll("details")) {
      details.open = open.has(`${track.id}:${details.className}`);
    }
    return node;
  }));
}

function setFilter(value) {
  filter = value;
  for (const button of filters) button.setAttribute("aria-pressed", String(button.dataset.filter === value));
  render();
}

async function refresh() {
  try {
    const response = await fetch("/api/progress");
    if (!response.ok) throw new Error("queue unavailable");
    snapshot = await response.json();
    feed.textContent = `Live queue · checked ${new Date(snapshot.updatedAt).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}`;
    render();
  } catch {
    feed.textContent = snapshot
      ? `Refresh unavailable · last checked ${new Date(snapshot.updatedAt).toLocaleString()}`
      : "Live queue temporarily unavailable";
  }
}

for (const button of filters) {
  button.addEventListener("click", () => setFilter(button.dataset.filter));
}

try {
  const response = await fetch("/tracks.json");
  if (!response.ok) throw new Error("tracks unavailable");
  tracks = await response.json();
  render();
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  await refresh();
  setInterval(refresh, 45_000);
} catch {
  grid.textContent = "Research tracks are temporarily unavailable.";
  feed.textContent = "";
}
