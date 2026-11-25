const prompt = document.querySelector("#join-prompt");
const copyButton = document.querySelector("#copy-prompt");
const copyStatus = document.querySelector("#copy-status");
let copyTimer;

copyButton.hidden = false;
copyButton.addEventListener("click", async () => {
  clearTimeout(copyTimer);
  try {
    await navigator.clipboard.writeText(prompt.textContent.trim());
    copyButton.textContent = "Copied";
    copyStatus.textContent = "Paste it into your assistant.";
    copyTimer = setTimeout(() => {
      copyButton.textContent = "Copy prompt";
      copyStatus.textContent = "";
    }, 3500);
  } catch {
    copyStatus.textContent = "Copy the selected text.";
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(prompt);
    selection.removeAllRanges();
    selection.addRange(range);
  }
});

const feed = document.querySelector("#feed");
const format = new Intl.NumberFormat();
let lastSummary;

async function updateQueue() {
  try {
    const response = await fetch("/api/progress");
    if (!response.ok) throw new Error("queue unavailable");
    const {network} = await response.json();
    const {ready, working, done} = network;
    lastSummary = `Live queue · ${format.format(ready)} ready · ${format.format(working)} in progress or review · ${format.format(done)} completed`;
    if (feed.textContent !== lastSummary) feed.textContent = lastSummary;
  } catch {
    feed.textContent = lastSummary ? lastSummary.replace("Live queue", "Last update") : "Live queue unavailable.";
  }
}

updateQueue();
setInterval(updateQueue, 45_000);
