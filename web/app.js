/* Deep Dives frontend: new-episode form + episode progress view (polling). */

const $ = (id) => document.getElementById(id);

/* fetch wrapper: a 401 anywhere pops the password screen */
async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (resp.status === 401) {
    showLogin();
    throw new Error("auth-required");
  }
  return resp;
}

function showLogin() {
  const overlay = $("login-overlay");
  if (!overlay.hidden) return;
  overlay.hidden = false;
  $("login-password").focus();
  $("login-form").onsubmit = async (e) => {
    e.preventDefault();
    const resp = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("login-password").value }),
    });
    if (resp.ok) location.reload();
    else $("login-error").textContent = "Wrong password — try again.";
  };
}
const DOC_TYPES = [
  ["earnings_transcript", "Earnings call transcript"],
  ["initiation_report", "Sell-side initiation report"],
  ["investor_deck", "Investor day / analyst deck"],
  ["expert_call", "Expert-network call transcript"],
  ["newsletter", "Newsletter deep dive"],
  ["book_excerpt", "Book excerpt / notes"],
  ["thesis_notes", "My own thesis / notes"],
  ["user_upload", "Other"],
];

const params = new URLSearchParams(location.search);
const episodeId = params.get("ep");
if (episodeId) {
  $("view-episode").hidden = false;
  pollEpisode();
} else {
  $("view-new").hidden = false;
  initForm();
  loadRecent();
}

/* ---------------------------------------------------------- new episode */

let pickedFiles = [];

function initForm() {
  $("file-input").addEventListener("change", (e) => {
    for (const f of e.target.files) {
      pickedFiles.push({ file: f, doc_type: "earnings_transcript", period: "" });
    }
    renderFileList();
    e.target.value = "";
  });

  $("create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("create-btn");
    btn.disabled = true;
    btn.textContent = "Starting research…";
    const form = e.target;
    const data = new FormData();
    data.append("company", form.company.value);
    data.append("runtime", form.runtime.value);
    data.append("preferences", form.preferences.value);
    data.append("doc_types", JSON.stringify(
      pickedFiles.map((p) => ({ file: p.file.name, doc_type: p.doc_type, period: p.period }))
    ));
    for (const p of pickedFiles) data.append("files", p.file);
    try {
      const resp = await api("/api/episodes", { method: "POST", body: data });
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);
      const { id } = await resp.json();
      location.href = `/?ep=${encodeURIComponent(id)}`;
    } catch (err) {
      if (err.message !== "auth-required") alert(`Could not start: ${err.message}`);
      btn.disabled = false;
      btn.textContent = "Research this company";
    }
  });
}

function renderFileList() {
  const box = $("file-list");
  box.innerHTML = "";
  pickedFiles.forEach((p, i) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const select = document.createElement("select");
    for (const [value, label] of DOC_TYPES) {
      const opt = new Option(label, value, false, value === p.doc_type);
      select.add(opt);
    }
    select.onchange = () => (p.doc_type = select.value);
    const period = document.createElement("input");
    period.placeholder = "Period (e.g. Q3 2008)";
    period.value = p.period;
    period.oninput = () => (p.period = period.value);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "✕";
    remove.className = "remove";
    remove.onclick = () => { pickedFiles.splice(i, 1); renderFileList(); };
    const name = document.createElement("span");
    name.className = "filename";
    name.textContent = p.file.name;
    row.append(name, select, period, remove);
    box.append(row);
  });
}

async function loadRecent() {
  try {
    const episodes = await (await api("/api/episodes")).json();
    if (!episodes.length) return;
    $("recent").hidden = false;
    $("recent-list").innerHTML = episodes.slice(0, 12).map((e) =>
      `<li><a href="/?ep=${encodeURIComponent(e.id)}">${esc(e.episode_title || e.company)}</a>
       <span class="pill ${e.status}">${esc(e.status)}</span></li>`).join("");
  } catch { /* no episodes yet */ }
}

/* ---------------------------------------------------------- episode view */

const STAGE_LABELS = {
  queued: "Queued", researching: "Researching", fetching: "Gathering sources",
  drafting_outline: "Structuring the episode", awaiting_approval: "Awaiting your approval",
  writing: "Writing", voicing: "Recording", stitching: "Finishing", done: "Ready",
  error: "Failed",
};
let approving = false;

async function pollEpisode() {
  let state;
  try {
    const resp = await api(`/api/episodes/${encodeURIComponent(episodeId)}`);
    if (!resp.ok) { $("status-message").textContent = "Episode not found."; return; }
    state = await resp.json();
  } catch (err) {
    if (err.message === "auth-required") return; // login screen showing; reload resumes
    setTimeout(pollEpisode, 4000);
    return;
  }

  render(state);
  if (!["done", "error"].includes(state.status)) setTimeout(pollEpisode, 2500);
}

function render(s) {
  $("ep-title").textContent = s.episode_title || s.company;
  $("ep-logline").textContent = s.logline || "";
  document.title = `${s.episode_title || s.company} — Deep Dives`;

  $("status-message").textContent = STAGE_LABELS[s.status] || s.status;
  $("status-detail").textContent = s.status === "error" ? (s.error || "") : (s.message || "");
  $("spinner").hidden = ["done", "error", "awaiting_approval"].includes(s.status);
  $("status-bar").classList.toggle("error", s.status === "error");
  $("status-bar").classList.toggle("ok", s.status === "done");

  // checkpoint
  const checkpoint = $("checkpoint");
  if (s.status === "awaiting_approval" && !approving) {
    if (checkpoint.hidden) renderCheckpoint(s);
    checkpoint.hidden = false;
  } else {
    checkpoint.hidden = true;
  }

  // chapters progress
  const started = ["writing", "voicing", "stitching", "done"].includes(s.status);
  $("chapters-section").hidden = !started || !(s.chapters || []).length;
  if (started) renderChapters(s.chapters || []);

  // final audio
  $("final").hidden = s.status !== "done";
  if (s.status === "done" && s.final_audio && !$("final-audio").src) {
    $("final-audio").src = s.final_audio;
    $("download-link").href = s.final_audio;
    $("script-link").href = `/api/episodes/${encodeURIComponent(s.id)}/script`;
  }

  // sources panel
  const sources = s.sources || [];
  $("sources-section").hidden = !sources.length;
  $("sources").innerHTML = sources.map((src) => {
    const title = esc(src.title);
    const label = src.url && src.url !== "-"
      ? `<a href="${escAttr(src.url)}" target="_blank" rel="noopener">${title}</a>` : title;
    return `<li><span class="pill">${esc((src.type || "").replaceAll("_", " "))}</span> ${label}</li>`;
  }).join("");
}

function renderCheckpoint(s) {
  $("checkpoint-chapters").innerHTML = (s.chapters || []).map((ch) => `
    <div class="chapter-brief">
      <div><strong>${ch.id}. ${esc(ch.title)}</strong>
        <div class="muted small">${esc(ch.teaser || "")}</div></div>
      <input data-note="${ch.id}" placeholder="Optional note — e.g. go deeper here">
    </div>`).join("");

  $("approve-btn").onclick = async () => {
    approving = true;
    $("approve-btn").disabled = true;
    $("approve-btn").textContent = "Starting generation…";
    const notes = {};
    document.querySelectorAll("[data-note]").forEach((el) => {
      if (el.value.trim()) notes[el.dataset.note] = el.value.trim();
    });
    await api(`/api/episodes/${encodeURIComponent(episodeId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, global_note: $("global-note").value.trim() }),
    });
    approving = false;
    $("checkpoint").hidden = true;
  };
}

const CH_STATUS = { pending: "…", writing: "writing", auditing: "fact-checking",
                    voicing: "recording", done: "" };

function renderChapters(chapters) {
  const box = $("chapters");
  for (const ch of chapters) {
    let el = box.querySelector(`[data-ch="${ch.id}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = "card chapter";
      el.dataset.ch = ch.id;
      box.append(el);
    }
    const audio = el.querySelector("audio");
    if (ch.status === "done" && ch.audio && !audio) {
      el.innerHTML = `<div class="ch-head"><strong>${ch.id}. ${esc(ch.title)}</strong></div>
        <div class="muted small">${esc(ch.teaser || "")}</div>
        <audio controls preload="none" src="${escAttr(ch.audio)}"></audio>`;
    } else if (!audio) {
      el.innerHTML = `<div class="ch-head"><strong>${ch.id}. ${esc(ch.title)}</strong>
        <span class="pill ${esc(ch.status)}">${esc(CH_STATUS[ch.status] ?? ch.status)}</span></div>
        <div class="muted small">${esc(ch.teaser || "")}</div>`;
    }
  }
}

/* ---------------------------------------------------------- utils */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escAttr(s) { return esc(s); }
