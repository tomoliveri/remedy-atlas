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

function impactValue(impact) {
  const inputs = [impact.baselineDeaths, impact.eligibleFraction, impact.reach, impact.mortalityReduction];
  const format = new Intl.NumberFormat(undefined, {maximumSignificantDigits: 2});
  const [low, high] = [0, 1].map(bound =>
    format.format(inputs.reduce((product, input) => product * input[bound], 1)));
  return low === high ? low : `${low}–${high}`;
}

function card(track) {
  const issueData = snapshot?.tracks[track.id];
  const tasks = issueData?.tasks ?? [];
  const done = tasks.filter(task => task.state === "done").length;
  const remaining = tasks.filter(task => !["done", "split", "cancelled", "failed"].includes(task.state)).length;
  const underway = tasks.filter(task => ["running", "review"].includes(task.state)).length;

  const article = element("article", "", "card");
  const top = element("div", "", "card-top");
  top.append(element("p", track.area, "category"), element("span", track.phase, `phase ${track.phase.toLowerCase().replace(" ", "-")}`));
  const impact = element("div", "", "metrics");
  const context = element("div", "", "metric");
  context.append(element("p", "Reported burden", "metric-label"),
    element("strong", track.burden.value), element("p", track.burden.label, "secondary"),
    link("Source", track.burden.source));
  const potential = element("div", "", "metric");
  potential.append(element("p", "Potential lives saved / year", "metric-label"),
    element("strong", track.impact ? impactValue(track.impact) : "Unestimated"),
    element("p", track.impact ? `Conditional scenario · ${track.impact.population}` : track.gap, "secondary"));
  track.impact?.sources.forEach((source, index) => potential.append(link(`Source ${index + 1}`, source), " "));
  impact.append(context, potential);

  const queue = element("div", "", "queue");
  queue.append(element("p", track.next, "next"));
  if (issueData) {
    queue.append(element("p", tasks.length ? `${done} reviewed and closed · ${remaining} open · ${underway} underway` :
      "Planning activity in the public queue", "queue-summary"));
    const details = element("details", "");
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
  article.append(top, element("h3", track.name), element("p", track.question), impact, queue);
  return article;
}

function render() {
  const open = new Set([...grid.querySelectorAll("article:has(details[open])")].map(node => node.id));
  const active = document.activeElement;
  // Leave keyboard focus and the expanded links in place until focus leaves the queue.
  if (grid.contains(active) && active.matches("a, summary")) return;
  grid.replaceChildren(...tracks.filter(track => filter === "All" || track.phase === filter).map(track => {
    const node = card(track);
    node.id = track.id;
    if (open.has(track.id)) node.querySelector("details").open = true;
    return node;
  }));
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
  button.addEventListener("click", () => {
    filter = button.dataset.filter;
    for (const choice of filters) choice.setAttribute("aria-pressed", String(choice === button));
    render();
  });
}

try {
  const response = await fetch("/tracks.json");
  if (!response.ok) throw new Error("tracks unavailable");
  tracks = await response.json();
  render();
  await refresh();
  setInterval(refresh, 45_000);
} catch {
  grid.textContent = "Research tracks are temporarily unavailable.";
  feed.textContent = "";
}
