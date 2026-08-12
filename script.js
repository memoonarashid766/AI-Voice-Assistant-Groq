/*
 * script.js
 * ---------
 * All browser-side voice logic: microphone capture + speech-to-text
 * (via the browser's native Web Speech API — no audio is uploaded for
 * transcription), talking to /api/chat and /api/speak, and automatic
 * audio playback with NO visible player/controls.
 *
 * Browser support note: the Web Speech API (SpeechRecognition) is
 * currently supported in Chrome, Edge, and Safari, but not Firefox.
 * Where it's unavailable, Start Listening is disabled and a warning
 * banner appears — typed input still works everywhere.
 */

const state = {
  status: "ready",
  speed: 1.0,
  history: [], // {role, content} pairs resent to /api/chat for context
};

const el = {
  status: document.getElementById("status-value"),
  startBtn: document.getElementById("start-btn"),
  stopBtn: document.getElementById("stop-btn"),
  recognized: document.getElementById("recognized-box"),
  response: document.getElementById("response-box"),
  typedInput: document.getElementById("typed-input"),
  sendBtn: document.getElementById("send-btn"),
  speedSlider: document.getElementById("speed-slider"),
  speedValue: document.getElementById("speed-value"),
  clearBtn: document.getElementById("clear-btn"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  browserWarning: document.getElementById("browser-warning"),
};

const STATUS_LABELS = {
  ready:       ["Ready", "status-ready"],
  listening:   ["Listening...", "status-recognizing"],
  recognizing: ["Recognizing speech...", "status-recognizing"],
  processing:  ["Processing...", "status-processing"],
  speaking:    ["Speaking...", "status-speaking"],
  error:       ["Error", "status-error"],
};

const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let currentAudio = null;

function setStatus(key) {
  state.status = key;
  const [label, cssClass] = STATUS_LABELS[key];
  el.status.textContent = label;
  el.status.className = "status-value " + cssClass;

  // Mic is disabled while busy so the assistant's own voice can never
  // be picked back up as the next input (also covers "Speaking...").
  el.startBtn.disabled = !SpeechRecognitionImpl || ["listening", "recognizing", "processing", "speaking"].includes(key);
  el.stopBtn.disabled = key !== "speaking";
}

function escapeForDisplay(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function setBox(elem, text, isPlaceholder) {
  elem.textContent = text;
  elem.classList.toggle("placeholder-text", !!isPlaceholder);
}

function appendHistory(userText, aiText) {
  el.historyEmpty.style.display = "none";
  const item = document.createElement("div");
  item.className = "history-item";
  const userLabel = document.createElement("div");
  userLabel.className = "history-label";
  userLabel.textContent = "User";
  const userText_ = document.createElement("div");
  userText_.className = "history-text";
  userText_.textContent = userText;
  const aiLabel = document.createElement("div");
  aiLabel.className = "history-label";
  aiLabel.textContent = "Assistant";
  const aiText_ = document.createElement("div");
  aiText_.className = "history-text";
  aiText_.textContent = aiText;
  item.append(userLabel, userText_, aiLabel, aiText_);
  el.historyList.prepend(item); // most recent first, like the original app
}

function describeSpeechError(err) {
  const map = {
    "not-allowed": "Microphone permission was denied. Please allow microphone access and try again.",
    "audio-capture": "No microphone was found. Please check your microphone settings.",
    "no-speech": "I couldn't hear anything. Please try again.",
    "network": "Speech recognition service is unavailable. Please check your internet connection.",
  };
  return map[err] || "I couldn't understand that. Please speak clearly and try again.";
}

// Plays (and immediately pauses) a silent clip during the Start
// Listening / Send click — this is the user gesture Chrome/Safari
// require before a page is allowed to autoplay audio with sound
// later. Doing it here, synchronously inside the click handler,
// "banks" that permission for the real response audio a few seconds
// later once Groq + gTTS have responded.
function unlockAudioPlayback() {
  try {
    const unlock = new Audio();
    unlock.play().catch(() => {});
  } catch (e) {
    /* ignore — best-effort unlock only */
  }
}

// ---------------------------------------------------------------
// Speech recognition (browser mic -> text)
// ---------------------------------------------------------------
if (!SpeechRecognitionImpl) {
  el.browserWarning.style.display = "block";
  el.startBtn.disabled = true;
}

function startListening() {
  if (!SpeechRecognitionImpl || state.status !== "ready") return;

  recognition = new SpeechRecognitionImpl();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = true;

  let finalTranscript = "";

  recognition.onstart = () => {
    finalTranscript = "";
    setBox(el.recognized, "Listening...", true);
    setStatus("listening");
  };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalTranscript += transcript;
      } else {
        interim += transcript;
      }
    }
    setBox(el.recognized, finalTranscript || interim, false);
    if (finalTranscript) setStatus("recognizing");
  };

  recognition.onerror = (event) => {
    if (event.error === "aborted") return; // caused by our own Stop click
    setStatus("error");
    setBox(el.recognized, "Nothing recognized yet.", true);
    setBox(el.response, describeSpeechError(event.error), false);
    setTimeout(() => { if (state.status === "error") setStatus("ready"); }, 3000);
  };

  recognition.onend = () => {
    const text = finalTranscript.trim();
    if (state.status === "error") return;
    if (text) {
      handleUserMessage(text);
    } else {
      setBox(el.recognized, "Nothing recognized yet.", true);
      setStatus("ready");
    }
  };

  recognition.start();
}

el.startBtn.addEventListener("click", () => {
  unlockAudioPlayback();
  startListening();
});

el.stopBtn.addEventListener("click", () => {
  // Stop is only enabled during "Speaking..." — this pauses the
  // browser's own Audio object immediately (a real, instant stop,
  // since playback happens client-side rather than through a
  // server-rendered player).
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  setStatus("ready");
});

// ---------------------------------------------------------------
// Typed input fallback
// ---------------------------------------------------------------
el.sendBtn.addEventListener("click", sendTyped);
el.typedInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendTyped();
});

function sendTyped() {
  if (state.status !== "ready") return;
  const text = el.typedInput.value.trim();
  if (!text) return;
  unlockAudioPlayback();
  el.typedInput.value = "";
  setBox(el.recognized, text, false);
  handleUserMessage(text);
}

// ---------------------------------------------------------------
// Settings
// ---------------------------------------------------------------
el.speedSlider.addEventListener("input", () => {
  state.speed = parseFloat(el.speedSlider.value);
  el.speedValue.textContent = state.speed.toFixed(2);
});

el.clearBtn.addEventListener("click", () => {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  state.history = [];
  el.historyList.innerHTML = "";
  el.historyEmpty.style.display = "block";
  setBox(el.recognized, "Nothing recognized yet.", true);
  setBox(el.response, "No response yet.", true);
  setStatus("ready");
});

// ---------------------------------------------------------------
// Core turn: text -> Groq -> gTTS -> automatic playback
// ---------------------------------------------------------------
async function handleUserMessage(text) {
  setStatus("processing");
  setBox(el.recognized, text, false);

  let data;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: state.history }),
    });
    data = await res.json();
    if (!res.ok) throw new Error(data.error || "Request failed.");
  } catch (err) {
    setStatus("error");
    setBox(el.response, err.message || "Something went wrong. Please try again.", false);
    setTimeout(() => { if (state.status === "error") setStatus("ready"); }, 3000);
    return;
  }

  setBox(el.response, data.reply, false);
  appendHistory(text, data.reply);
  state.history.push({ role: "user", content: text });
  state.history.push({ role: "assistant", content: data.reply });

  if (data.is_exit) {
    setStatus("ready");
    return;
  }

  await speak(data.reply);
}

async function speak(text) {
  setStatus("speaking");
  try {
    const res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, speed: state.speed }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || "Speech generation failed.");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    currentAudio = new Audio(url);

    currentAudio.addEventListener("ended", () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
      if (state.status === "speaking") setStatus("ready");
    });

    try {
      await currentAudio.play();
    } catch (playErr) {
      // Autoplay was blocked by the browser despite the unlock attempt
      // (can still happen in some browsers/settings) — say so plainly
      // rather than silently failing; the text response is still shown.
      currentAudio = null;
      setBox(el.response, describeAutoplayBlocked(text), false);
      setStatus("ready");
    }
  } catch (err) {
    // Text reply already succeeded and is on screen — speech failing
    // isn't fatal, just note it and return to Ready.
    console.error(err);
    setStatus("ready");
  }
}

function describeAutoplayBlocked(text) {
  return text + "\n\n(Your browser blocked automatic audio playback. Click Start Listening once to enable it, then try again.)";
}

setStatus("ready");
