import { PipecatClient } from "https://esm.sh/@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "https://esm.sh/@pipecat-ai/small-webrtc-transport";

const orb = document.getElementById("orb");
const callBtn = document.getElementById("call-btn");
const statusLine = document.getElementById("status-line");
const muteBtn = document.getElementById("mute-btn");
const muteLabel = document.getElementById("mute-label");
const emptyState = document.getElementById("empty-state");
const transcriptEl = document.getElementById("transcript");
const settingsBtn = document.getElementById("settings-btn");
const drawer = document.getElementById("settings-drawer");
const drawerBackdrop = document.getElementById("drawer-backdrop");
const drawerClose = document.getElementById("drawer-close");
const historyList = document.getElementById("history-list");
const traceList = document.getElementById("trace-list");

let client = null;
let connected = false;
let muted = false;
let busy = false;
const botAudioElements = [];

function setStatus(text, kind = "muted") {
  statusLine.textContent = text;
  statusLine.classList.remove("muted", "connected", "error");
  statusLine.classList.add(kind);
}

function setConnectedUI(isConnected) {
  connected = isConnected;
  orb.classList.toggle("connected", isConnected);
  callBtn.classList.toggle("connected", isConnected);
  const label = isConnected ? "Disconnect" : "Connect";
  callBtn.title = label;
  callBtn.setAttribute("aria-label", label);
}

function showTranscript() {
  emptyState.hidden = true;
  transcriptEl.hidden = false;
}

function resetSession() {
  seenTurns.clear();
  transcriptEl.innerHTML = "";
  historyList.innerHTML = "";
  traceList.innerHTML = "";
  transcriptEl.hidden = true;
  emptyState.hidden = false;
  muted = false;
  muteBtn.classList.remove("muted-active");
  muteBtn.setAttribute("aria-label", "Mute");
  muteLabel.textContent = "Mute";
}

const seenTurns = new Set();

function addTurn(role, text) {
  if (!text) return;
  // Bot output re-emits each sentence across new/in-progress/completed "spoken"
  // phases, interleaved with other sentences — dedupe by exact (role, text), not
  // just consecutive repeats.
  const key = `${role}:${text}`;
  if (seenTurns.has(key)) return;
  seenTurns.add(key);
  showTranscript();
  const bubble = document.createElement("div");
  bubble.className = `turn ${role}`;
  bubble.textContent = text;
  transcriptEl.appendChild(bubble);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;

  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `<div class="log-meta">${role} &middot; ${new Date().toLocaleTimeString()}</div>${escapeHtml(text)}`;
  historyList.appendChild(entry);
}

function addTrace(kind, data) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const label = {
    started: "Function call started",
    in_progress: "Function call arguments",
    stopped: "Function call result",
  }[kind];
  entry.innerHTML = `<div class="log-meta">${label} &middot; ${new Date().toLocaleTimeString()}</div><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  traceList.appendChild(entry);
  traceList.scrollTop = traceList.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function connect() {
  resetSession();
  setStatus("Connecting…");
  muteBtn.disabled = true;
  client = new PipecatClient({
    transport: new SmallWebRTCTransport({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    }),
    enableMic: true,
    callbacks: {
      onBotReady: () => {
        setConnectedUI(true);
        setStatus("Connected", "connected");
        muteBtn.disabled = false;
      },
      onDisconnected: () => {
        setConnectedUI(false);
        setStatus("Not connected");
        muteBtn.disabled = true;
        resetSession();
      },
      onTransportStateChanged: (state) => {
        if (state === "connected") return; // onBotReady sets the "Connected" label
        setStatus(state);
      },
      onUserTranscript: (data) => {
        if (data && data.final) addTurn("user", data.text);
      },
      onBotOutput: (data) => {
        const text = (data && (data.text ?? data.aggregated_text)) || "";
        if (text) addTurn("assistant", text);
      },
      onLLMFunctionCallStarted: (data) => addTrace("started", data),
      onLLMFunctionCallInProgress: (data) => addTrace("in_progress", data),
      onLLMFunctionCallStopped: (data) => addTrace("stopped", data),
      onTrackStarted: (track, participant) => {
        if (track.kind !== "audio") return;
        const audioEl = document.createElement("audio");
        audioEl.dataset.participant = participant?.id ?? "unknown";
        audioEl.srcObject = new MediaStream([track]);
        document.body.appendChild(audioEl);
        audioEl.play().catch((err) => console.error("Audio playback blocked", err));
        botAudioElements.push(audioEl);
      },
      onError: (err) => {
        console.error("Pipecat client error", err);
        setStatus("Error — see console", "error");
      },
    },
  });

  const botBaseUrl = window.__BOT_BASE_URL__;
  try {
    await client.connect({ webrtcRequestParams: { endpoint: `${botBaseUrl}/api/offer` } });
  } catch (err) {
    console.error(err);
    setStatus("Failed to connect — see console", "error");
    setConnectedUI(false);
    muteBtn.disabled = true;
  }
}

async function disconnect() {
  if (client) {
    await client.disconnect();
    client = null;
  }
  for (const el of botAudioElements.splice(0)) {
    el.pause();
    el.remove();
  }
  // onDisconnected (fired by client.disconnect() above, or by the bot
  // hanging up server-side) handles setConnectedUI/setStatus/resetSession.
}

callBtn.addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  callBtn.disabled = true;
  try {
    if (connected) {
      await disconnect();
    } else {
      await connect();
    }
  } finally {
    busy = false;
    callBtn.disabled = false;
  }
});

muteBtn.addEventListener("click", () => {
  if (!client) return;
  muted = !muted;
  client.enableMic(!muted);
  const label = muted ? "Unmute" : "Mute";
  muteBtn.classList.toggle("muted-active", muted);
  muteBtn.setAttribute("aria-label", label);
  muteLabel.textContent = label;
});

function openDrawer() {
  drawer.hidden = false;
  drawerBackdrop.hidden = false;
}

function closeDrawer() {
  drawer.hidden = true;
  drawerBackdrop.hidden = true;
}

settingsBtn.addEventListener("click", openDrawer);
drawerClose.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !drawer.hidden) closeDrawer();
});

for (const tab of document.querySelectorAll(".drawer-tab")) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll(".drawer-tab")) t.classList.remove("active");
    tab.classList.add("active");
    document.getElementById("tab-history").hidden = tab.dataset.tab !== "history";
    document.getElementById("tab-trace").hidden = tab.dataset.tab !== "trace";
  });
}

// Typed messages are disabled (see call.html) — the bot's pipeline has no
// text-input frame handler yet (audio only).
