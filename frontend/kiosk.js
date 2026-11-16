/**
 * HID Smart Entry Kiosk Client Application
 * Handles webcam streaming, passive liveness evaluation, campus schedule authorization,
 * offline mode simulation, step-up verification, and spoof attack lab injection.
 */

const API_BASE = "http://localhost:8000";

// DOM Elements
const $ = (id) => document.getElementById(id);
const webcam = $("webcam");
const canvas = $("snapshotCanvas");
const hudReticle = $("hudReticle");
const latencyTimer = $("latencyTimer");
const slaBadge = $("slaComplianceBadge");

const btnStart = $("btnStartCamera");
const btnStop = $("btnStopCamera");
const btnEvaluate = $("btnEvaluateAccess");

const verdictBanner = $("verdictBanner");
const verdictTitle = $("verdictTitle");
const verdictReason = $("verdictReason");

const livenessStatusVal = $("livenessStatusVal");
const livenessScoreTag = $("livenessScoreTag");
const spoofTypeVal = $("spoofTypeVal");
const spoofTypeTag = $("spoofTypeTag");
const identityNameVal = $("identityNameVal");
const identityDistTag = $("identityDistTag");
const scheduleStatusVal = $("scheduleStatusVal");
const scheduleZoneTag = $("scheduleZoneTag");
const offlineBacklogVal = $("offlineBacklogVal");

const selectZone = $("selectZone");
const selectRole = $("selectRole");
const simulatedTimeInput = $("simulatedTimeInput");
const toggleOfflineMode = $("toggleOfflineMode");
const networkModeLabel = $("networkModeLabel");
const offlineStatePill = $("offlineStatePill");

const stepUpModal = $("stepUpModal");
const modalReasonText = $("modalReasonText");
const otpCodeInput = $("otpCodeInput");
const demoOtpCode = $("demoOtpCode");
const btnSubmitOtp = $("btnSubmitOtp");
const btnCancelModal = $("btnCancelModal");

let stream = null;
let lastMatchedUser = "Authorized Person";

// ── Check API Health on Startup ──
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      $("apiStatusText").textContent = `API: Online (${data.users} enrolled)`;
      $("apiStatePill").classList.add("online");
    } else {
      $("apiStatusText").textContent = "API: Degraded";
    }
  } catch (err) {
    $("apiStatusText").textContent = "API: Disconnected";
    $("apiStatePill").classList.remove("online");
  }
}
checkHealth();
setInterval(checkHealth, 8000);

// ── Sync Status Polling ──
async function updateSyncStatus() {
  try {
    const res = await fetch(`${API_BASE}/sync/status`);
    if (res.ok) {
      const data = await res.json();
      offlineBacklogVal.textContent = `${data.local_pending_sync_count} pending / ${data.central_reconciled_count} synced`;
    }
  } catch (e) {
    // Kiosk air-gapped simulation
  }
}
updateSyncStatus();

// ── Campus Schedule Real-Time Policy Inspector ──
let cachedPolicies = {};
async function loadCampusPolicies() {
  try {
    const res = await fetch(`${API_BASE}/schedule/policies`);
    if (res.ok) {
      const data = await res.json();
      cachedPolicies = data.zones || {};
      previewScheduleClearance();
    }
  } catch (e) {
    console.warn("Failed to load schedule policies:", e);
  }
}

function previewScheduleClearance() {
  const currentZone = selectZone.value;
  const currentRole = selectRole.value;
  const policy = cachedPolicies[currentZone];

  if (!policy) return;

  const isRoleAllowed = currentRole === "security" || policy.allowed_roles.includes(currentRole);
  if (!isRoleAllowed) {
    scheduleStatusVal.textContent = `ROLE '${currentRole.toUpperCase()}' RESTRICTED`;
    scheduleStatusVal.style.color = "var(--verdict-deny)";
  } else {
    scheduleStatusVal.textContent = `CLEARANCE ACTIVE (${policy.name.split(" ")[0]})`;
    scheduleStatusVal.style.color = "var(--verdict-allow)";
  }
}

selectZone.addEventListener("change", previewScheduleClearance);
selectRole.addEventListener("change", previewScheduleClearance);
simulatedTimeInput.addEventListener("input", previewScheduleClearance);
loadCampusPolicies();

// ── Camera Control ──
btnStart.onclick = async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    webcam.srcObject = stream;
    await webcam.play();

    btnStart.disabled = true;
    btnStop.disabled = false;
    btnEvaluate.disabled = false;
    setReticleState("");
    verdictTitle.textContent = "SCANNING";
    verdictReason.textContent = "Camera active. Ready for sub-2s physical presence inspection.";
  } catch (err) {
    alert("Camera access failed: " + err.message);
  }
};

btnStop.onclick = () => {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  webcam.srcObject = null;
  btnStart.disabled = false;
  btnStop.disabled = true;
  btnEvaluate.disabled = true;
  setReticleState("");
  verdictTitle.textContent = "READY";
  verdictReason.textContent = "Camera stopped.";
};

// ── Reticle & Verdict State Helpers ──
function setReticleState(state) {
  hudReticle.className = "hud-reticle " + state;
}

function updateVerdict(decision, reason, latencyMs) {
  verdictBanner.className = "verdict-banner " + decision.toLowerCase().replace(/[\s_]+/g, "");
  verdictTitle.textContent = decision;
  verdictReason.textContent = reason;

  latencyTimer.textContent = `${latencyMs.toFixed(1)} ms`;
  if (latencyMs <= 2000) {
    slaBadge.className = "sla-badge";
    slaBadge.textContent = "SLA \u2264 2.0s \u2713";
  } else {
    slaBadge.className = "sla-badge";
    slaBadge.style.color = "var(--verdict-deny)";
    slaBadge.textContent = "SLA BREACH";
  }

  if (decision === "ALLOW") {
    setReticleState("allow");
  } else if (decision === "REQUEST VERIFICATION" || decision === "STEP-UP VERIFICATION") {
    setReticleState("verify");
  } else {
    setReticleState("deny");
  }
}

// ── Capture Frame as JPEG Blob ──
async function captureFrameBlob() {
  if (!webcam.videoWidth) {
    throw new Error("Webcam video stream not ready");
  }
  canvas.width = webcam.videoWidth;
  canvas.height = webcam.videoHeight;
  const ctx = canvas.getContext("2d");
  // Un-mirror horizontally for accurate matching
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(webcam, 0, 0, canvas.width, canvas.height);

  return new Promise((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", 0.9);
  });
}

// ── Core Access Evaluation ──
btnEvaluate.onclick = async () => {
  btnEvaluate.disabled = true;
  const t0 = performance.now();
  latencyTimer.textContent = "Evaluating...";

  try {
    const blob = await captureFrameBlob();
    await sendEvaluationRequest(blob, t0);
  } catch (err) {
    updateVerdict("DENY", "Capture failed: " + err.message, performance.now() - t0);
  } finally {
    btnEvaluate.disabled = false;
  }
};

async function sendEvaluationRequest(blob, t0) {
  const formData = new FormData();
  formData.append("image", blob, "kiosk-capture.jpg");
  formData.append("role", selectRole.value);
  formData.append("zone", selectZone.value);
  formData.append("offline", toggleOfflineMode.value);
  if (simulatedTimeInput.value.trim()) {
    formData.append("simulated_time", simulatedTimeInput.value.trim());
  }

  const res = await fetch(`${API_BASE}/access/evaluate`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json();
  const elapsed = performance.now() - t0;

  if (!res.ok) {
    throw new Error(data.detail || "Authentication evaluation failed");
  }

  // Update telemetry display
  const bio = data.biometric || {};
  const live = bio.liveness || {};
  const ident = bio.identity || {};
  const sched = data.schedule || {};

  livenessStatusVal.textContent = live.is_live ? "Live Human Confirmed" : (live.is_borderline ? "Borderline Confidence" : "Attack Detected");
  livenessScoreTag.textContent = live.liveness_score ? `Score: ${live.liveness_score.toFixed(2)}` : "—";
  livenessScoreTag.style.color = live.is_live ? "var(--verdict-allow)" : "var(--verdict-deny)";

  spoofTypeVal.textContent = live.spoof_type ? live.spoof_type.replace(/_/g, " ").toUpperCase() : "None";
  spoofTypeTag.textContent = live.spoof_type === "genuine" ? "CLEAN" : "FLAGGED";
  spoofTypeTag.style.color = live.spoof_type === "genuine" ? "var(--verdict-allow)" : "var(--verdict-deny)";

  identityNameVal.textContent = ident.name || "Unknown";
  lastMatchedUser = ident.name || "Authorized Person";
  identityDistTag.textContent = ident.distance !== undefined ? `Dist: ${ident.distance.toFixed(3)}` : "—";

  scheduleStatusVal.textContent = sched.schedule_status ? sched.schedule_status.replace(/_/g, " ").toUpperCase() : "OK";
  scheduleZoneTag.textContent = selectZone.options[selectZone.selectedIndex].text.split(" ")[0];

  updateVerdict(data.final_decision, data.reason, data.total_latency_ms || elapsed);

  // If step-up verification is required, automatically display modal
  if (data.step_up_required) {
    modalReasonText.textContent = data.reason;
    stepUpModal.classList.add("active");
  }

  updateSyncStatus();
}

// ── Interactive Offline Mode Toggle ──
let previousOfflineState = false;
toggleOfflineMode.onchange = async () => {
  const isOffline = toggleOfflineMode.value === "true";
  if (isOffline) {
    networkModeLabel.textContent = "Offline · Safe Fail-Secure";
    offlineStatePill.className = "status-pill offline";
    verdictReason.textContent = "Offline air-gap mode active. Local fail-secure policies and audit chain enforced.";
  } else {
    networkModeLabel.textContent = "Online · Cloud Central";
    offlineStatePill.className = "status-pill online";
    // If returning from offline mode, offer auto-reconciliation
    if (previousOfflineState) {
      const syncConfirm = confirm("Network connection restored! Synchronize queued offline access decisions with central server now?");
      if (syncConfirm) {
        $("btnSyncNow").click();
      }
    }
  }
  previousOfflineState = isOffline;
};

// ── TOTP 30-Second Refresh Countdown Timer ──
let totpInterval = null;
function startTotpCountdown() {
  if (totpInterval) clearInterval(totpInterval);
  const updateCountdown = () => {
    const epochSec = Math.floor(Date.now() / 1000);
    const rem = 30 - (epochSec % 30);
    const demoBtn = $("demoOtpCode");
    if (demoBtn && demoBtn.textContent !== "Click to load") {
      demoBtn.title = `Passcode refreshes in ${rem}s`;
    }
  };
  updateCountdown();
  totpInterval = setInterval(updateCountdown, 1000);
}
startTotpCountdown();

// ── Interactive Reconnection Sync ──
$("btnSyncNow").onclick = async () => {
  try {
    const res = await fetch(`${API_BASE}/sync/trigger-local`, { method: "POST" });
    const data = await res.json();
    alert(data.message || `Synchronized ${data.synced_count} events.`);
    updateSyncStatus();
  } catch (e) {
    alert("Reconnection sync failed: " + e.message);
  }
};

// ── Step-Up Modal Handlers ──
btnCancelModal.onclick = () => {
  stepUpModal.classList.remove("active");
};

demoOtpCode.onclick = async () => {
  try {
    const res = await fetch(`${API_BASE}/access/step-up/current-otp`);
    const data = await res.json();
    otpCodeInput.value = data.current_token;
    demoOtpCode.textContent = data.current_token;
  } catch (e) {
    otpCodeInput.value = "994821";
  }
};

btnSubmitOtp.onclick = async () => {
  const code = otpCodeInput.value.trim();
  if (!code) {
    alert("Please enter a verification code.");
    return;
  }

  const formData = new FormData();
  formData.append("verification_type", "otp");
  formData.append("code", code);
  formData.append("user_name", lastMatchedUser);
  formData.append("zone", selectZone.value);
  formData.append("offline", toggleOfflineMode.value);

  try {
    const res = await fetch(`${API_BASE}/access/step-up/verify`, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    stepUpModal.classList.remove("active");
    updateVerdict(data.final_decision, data.reason, data.latency_ms || 15.0);
    updateSyncStatus();
  } catch (e) {
    alert("Verification failed: " + e.message);
  }
};

// ── Interactive Spoof Attack Testing Lab ──
// Generates synthetic presentation attack payloads so reviewers can test all 4 spoofs with 1 click!

function generateSyntheticAttackBlob(type) {
  const offCanvas = document.createElement("canvas");
  offCanvas.width = 120;
  offCanvas.height = 120;
  const ctx = offCanvas.getContext("2d");

  // Face base tone
  ctx.fillStyle = type === "mask" ? "#9a9a9a" : "#c49a75";
  ctx.fillRect(0, 0, 120, 120);

  // Facial features
  ctx.fillStyle = "#333333";
  ctx.beginPath();
  ctx.ellipse(36, 45, 8, 5, 0, 0, Math.PI * 2);
  ctx.ellipse(84, 45, 8, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#8a3a3a";
  ctx.fillRect(45, 80, 30, 8);

  if (type === "photo") {
    // White paper border
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 14;
    ctx.strokeRect(0, 0, 120, 120);
  } else if (type === "screen") {
    // Glass specular reflection highlight
    ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
    ctx.fillRect(35, 30, 45, 35);
    // Blue tint
    ctx.fillStyle = "rgba(0, 100, 255, 0.25)";
    ctx.fillRect(0, 0, 120, 120);
  } else if (type === "video") {
    // Moire interference lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.6)";
    ctx.lineWidth = 1;
    for (let i = 0; i < 120; i += 3) {
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(120, i);
      ctx.stroke();
    }
  } else if (type === "mask") {
    // Sharp rim cutout lines around eyes and mouth
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 4;
    ctx.strokeRect(26, 38, 20, 14);
    ctx.strokeRect(74, 38, 20, 14);
    ctx.strokeRect(40, 75, 40, 18);
  }

  return new Promise((resolve) => offCanvas.toBlob(resolve, "image/jpeg", 0.9));
}

async function injectAttack(type) {
  const t0 = performance.now();
  latencyTimer.textContent = "Analyzing Attack Presentation...";

  // Visual feedback on HUD
  const attackTitles = {
    photo: "ATTACK PRESENTATION: PRINTED PHOTO",
    screen: "ATTACK PRESENTATION: SCREEN REPLAY",
    video: "ATTACK PRESENTATION: VIDEO REPLAY (MOIRE)",
    mask: "ATTACK PRESENTATION: 3D / PRINTED MASK",
    genuine: "PRESENTATION: GENUINE LIVE SUBJECT",
  };
  verdictTitle.textContent = "INSPECTING";
  verdictReason.textContent = attackTitles[type] || "Evaluating physical presentation attack...";

  const blob = await generateSyntheticAttackBlob(type);

  // Render to canvas so user sees the attack in the UI
  const imgUrl = URL.createObjectURL(blob);
  const tempImg = new Image();
  tempImg.onload = () => {
    canvas.hidden = false;
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(tempImg, 0, 0, 640, 480);
    // Add watermark
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
    ctx.fillRect(0, 430, 640, 50);
    ctx.fillStyle = type === "genuine" ? "#10b981" : "#ef4444";
    ctx.font = "bold 16px Inter, sans-serif";
    ctx.fillText(attackTitles[type] || "ATTACK", 20, 460);
    URL.revokeObjectURL(imgUrl);
  };
  tempImg.src = imgUrl;

  await sendEvaluationRequest(blob, t0);
}

$("btnAttackPhoto").onclick = () => injectAttack("photo");
$("btnAttackScreen").onclick = () => injectAttack("screen");
$("btnAttackVideo").onclick = () => injectAttack("video");
$("btnAttackMask").onclick = () => injectAttack("mask");
$("btnInjectGenuine").onclick = () => injectAttack("genuine");

// ── Automated Benchmark Trigger ──
$("btnRunBenchmark").onclick = async () => {
  const btn = $("btnRunBenchmark");
  btn.disabled = true;
  btn.textContent = "Running benchmark...";
  try {
    const res = await fetch(`${API_BASE}/benchmark/run`);
    const data = await res.json();
    alert(
      `HID Hackathon Automated Benchmark Report:\n\n` +
      `• Total Presentations: ${data.total_presentations}\n` +
      `• Overall Accuracy: ${data.accuracy_percent}%\n` +
      `• APCER (Attack Error): ${data.apcer_percent}%\n` +
      `• BPCER (Bona Fide Error): ${data.bpcer_percent}%\n\n` +
      `• Mean Latency: ${data.latency_metrics_ms.mean} ms (p95: ${data.latency_metrics_ms.p95} ms)\n` +
      `• SLA Status: ${data.latency_metrics_ms.all_within_2s_sla ? "PASSED (\u2264 2.0s)" : "FAILED"}`
    );
  } catch (e) {
    alert("Benchmark execution failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> Run Benchmark`;
  }
};
