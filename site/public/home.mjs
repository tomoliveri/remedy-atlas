import {roadmapStatus} from "./roadmap.mjs";

const milestones = [
  ["One person gets a better answer.", "Crowdsource a question with a real person at the other end. Who is falling through a gap in care, and what would help them?"],
  ["A small team tests the idea.", "Check what is already known and find a care team that can test the next step. Even a small change can matter to a family."],
  ["One community finds what works.", "Follow an improvement in a defined community. Count who got care, who was missed, and what changed for patients."],
  ["Other communities can build on it.", "Share the evidence and what it took to put it into practice. A different team needs enough detail to see whether it works where they are."],
  ["Better care reaches more people.", "Grow the approaches that hold up across settings. Keep access, cost and quality in view as more people get care."],
  ["More diseases get a path forward.", "Use what we learn from infections, snakebite and cervical cancer to open new questions in prevention, diagnosis and treatment."],
  ["Help more people survive cancer.", "Build separate programs for different cancers. Work with clinical partners on better prevention and treatment, including cures where the evidence supports them."],
  ["Help save millions across diseases.", "The long-term hope is for many cancers to be preventable or curable, and for proven care to reach millions of people who would otherwise miss out."],
];

const slider = document.querySelector("#scale");
const scalePanel = document.querySelector(".scale-panel");
const ticks = [...document.querySelectorAll("[data-step]")];

function setStep(step) {
  const [heading, copy] = milestones[step];
  const number = new Intl.NumberFormat().format(10 ** step);
  const unit = step === 0 ? "life" : "lives";
  slider.value = step;
  slider.setAttribute("aria-valuetext", `${number} ${unit}`);
  scalePanel.style.setProperty("--step", step);
  document.querySelector("#scale-number").textContent = number;
  document.querySelector("#scale-unit").textContent = unit;
  document.querySelector("#scale-heading").textContent = heading;
  document.querySelector("#scale-copy").textContent = copy;
  for (const tick of ticks) tick.setAttribute("aria-pressed", String(Number(tick.dataset.step) === step));
}

slider.addEventListener("input", () => setStep(Number(slider.value)));
for (const tick of ticks) tick.addEventListener("click", () => setStep(Number(tick.dataset.step)));

const feed = document.querySelector("#feed");
const focusList = document.querySelector("#focus-list");
const count = new Intl.NumberFormat();
let updatedAt;
const otherTracks = new Map();
const trackCatalog = fetch("/tracks.json").then(response => response.ok ? response.json() : []).catch(() => []);

function showStatus(node, phase, data) {
  const status = roadmapStatus(phase, data);
  node.textContent = status.complete ? `✓ ${status.label}` : status.label;
}

function updateFocus(tracks, catalog) {
  for (const label of document.querySelectorAll("[data-focus]")) {
    const ids = label.dataset.focus.split(",");
    const jobs = ids.flatMap(id => tracks[id]?.jobs ?? []);
    const tasks = ids.flatMap(id => tracks[id]?.tasks ?? []);
    showStatus(label, "Research track", {jobs, tasks});
  }

  for (const track of catalog) {
    if (["ndm", "kpc-oxa", "snakebite", "cervical"].includes(track.id) || !tracks[track.id]?.jobs?.length) continue;
    let status = otherTracks.get(track.id);
    if (!status) {
      const row = document.createElement("li");
      const link = document.createElement("a");
      link.href = `/research.html#${track.id}`;
      link.textContent = track.name;
      status = document.createElement("span");
      row.append(link, status);
      focusList.append(row);
      otherTracks.set(track.id, status);
    }
    showStatus(status, track.phase === "On hold" ? track.phase : "Research track", tracks[track.id]);
  }
}

async function updateNetwork() {
  try {
    const response = await fetch("/api/progress");
    if (!response.ok) throw new Error("queue unavailable");
    const {network, tracks, updatedAt: stamp} = await response.json();
    if (!network) throw new Error("network summary unavailable");
    for (const [key, value] of Object.entries(network)) {
      const metric = document.getElementById(`${key}-count`);
      if (metric) metric.textContent = count.format(value);
    }
    updatedAt = new Date(stamp);
    feed.textContent = `Live queue · checked ${updatedAt.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}`;
    updateFocus(tracks, await trackCatalog);
  } catch {
    feed.textContent = updatedAt ? "Showing the last update. We’ll try again shortly." : "The live queue is temporarily unavailable.";
  }
}

await updateNetwork();
setInterval(updateNetwork, 45_000);
