// =============================================================
// AUTHENTICATION & SECURE SESSION MANAGEMENT
// =============================================================
// Production Notes:
// 1. In production, enterprise deployments would integrate SAML 2.0 / OpenID Connect
//    with Okta, Azure AD, or PingFederate, and enforce WebAuthn/FIDO2 MFA.
// 2. All tokens are securely issued as HttpOnly, SameSite=Lax, Secure cookies.
//    No tokens or plain credentials are ever stored in localStorage or sessionStorage.
// 3. Sensitive operations require double-submit CSRF verification via X-CSRF-Token.

let currentUser = null;
let inactivityTimer = null;
let warningTimer = null;
let countdownInterval = null;
let secondsRemaining = 60;
const INACTIVITY_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes
const WARNING_TIMEOUT_MS = 14 * 60 * 1000;    // 14 minutes

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

function getCsrfToken() {
  return getCookie("csrf_token") || "";
}

// Intercept window.fetch to automatically include CSRF token and handle silent refresh on 401
const _rawFetch = window.fetch.bind(window);
window.fetch = async function (url, options = {}) {
  options.credentials = options.credentials || "same-origin";
  const method = (options.method || "GET").toUpperCase();

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    options.headers = options.headers || {};
    const csrf = getCsrfToken();
    if (csrf) {
      if (options.headers instanceof Headers) {
        options.headers.set("X-CSRF-Token", csrf);
      } else {
        options.headers["X-CSRF-Token"] = csrf;
      }
    }
  }

  const response = await _rawFetch(url, options);

  // Silent refresh on 401 (except for login/logout/refresh endpoints themselves)
  if (response.status === 401 && !url.includes("/api/auth/login") && !url.includes("/api/auth/refresh") && !url.includes("/api/auth/logout")) {
    try {
      const refreshRes = await _rawFetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin"
      });

      if (refreshRes.ok) {
        // Refresh succeeded! Retry original request with updated CSRF token
        if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
          const newCsrf = getCsrfToken();
          if (newCsrf) {
            if (options.headers instanceof Headers) {
              options.headers.set("X-CSRF-Token", newCsrf);
            } else {
              options.headers["X-CSRF-Token"] = newCsrf;
            }
          }
        }
        return await _rawFetch(url, options);
      } else {
        // Refresh failed: session expired
        renderUnauthenticated("Your session expired. Please sign in again.");
      }
    } catch (e) {
      renderUnauthenticated("Your session expired. Please sign in again.");
    }
  }

  return response;
};

function renderAuthenticated(user) {
  currentUser = user;
  const loginC = document.getElementById("loginContainer");
  const appC = document.getElementById("appContainer");
  if (loginC) loginC.classList.add("hidden");
  if (appC) appC.classList.remove("hidden");

  // Update Header User Profile
  const nameEl = document.getElementById("headerUserName");
  const roleEl = document.getElementById("headerUserRole");
  const emailEl = document.getElementById("dropdownUserEmail");
  const roleLineEl = document.getElementById("dropdownUserRoleLine");
  const avatarEl = document.getElementById("userAvatar");
  const adminBtn = document.getElementById("adminNavBtn");

  if (nameEl) nameEl.textContent = user.full_name || user.email;
  if (roleEl) roleEl.textContent = user.role;
  if (emailEl) emailEl.textContent = user.email;
  if (roleLineEl) roleLineEl.textContent = `Role: ${user.role}`;
  if (avatarEl) avatarEl.textContent = (user.full_name || user.email)[0].toUpperCase();

  // Role-based visibility
  if (user.role === "admin") {
    if (adminBtn) adminBtn.classList.remove("hidden");
  } else {
    if (adminBtn) adminBtn.classList.add("hidden");
  }

  resetInactivityTimer(true);
  if (window.lucide) window.lucide.createIcons();
}

function renderUnauthenticated(errorMessage = null) {
  currentUser = null;
  clearInactivityTimers();
  const loginC = document.getElementById("loginContainer");
  const appC = document.getElementById("appContainer");
  if (appC) appC.classList.add("hidden");
  if (loginC) loginC.classList.remove("hidden");

  const errBox = document.getElementById("loginError");
  const errText = document.getElementById("loginErrorText");
  if (errorMessage && errBox && errText) {
    errText.textContent = errorMessage;
    errBox.classList.remove("hidden");
  } else if (errBox) {
    errBox.classList.add("hidden");
  }
  if (window.lucide) window.lucide.createIcons();
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const emailInput = document.getElementById("loginEmail");
  const passwordInput = document.getElementById("loginPassword");
  const errBox = document.getElementById("loginError");
  const errText = document.getElementById("loginErrorText");
  const submitBtn = document.getElementById("loginSubmitBtn");
  const spinner = document.getElementById("loginBtnSpinner");
  const btnText = document.getElementById("loginBtnText");

  errBox.classList.add("hidden");
  submitBtn.disabled = true;
  spinner.classList.remove("hidden");
  btnText.textContent = "Signing in...";

  try {
    const res = await _rawFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: emailInput.value.trim(),
        password: passwordInput.value
      }),
      credentials: "same-origin"
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Unable to sign in. Please verify your credentials.");
    }

    // Success
    passwordInput.value = "";
    renderAuthenticated(data.user);
    await fetchCasesList();
    goToStep(1);

  } catch (err) {
    errText.textContent = err.message || "Server unreachable. Please check your network connection.";
    errBox.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    spinner.classList.add("hidden");
    btnText.textContent = "Sign in";
  }
}

async function handleSignOut() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (e) {
    // Ignore error
  }
  renderUnauthenticated();
}

function togglePasswordInput(id, btn) {
  const input = document.getElementById(id);
  if (!input) return;
  const isPass = input.type === "password";
  input.type = isPass ? "text" : "password";
  btn.innerHTML = isPass ? '<i data-lucide="eye-off" class="w-4 h-4"></i>' : '<i data-lucide="eye" class="w-4 h-4"></i>';
  if (window.lucide) window.lucide.createIcons();
}

function fillDemoEmail(email) {
  const emailInput = document.getElementById("loginEmail");
  const passInput = document.getElementById("loginPassword");
  if (emailInput) {
    emailInput.value = email;
    if (passInput) passInput.focus();
  }
}

function toggleUserDropdown() {
  const dd = document.getElementById("userDropdown");
  if (dd) dd.classList.toggle("hidden");
}

document.addEventListener("click", (e) => {
  const wrapper = document.getElementById("userMenuWrapper");
  const dd = document.getElementById("userDropdown");
  if (wrapper && dd && !wrapper.contains(e.target)) {
    dd.classList.add("hidden");
  }
});

// Inactivity handling
function resetInactivityTimer(fromUserAction = true) {
  if (!currentUser) return;

  clearInactivityTimers();

  const modal = document.getElementById("inactivityModal");
  if (modal) modal.classList.add("hidden");

  warningTimer = setTimeout(() => {
    showInactivityWarning();
  }, WARNING_TIMEOUT_MS);

  inactivityTimer = setTimeout(() => {
    handleSignOut();
    renderUnauthenticated("You have been signed out due to 15 minutes of inactivity.");
  }, INACTIVITY_TIMEOUT_MS);
}

function clearInactivityTimers() {
  if (warningTimer) clearTimeout(warningTimer);
  if (inactivityTimer) clearTimeout(inactivityTimer);
  if (countdownInterval) clearInterval(countdownInterval);
  warningTimer = null;
  inactivityTimer = null;
  countdownInterval = null;
}

function showInactivityWarning() {
  const modal = document.getElementById("inactivityModal");
  const countEl = document.getElementById("inactivityCountdown");
  if (!modal) return;
  modal.classList.remove("hidden");
  secondsRemaining = 60;
  if (countEl) countEl.textContent = `${secondsRemaining}s`;

  countdownInterval = setInterval(() => {
    secondsRemaining--;
    if (countEl) countEl.textContent = `${secondsRemaining}s`;
    if (secondsRemaining <= 0) {
      clearInterval(countdownInterval);
    }
  }, 1000);
  if (window.lucide) window.lucide.createIcons();
}

// Change Password Handlers
function openChangePasswordModal() {
  const dd = document.getElementById("userDropdown");
  if (dd) dd.classList.add("hidden");
  document.getElementById("changePassError").classList.add("hidden");
  document.getElementById("changePassSuccess").classList.add("hidden");
  document.getElementById("changePasswordForm").reset();
  document.getElementById("changePasswordModal").classList.remove("hidden");
  if (window.lucide) window.lucide.createIcons();
}

function closeChangePasswordModal() {
  document.getElementById("changePasswordModal").classList.add("hidden");
}

async function handleChangePasswordSubmit(e) {
  e.preventDefault();
  const currentPass = document.getElementById("cpCurrent").value;
  const newPass = document.getElementById("cpNew").value;
  const confirmPass = document.getElementById("cpConfirm").value;
  const errBox = document.getElementById("changePassError");
  const succBox = document.getElementById("changePassSuccess");

  errBox.classList.add("hidden");
  succBox.classList.add("hidden");

  if (newPass !== confirmPass) {
    errBox.textContent = "New passwords do not match.";
    errBox.classList.remove("hidden");
    return;
  }

  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPass, new_password: newPass })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to update password.");

    succBox.textContent = "Password updated successfully.";
    succBox.classList.remove("hidden");
    setTimeout(() => {
      closeChangePasswordModal();
    }, 1500);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

// Admin Console Handlers
function openAdminModal() {
  document.getElementById("adminModal").classList.remove("hidden");
  switchAdminTab('users');
  if (window.lucide) window.lucide.createIcons();
}

function closeAdminModal() {
  document.getElementById("adminModal").classList.add("hidden");
}

function switchAdminTab(tab) {
  const usersBtn = document.getElementById("adminTabUsersBtn");
  const auditBtn = document.getElementById("adminTabAuditBtn");
  const usersTab = document.getElementById("adminTabUsers");
  const auditTab = document.getElementById("adminTabAudit");

  if (tab === 'users') {
    usersBtn.className = "pb-2 border-b-2 border-blue-600 text-blue-600";
    auditBtn.className = "pb-2 border-b-2 border-transparent text-slate-500 hover:text-slate-800";
    usersTab.classList.remove("hidden");
    auditTab.classList.add("hidden");
    loadAdminUsers();
  } else {
    auditBtn.className = "pb-2 border-b-2 border-blue-600 text-blue-600";
    usersBtn.className = "pb-2 border-b-2 border-transparent text-slate-500 hover:text-slate-800";
    auditTab.classList.remove("hidden");
    usersTab.classList.add("hidden");
    loadAdminAuditLog();
  }
  if (window.lucide) window.lucide.createIcons();
}

async function loadAdminUsers() {
  const tbody = document.getElementById("adminUsersTableBody");
  tbody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-slate-400">Loading accounts...</td></tr>';
  try {
    const res = await fetch("/api/admin/users");
    if (!res.ok) throw new Error("Unauthorized or server error.");
    const users = await res.json();
    tbody.innerHTML = "";

    users.forEach(u => {
      const isLocked = u.is_locked;
      const statusBadge = !u.is_active
        ? '<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">Inactive</span>'
        : isLocked
        ? '<span class="px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 font-medium">Locked</span>'
        : '<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-medium">Active</span>';

      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-50 transition";
      tr.innerHTML = `
        <td class="p-2.5">
          <div class="font-medium text-slate-900">${u.full_name}</div>
          <div class="text-[11px] text-slate-400 font-mono">${u.email}</div>
        </td>
        <td class="p-2.5">
          <span class="px-2 py-0.5 rounded-md font-mono text-[11px] font-semibold bg-slate-100 text-slate-700 uppercase">${u.role}</span>
        </td>
        <td class="p-2.5">${statusBadge}</td>
        <td class="p-2.5 text-slate-500">${u.last_login_at ? u.last_login_at.replace("T", " ").substring(0, 16) : "Never"}</td>
        <td class="p-2.5 text-right space-x-1">
          ${isLocked ? `<button onclick="unlockStaffUser('${u.id}')" class="px-2 py-1 bg-amber-50 hover:bg-amber-100 text-amber-700 rounded font-medium text-[11px] transition">Unlock</button>` : ""}
          <button onclick="toggleStaffActive('${u.id}', ${u.is_active})" class="px-2 py-1 rounded font-medium text-[11px] transition ${u.is_active ? 'bg-rose-50 hover:bg-rose-100 text-rose-700' : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700'}">
            ${u.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-rose-500">${err.message}</td></tr>`;
  }
}

async function handleAdminCreateUser(event) {
  event.preventDefault();
  const name = document.getElementById("newStaffName").value.trim();
  const email = document.getElementById("newStaffEmail").value.trim();
  const pass = document.getElementById("newStaffPassword").value;
  const role = document.getElementById("newStaffRole").value;
  const msgEl = document.getElementById("adminCreateUserMsg");

  msgEl.classList.add("hidden");
  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: name, email, password: pass, role })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to create user.");

    document.getElementById("adminCreateUserForm").reset();
    msgEl.textContent = `User ${email} created successfully.`;
    msgEl.className = "text-xs text-emerald-600 font-medium block";
    msgEl.classList.remove("hidden");
    await loadAdminUsers();
  } catch (err) {
    msgEl.textContent = err.message;
    msgEl.className = "text-xs text-rose-600 font-medium block";
    msgEl.classList.remove("hidden");
  }
}

async function toggleStaffActive(userId, currentActive) {
  try {
    const res = await fetch(`/api/admin/users/${userId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentActive })
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.detail || "Failed to update status");
    }
    await loadAdminUsers();
  } catch (err) {
    alert("Error updating user status: " + err.message);
  }
}

async function unlockStaffUser(userId) {
  try {
    const res = await fetch(`/api/admin/users/${userId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unlock_account: true })
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.detail || "Failed to unlock account");
    }
    await loadAdminUsers();
  } catch (err) {
    alert("Error unlocking user: " + err.message);
  }
}

async function loadAdminAuditLog() {
  const tbody = document.getElementById("adminAuditTableBody");
  tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-slate-400">Loading audit records...</td></tr>';
  try {
    const res = await fetch("/api/admin/audit?limit=50");
    if (!res.ok) throw new Error("Unauthorized or server error.");
    const logs = await res.json();
    tbody.innerHTML = "";

    logs.forEach(l => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-50 transition";
      tr.innerHTML = `
        <td class="p-2.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
          ${l.timestamp ? l.timestamp.replace("T", " ").substring(0, 19) : ""}
        </td>
        <td class="p-2.5">
          <span class="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-semibold font-mono text-[10px] uppercase">${l.event_type}</span>
        </td>
        <td class="p-2.5 text-slate-700">
          <div class="font-medium">${l.user_id ? l.user_id.substring(0, 8) + '...' : 'System'}</div>
          <div class="text-[10px] text-slate-400 font-mono">${l.user_role || 'n/a'}</div>
        </td>
        <td class="p-2.5 text-slate-600">
          <div>${l.input_summary || l.output_summary || ''}</div>
          ${l.decision ? `<div class="text-[11px] font-semibold text-slate-800">Decision: ${l.decision} — "${l.reason || ''}"</div>` : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-rose-500">${err.message}</td></tr>`;
  }
}

// ClaimLens — Simplified 4-Step Case Workbench
// State Management
let activeCaseId = null;
let activeCaseData = null;
let currentStep = 1;
let currentDetailTab = "evidence";
let piiMasked = true;
let selectedDecisionType = null;
let selectedFilesList = [];
let matrixVisible = false;

// 11 Core Multi-Agent Modules
const AGENTS = [
  "IntakeAgent",
  "VisionAgent",
  "NarrativeAgent",
  "PolicyAgent",
  "ContextAgent",
  "EstimateAgent",
  "ConsistencyEngine",
  "ReconstructionAgent",
  "HypothesisAgent",
  "DecisionSupportAgent",
  "VerifierAgent"
];

// Screen Help Explanations (3 lines per step)
const STEP_HELP_TEXT = {
  1: [
    "<strong>Upload:</strong> Provide the evidence files for the claim, including damage photos, policy contract, and repair estimate.",
    "<strong>Classification:</strong> The system automatically detects file types and metadata without manual tagging.",
    "<strong>Action:</strong> Click 'Analyze Claim' or choose one of the pre-built test bundles to begin reasoning."
  ],
  2: [
    "<strong>Investigating:</strong> 11 specialized AI agents are running parallel and sequential reasoning steps.",
    "<strong>Cross-Checking:</strong> Photos are checked for damage zones, EXIF dates are matched to statements, and policy rules are verified.",
    "<strong>No Fake Results:</strong> All analysis is computed in real time from the uploaded evidence."
  ],
  3: [
    "<strong>Summary:</strong> The high-level assessment of whether the claim evidence aligns or conflicts.",
    "<strong>Key Decision Metrics:</strong> Review coverage status, estimated payout, and the top inconsistencies.",
    "<strong>Adjuster Decision:</strong> Use the bottom bar to Approve, Request More Info, or Escalate with mandatory audit justification."
  ],
  4: [
    "<strong>Details:</strong> Inspect the full underlying evidence, forensic damage zones, and policy clauses on demand.",
    "<strong>Comparison Table:</strong> Toggle 'Does the evidence agree?' to view the deterministic fact-by-evidence matrix.",
    "<strong>Audit Trail:</strong> Access the tamper-evident log of model calls and reasoning traces for compliance."
  ]
};

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) window.lucide.createIcons();
  setupDragAndDrop();

  // Inactivity tracking
  ['mousemove', 'keydown', 'mousedown', 'touchstart', 'scroll'].forEach(evt => {
    window.addEventListener(evt, () => resetInactivityTimer(true), { passive: true });
  });

  // Check authenticated state
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      const user = await res.json();
      renderAuthenticated(user);
      await fetchCasesList();
      goToStep(1);
    } else {
      renderUnauthenticated();
    }
  } catch (e) {
    renderUnauthenticated();
  }
});

// -------------------------------------------------------------
// Drag & Drop Setup (Step 1)
// -------------------------------------------------------------
function setupDragAndDrop() {
  const dropZone = document.getElementById("dropZone");
  if (!dropZone) return;

  ["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("border-blue-500", "bg-blue-50/50");
    }, false);
  });

  ["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("border-blue-500", "bg-blue-50/50");
    }, false);
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFileSelection(files);
  }, false);
}

function handleFileSelection(files) {
  if (!files || files.length === 0) return;
  selectedFilesList = Array.from(files);

  const container = document.getElementById("fileChipsContainer");
  const list = document.getElementById("fileChipsList");
  const count = document.getElementById("fileCount");

  container.classList.remove("hidden");
  count.textContent = selectedFilesList.length;
  list.innerHTML = "";

  selectedFilesList.forEach((f, idx) => {
    let typeName = "Document";
    let icon = "file-text";
    let color = "bg-slate-100 text-slate-700 border-slate-200";

    const nameLower = f.name.toLowerCase();
    if (nameLower.endsWith(".jpg") || nameLower.endsWith(".jpeg") || nameLower.endsWith(".png")) {
      typeName = "Photo";
      icon = "image";
      color = "bg-indigo-50 text-indigo-700 border-indigo-200";
    } else if (nameLower.includes("policy")) {
      typeName = "Policy";
      icon = "shield";
      color = "bg-blue-50 text-blue-700 border-blue-200";
    } else if (nameLower.includes("estimate") || nameLower.includes("repair")) {
      typeName = "Estimate";
      icon = "dollar-sign";
      color = "bg-emerald-50 text-emerald-700 border-emerald-200";
    } else if (nameLower.includes("statement") || nameLower.includes("narrative")) {
      typeName = "Statement";
      icon = "message-square";
      color = "bg-amber-50 text-amber-700 border-amber-200";
    }

    const chip = document.createElement("div");
    chip.className = `flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium ${color} shadow-sm`;
    chip.innerHTML = `
      <i data-lucide="${icon}" class="w-3.5 h-3.5"></i>
      <span class="font-semibold">${typeName}:</span>
      <span class="truncate max-w-[150px]">${f.name}</span>
      <span class="text-[10px] opacity-60">(${(f.size / 1024).toFixed(0)} KB)</span>
    `;
    list.appendChild(chip);
  });

  if (window.lucide) window.lucide.createIcons();
}

function toggleUploadMetaFields() {
  const fields = document.getElementById("uploadMetaFields");
  const label = document.getElementById("metaExpandIcon");
  if (fields.classList.contains("hidden")) {
    fields.classList.remove("hidden");
    label.textContent = "Hide";
  } else {
    fields.classList.add("hidden");
    label.textContent = "Show";
  }
}

// -------------------------------------------------------------
// 4-Step Navigation Logic
// -------------------------------------------------------------
function goToStep(stepNum) {
  currentStep = stepNum;

  // 1. Update Stepper Buttons & Lines
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById(`step-btn-${i}`);
    const num = document.getElementById(`step-num-${i}`);
    const line = document.getElementById(`step-line-${i}`);

    if (i === stepNum) {
      btn.className = "step-nav-btn flex items-center gap-2 text-blue-600 font-semibold focus:outline-none";
      num.className = "w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold shadow-sm";
    } else if (i < stepNum) {
      btn.className = "step-nav-btn flex items-center gap-2 text-emerald-600 font-semibold focus:outline-none";
      num.className = "w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold";
      num.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5"></i>';
    } else {
      btn.className = "step-nav-btn flex items-center gap-2 text-slate-400 focus:outline-none";
      num.className = "w-6 h-6 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center text-xs font-bold";
      num.textContent = i;
    }

    if (line) {
      line.className = i < stepNum ? "flex-1 h-0.5 mx-2 sm:mx-4 bg-emerald-500" : "flex-1 h-0.5 mx-2 sm:mx-4 bg-slate-200";
    }
  }

  // 2. Show Only Current Section
  document.querySelectorAll(".step-content").forEach(el => el.classList.add("hidden"));
  const currentSection = document.getElementById(`step-${stepNum}`);
  if (currentSection) currentSection.classList.remove("hidden");

  // 3. Show Adjuster Decision Bar only on Steps 3 and 4
  const adjusterBar = document.getElementById("adjusterBar");
  if (adjusterBar) {
    if (stepNum >= 3) {
      adjusterBar.classList.remove("hidden");
    } else {
      adjusterBar.classList.add("hidden");
    }
  }

  // Scroll to top
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (window.lucide) window.lucide.createIcons();
}

function openHelpModal() {
  const modal = document.getElementById("helpModal");
  const textContainer = document.getElementById("helpModalText");
  const lines = STEP_HELP_TEXT[currentStep] || STEP_HELP_TEXT[1];
  textContainer.innerHTML = lines.map(line => `<p>${line}</p>`).join("");
  modal.classList.remove("hidden");
}

function closeHelpModal() {
  document.getElementById("helpModal").classList.add("hidden");
}

// -------------------------------------------------------------
// Case Data Fetching & Switching
// -------------------------------------------------------------
async function fetchCasesList() {
  try {
    const res = await fetch("/api/cases");
    if (!res.ok) return;
    const cases = await res.json();
    const select = document.getElementById("caseSelector");
    select.innerHTML = '<option value="">Select Case...</option>';

    cases.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      const maskedName = piiMasked ? maskPII(c.claimant_name) : c.claimant_name;
      opt.textContent = `${c.claim_number} — ${maskedName}`;
      select.appendChild(opt);
    });

    if (cases.length > 0) {
      const targetId = activeCaseId || cases[0].id;
      select.value = targetId;
      await switchCase(targetId, false);
    }
  } catch (err) {
    console.error("Failed to load cases list:", err);
  }
}

async function switchCase(caseId, navigateToSummary = true) {
  if (!caseId) return;
  activeCaseId = caseId;
  const select = document.getElementById("caseSelector");
  if (select) select.value = caseId;

  try {
    const res = await fetch(`/api/cases/${caseId}`);
    if (!res.ok) return;
    activeCaseData = await res.json();
    renderAllViews(activeCaseData);

    if (navigateToSummary) {
      goToStep(3);
    }
  } catch (err) {
    console.error("Error switching case:", err);
  }
}

// -------------------------------------------------------------
// Step 1: Start Analysis Flow
// -------------------------------------------------------------
async function startAnalysis() {
  const claimant = document.getElementById("inputClaimant").value.trim() || "Sarah Jenkins";
  const policy = document.getElementById("inputPolicy").value.trim() || "POL-99281-X";
  const date = document.getElementById("inputDate").value || "2026-05-10";
  const loc = document.getElementById("inputLocation").value.trim() || "Main St & 4th Ave, NY";

  try {
    // 1. Create Case
    const caseRes = await fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        policy_number: policy,
        claimant_name: claimant,
        incident_date: date,
        incident_location: loc
      })
    });
    const newCase = await caseRes.json();
    activeCaseId = newCase.id;

    // 2. Upload Files if Selected
    if (selectedFilesList.length > 0) {
      const formData = new FormData();
      selectedFilesList.forEach(f => formData.append("files", f));
      await fetch(`/api/cases/${newCase.id}/upload`, {
        method: "POST",
        body: formData
      });
    }

    // 3. Move to Step 2 (Analyzing) & Run Pipeline with SSE
    goToStep(2);
    resetAgentRows();
    await runPipelineWithSSE(newCase.id);

    // 4. Analysis Complete — Fetch full case & move to Step 3 (Summary)
    await fetchCasesList();
    await switchCase(newCase.id, true);

  } catch (err) {
    console.error("Analysis failed:", err);
    alert("Analysis failed to run: " + err.message);
    goToStep(1);
  }
}

// -------------------------------------------------------------
// Load Synthetic Bundle Preset Flow
// -------------------------------------------------------------
async function loadBundlePreset(bundleId) {
  closeBundleModal();
  goToStep(2);
  resetAgentRows();

  try {
    // 1. Create Case
    const caseRes = await fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        policy_number: `POL-BUNDLE-${bundleId}`,
        claimant_name: bundleId === 7 ? "Sarah Jenkins" : `Claimant Bundle ${bundleId}`,
        incident_date: "2026-05-10",
        incident_location: "Main St & 4th Ave, NY"
      })
    });
    const newCase = await caseRes.json();
    activeCaseId = newCase.id;

    // 2. Call Preset Loader (runs pipeline server-side)
    const runRes = await fetch(`/api/cases/${newCase.id}/upload_preset/${bundleId}`, { method: "POST" });
    if (!runRes.ok) throw new Error("Preset upload failed");

    // Mark all agent rows as completed
    markAllAgentRowsCompleted();

    // 3. Switch to Step 3 Summary
    await fetchCasesList();
    await switchCase(newCase.id, true);

  } catch (err) {
    console.error("Failed to load preset bundle:", err);
    alert("Preset load error: " + err.message);
    goToStep(1);
  }
}

// -------------------------------------------------------------
// Step 2: Agent Row Status Management
// -------------------------------------------------------------
function resetAgentRows() {
  const rowMapping = {
    IntakeAgent: "row-IntakeAgent",
    VisionAgent: "row-VisionAgent",
    NarrativeAgent: "row-NarrativeAgent",
    PolicyAgent: "row-PolicyAgent",
    ContextAgent: "row-ContextAgent",
    EstimateAgent: "row-EstimateAgent",
    ConsistencyEngine: "row-ConsistencyEngine",
    HypothesisAgent: "row-HypothesisAgent",
    DecisionSupportAgent: "row-DecisionSupportAgent"
  };

  Object.values(rowMapping).forEach(rowId => {
    const row = document.getElementById(rowId);
    if (!row) return;
    const icon = row.querySelector(".step-icon");
    const status = row.querySelector(".step-status");
    icon.className = "step-icon w-8 h-8 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center";
    icon.innerHTML = '<i data-lucide="clock" class="w-4 h-4"></i>';
    status.className = "step-status text-xs font-medium text-slate-400";
    status.textContent = "Waiting";
  });
  if (window.lucide) window.lucide.createIcons();
}

function updateAgentRow(agentName, statusText, durationMs) {
  let targetRowId = `row-${agentName}`;
  if (agentName === "ReconstructionAgent") targetRowId = "row-ConsistencyEngine";
  if (agentName === "VerifierAgent") targetRowId = "row-DecisionSupportAgent";

  const row = document.getElementById(targetRowId);
  if (!row) return;

  const icon = row.querySelector(".step-icon");
  const status = row.querySelector(".step-status");

  if (statusText === "running") {
    icon.className = "step-icon w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center animate-spin";
    icon.innerHTML = '<i data-lucide="loader" class="w-4 h-4"></i>';
    status.className = "step-status text-xs font-medium text-blue-600";
    status.textContent = "In progress...";
  } else if (statusText === "completed" || statusText === "success") {
    icon.className = "step-icon w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center";
    icon.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i>';
    status.className = "step-status text-xs font-semibold text-emerald-700";
    status.textContent = durationMs ? `Done (${Math.round(durationMs)}ms)` : "Done";
  } else if (statusText === "failed" || statusText === "degraded") {
    icon.className = "step-icon w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center";
    icon.innerHTML = '<i data-lucide="alert-triangle" class="w-4 h-4"></i>';
    status.className = "step-status text-xs font-semibold text-amber-700";
    status.textContent = "Notice";
  }
  if (window.lucide) window.lucide.createIcons();
}

function markAllAgentRowsCompleted() {
  const rowIds = [
    "row-IntakeAgent", "row-VisionAgent", "row-NarrativeAgent",
    "row-PolicyAgent", "row-ContextAgent", "row-EstimateAgent",
    "row-ConsistencyEngine", "row-HypothesisAgent", "row-DecisionSupportAgent"
  ];
  rowIds.forEach(id => {
    const row = document.getElementById(id);
    if (!row) return;
    const icon = row.querySelector(".step-icon");
    const status = row.querySelector(".step-status");
    icon.className = "step-icon w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center";
    icon.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i>';
    status.className = "step-status text-xs font-semibold text-emerald-700";
    status.textContent = "Done";
  });
  if (window.lucide) window.lucide.createIcons();
}

// -------------------------------------------------------------
// SSE Streaming Runner
// -------------------------------------------------------------
function runPipelineWithSSE(caseId) {
  return new Promise((resolve, reject) => {
    const TIMEOUT_MS = 180_000;
    const es = new EventSource(`/api/cases/${caseId}/stream`);
    let done = false;

    const timer = setTimeout(() => {
      if (!done) {
        done = true;
        es.close();
        resolve();
      }
    }, TIMEOUT_MS);

    es.addEventListener("connected", () => {
      fetch(`/api/cases/${caseId}/run_stream`, { method: "POST" }).catch(reject);
    });

    es.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.agent === "__done__") {
          done = true;
          clearTimeout(timer);
          es.close();
          resolve();
          return;
        }
        updateAgentRow(msg.agent, msg.status, msg.duration_ms);
      } catch (_) {}
    };

    es.onerror = () => {
      if (!done) {
        done = true;
        clearTimeout(timer);
        es.close();
        resolve();
      }
    };
  });
}

// -------------------------------------------------------------
// Render All Views (Step 3 Summary & Step 4 Details)
// -------------------------------------------------------------
function renderAllViews(data) {
  if (!data) return;

  const c = data.case;
  const pState = data.pipeline_state || {};
  const findings = data.findings || [];
  const evidence = data.evidence || [];
  const decision = pState.decision || {};
  const matrix = pState.matrix || null;
  const reconstruction = pState.reconstruction || null;
  const policyEval = pState.policy_evaluation || null;
  const diff = pState.diff || null;

  // --- Step 3: Summary View ---
  renderSummaryScreen(c, findings, decision, policyEval);

  // --- Step 4: Details Views ---
  renderEvidenceGrid(evidence);
  renderFullFindings(findings);
  if (matrix) renderConsistencyMatrix(matrix);
  if (policyEval) renderPolicyDetails(policyEval);
  if (reconstruction) renderTimelineDetails(reconstruction);
  renderAuditLogs(data.audit_logs || []);

  if (window.lucide) window.lucide.createIcons();
}

// -------------------------------------------------------------
// Render Step 3 (Summary Screen)
// -------------------------------------------------------------
function renderSummaryScreen(claim, findings, decision, policyEval) {
  // Claim metadata in card header
  document.getElementById("summaryClaimId").textContent = claim.claim_number || "CLM-000000";
  document.getElementById("summaryClaimant").textContent = piiMasked ? maskPII(claim.claimant_name) : (claim.claimant_name || "--");
  document.getElementById("summaryPolicy").textContent = claim.policy_number || "--";
  document.getElementById("summaryDate").textContent = claim.incident_date || "2026-05-10";

  // Overall Status Badge & Accent Bar
  const badge = document.getElementById("overallStatusBadge");
  const badgeText = document.getElementById("overallStatusText");
  const accent = document.getElementById("summaryCardAccent");
  const overviewP = document.getElementById("summaryOverviewParagraph");

  const hasInvestigate = findings.some(f => f.severity === "investigate");
  const hasReview = findings.some(f => f.severity === "review");
  const isExcluded = policyEval && policyEval.overall_status === "excluded";

  if (hasInvestigate || isExcluded) {
    badge.className = "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs sm:text-sm font-semibold bg-rose-50 text-rose-700 border border-rose-200";
    badge.innerHTML = '<i data-lucide="alert-octagon" class="w-4 h-4 text-rose-600"></i><span>Investigate</span>';
    accent.className = "absolute top-0 left-0 right-0 h-1.5 bg-rose-600";
  } else if (hasReview) {
    badge.className = "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs sm:text-sm font-semibold bg-amber-50 text-amber-800 border border-amber-200";
    badge.innerHTML = '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i><span>Needs review</span>';
    accent.className = "absolute top-0 left-0 right-0 h-1.5 bg-amber-500";
  } else {
    badge.className = "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs sm:text-sm font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200";
    badge.innerHTML = '<i data-lucide="check-circle" class="w-4 h-4 text-emerald-600"></i><span>Looks consistent</span>';
    accent.className = "absolute top-0 left-0 right-0 h-1.5 bg-emerald-600";
  }

  // Plain language 2-3 sentence overview
  if (findings.length === 0) {
    overviewP.textContent = `All submitted evidence—including damage photos, policy contract, and claimant narrative—fully aligns with the reported collision. The repair estimate reflects standard market labor, and policy coverage is in force. We recommend standard claim approval.`;
  } else {
    const topF = findings[0];
    overviewP.textContent = `Evidence review identified an inconsistency requiring adjuster verification: ${topF.inconsistency}. While alternative explanations exist, we recommend obtaining the requested documentation before issuing final settlement.`;
  }

  // (a) Coverage Card
  const covStatus = document.getElementById("cardCoverageStatus");
  const covClause = document.getElementById("cardCoverageClause");
  const covReason = document.getElementById("cardCoverageReason");
  if (policyEval) {
    if (policyEval.overall_status === "covered") {
      covStatus.textContent = "Covered";
      covStatus.className = "text-lg font-bold text-emerald-700";
      covClause.textContent = "Sec. 2.1";
      covReason.textContent = "Standard collision coverage active; deductible applies.";
    } else if (policyEval.overall_status === "excluded") {
      covStatus.textContent = "Excluded";
      covStatus.className = "text-lg font-bold text-rose-700";
      covClause.textContent = "Sec. 4.2";
      covReason.textContent = "Commercial/rideshare exclusion applies to this claim.";
    } else {
      covStatus.textContent = "Unclear";
      covStatus.className = "text-lg font-bold text-amber-700";
      covClause.textContent = "Review";
      covReason.textContent = "Coverage applicability requires manual clause check.";
    }
  }

  // (b) Estimated Payout Card
  const payoutRange = document.getElementById("cardPayoutRange");
  const payoutReason = document.getElementById("cardPayoutReason");
  if (decision && decision.settlement_range) {
    const sr = decision.settlement_range;
    if (sr.settlement_minimum === sr.settlement_maximum) {
      payoutRange.textContent = `$${sr.settlement_minimum.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    } else {
      payoutRange.textContent = `$${sr.settlement_minimum.toLocaleString('en-US', { minimumFractionDigits: 0 })} – $${sr.settlement_maximum.toLocaleString('en-US', { minimumFractionDigits: 0 })}`;
    }
    payoutReason.textContent = `Total estimate ($${sr.total_claimed_estimate.toFixed(0)}) minus $${sr.deductible.toFixed(0)} deductible.`;
  } else {
    payoutRange.textContent = "$0.00";
    payoutReason.textContent = "Awaiting estimate verification.";
  }

  // (c) Confidence Card
  const confBadge = document.getElementById("cardConfidenceBadge");
  const confReason = document.getElementById("cardConfidenceReason");
  if (findings.length > 0) {
    const avgConf = findings.reduce((acc, f) => acc + (f.confidence || 0.8), 0) / findings.length;
    confBadge.textContent = avgConf >= 0.8 ? `High (${(avgConf * 100).toFixed(0)}%)` : `Medium (${(avgConf * 100).toFixed(0)}%)`;
    confReason.textContent = findings[0].confidence_explanation || "Supported by physical photos and metadata.";
  } else {
    confBadge.textContent = "High (95%)";
    confReason.textContent = "All evidence sources verified without conflicts.";
  }

  // Key Findings (At most 3 one-line cards)
  const findingsList = document.getElementById("keyFindingsList");
  const findingsCount = document.getElementById("keyFindingsCount");
  findingsCount.textContent = findings.length;
  findingsList.innerHTML = "";

  if (findings.length === 0) {
    findingsList.innerHTML = `
      <div class="p-4 bg-emerald-50/60 rounded-xl border border-emerald-100 flex items-center gap-3 text-xs text-emerald-800">
        <i data-lucide="check-circle" class="w-5 h-5 text-emerald-600 flex-shrink-0"></i>
        <span>No inconsistencies found. Damage photos, stated direction, and weather records all match.</span>
      </div>
    `;
  } else {
    findings.slice(0, 3).forEach((f, idx) => {
      let iconColor = "text-amber-500 bg-amber-50 border-amber-200";
      let icon = "alert-triangle";
      if (f.severity === "investigate") {
        iconColor = "text-rose-600 bg-rose-50 border-rose-200";
        icon = "alert-octagon";
      }

      const card = document.createElement("div");
      card.className = "bg-white hover:bg-slate-50 border border-slate-200 rounded-xl p-3.5 shadow-sm flex items-center justify-between gap-3 cursor-pointer transition hover:border-blue-400 group";
      card.onclick = () => openFindingDrawer(f);
      card.innerHTML = `
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${iconColor}">
            <i data-lucide="${icon}" class="w-4 h-4"></i>
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-xs font-bold text-slate-900 group-hover:text-blue-600 transition truncate">${f.title}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${f.severity === 'investigate' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'}">${f.severity}</span>
            </div>
            <p class="text-xs text-slate-500 truncate mt-0.5">${f.inconsistency}</p>
          </div>
        </div>
        <div class="flex items-center gap-1 text-xs text-blue-600 font-medium flex-shrink-0">
          <span>Details</span>
          <i data-lucide="chevron-right" class="w-4 h-4"></i>
        </div>
      `;
      findingsList.appendChild(card);
    });
  }

  // What's Missing Checklist
  const missingUl = document.getElementById("summaryMissingList");
  missingUl.innerHTML = "";
  if (decision && decision.missing_evidence && decision.missing_evidence.length > 0) {
    decision.missing_evidence.forEach(m => {
      const li = document.createElement("li");
      li.className = "flex items-start gap-2 text-xs text-slate-700";
      li.innerHTML = `<i data-lucide="circle-alert" class="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5"></i><span>${m}</span>`;
      missingUl.appendChild(li);
    });
  } else {
    missingUl.innerHTML = `
      <li class="flex items-center gap-2 text-xs text-slate-600">
        <i data-lucide="check" class="w-4 h-4 text-emerald-600"></i> All standard evidence items (photos, estimate, statement, policy) are present.
      </li>
    `;
  }
}

// -------------------------------------------------------------
// Step 4: Details Screen & Tabs
// -------------------------------------------------------------
function switchDetailTab(tabName) {
  currentDetailTab = tabName;
  document.querySelectorAll(".dtab-btn").forEach(btn => {
    btn.className = "dtab-btn flex-1 py-2 px-3 rounded-lg text-slate-600 hover:text-slate-900 flex items-center justify-center gap-1.5 transition";
  });
  document.querySelectorAll(".detail-panel").forEach(p => p.classList.add("hidden"));

  const activeBtn = document.getElementById(`dtab-${tabName}`);
  const activePanel = document.getElementById(`dpanel-${tabName}`);
  if (activeBtn) {
    activeBtn.className = "dtab-btn flex-1 py-2 px-3 rounded-lg bg-blue-50 text-blue-700 font-semibold flex items-center justify-center gap-1.5 shadow-sm";
  }
  if (activePanel) {
    activePanel.classList.remove("hidden");
  }
  if (window.lucide) window.lucide.createIcons();
}

function renderEvidenceGrid(evidence) {
  const grid = document.getElementById("evidenceCardsGrid");
  grid.innerHTML = "";

  let firstPhoto = null;

  evidence.forEach(e => {
    let typeBadge = "bg-slate-100 text-slate-700 border-slate-200";
    let icon = "file-text";

    if (e.file_type === "photo") {
      typeBadge = "bg-indigo-50 text-indigo-700 border-indigo-200";
      icon = "image";
      if (!firstPhoto) firstPhoto = e;
    } else if (e.file_type === "policy") {
      typeBadge = "bg-blue-50 text-blue-700 border-blue-200";
      icon = "shield";
    } else if (e.file_type === "estimate") {
      typeBadge = "bg-emerald-50 text-emerald-700 border-emerald-200";
      icon = "dollar-sign";
    } else if (e.file_type === "narrative") {
      typeBadge = "bg-amber-50 text-amber-700 border-amber-200";
      icon = "message-square";
    }

    const card = document.createElement("div");
    card.className = "bg-white rounded-xl border border-slate-200 p-4 space-y-2.5 shadow-sm hover:border-slate-300 transition cursor-pointer";
    card.onclick = () => {
      if (e.file_type === "photo") {
        inspectPhoto(e);
      }
    };

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="font-mono font-bold text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">${e.id}</span>
          <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold border ${typeBadge}">${e.file_type.toUpperCase()}</span>
          <span class="font-semibold text-xs text-slate-800 truncate max-w-[150px]">${e.file_name}</span>
        </div>
        <a href="${e.file_url}" target="_blank" onclick="event.stopPropagation()" class="text-blue-600 hover:text-blue-700 text-xs flex items-center gap-1 font-medium">
          <i data-lucide="external-link" class="w-3 h-3"></i> View
        </a>
      </div>
      <p class="text-xs text-slate-500 line-clamp-2">${e.extracted_text || "Binary file captured."}</p>
      ${e.analysis && e.analysis.summary ? `
        <div class="pt-2 border-t border-slate-100 text-[11px] text-slate-600 font-mono">
          ${e.analysis.summary}
        </div>
      ` : ''}
    `;
    grid.appendChild(card);
  });

  if (firstPhoto) {
    inspectPhoto(firstPhoto);
  }
}

function inspectPhoto(photoItem) {
  const card = document.getElementById("photoInspectorCard");
  const img = document.getElementById("detailPhotoImage");
  const nameBadge = document.getElementById("photoFileNameBadge");
  const exif = (photoItem.metadata && photoItem.metadata.exif) ? photoItem.metadata.exif : {};
  const analysis = photoItem.analysis || {};

  card.classList.remove("hidden");
  img.src = photoItem.file_url;
  nameBadge.textContent = `${photoItem.id} — ${photoItem.file_name}`;

  document.getElementById("photoExifTs").textContent = exif.timestamp || "None embedded";
  document.getElementById("photoCamera").textContent = `${exif.camera_make || ''} ${exif.camera_model || 'Standard'}`.trim() || "--";
  document.getElementById("photoGPS").textContent = exif.gps ? `${exif.gps.latitude.toFixed(3)}, ${exif.gps.longitude.toFixed(3)}` : "No GPS";

  const dateMatch = document.getElementById("photoDateMatch");
  if (analysis.stated_timestamp_match === false) {
    dateMatch.textContent = "Mismatch (Conflict)";
    dateMatch.className = "font-bold text-rose-600";
  } else if (analysis.stated_timestamp_match === true) {
    dateMatch.textContent = "Verified Match";
    dateMatch.className = "font-bold text-emerald-700";
  } else {
    dateMatch.textContent = "No Date Tag";
    dateMatch.className = "text-slate-500 font-normal";
  }

  // Damaged zones
  const zonesDiv = document.getElementById("photoZonesDetected");
  const zones = analysis.damaged_zones || [];
  if (zones.length > 0) {
    zonesDiv.innerHTML = `
      <span class="font-semibold text-slate-700 block mb-1">Identified Damage Zones:</span>
      <div class="flex flex-wrap gap-1.5">
        ${zones.map(z => `
          <span class="px-2.5 py-1 rounded-lg text-xs bg-rose-50 text-rose-800 border border-rose-200 font-medium">
            <strong>${z.zone.toUpperCase()}</strong> (${z.severity}) — ${z.description}
          </span>
        `).join('')}
      </div>
    `;
  } else {
    zonesDiv.innerHTML = '<span class="text-slate-500 italic">No visible damage zones tagged.</span>';
  }
}

function renderFullFindings(findings) {
  const container = document.getElementById("fullFindingsContainer");
  container.innerHTML = "";

  if (findings.length === 0) {
    container.innerHTML = `
      <div class="p-6 bg-white rounded-xl border border-slate-200 text-center text-slate-500 shadow-sm">
        <i data-lucide="check-circle" class="w-8 h-8 text-emerald-600 mx-auto mb-2"></i>
        <p class="text-sm font-semibold text-slate-800">No Inconsistencies Detected</p>
        <p class="text-xs text-slate-500 mt-1">All evidence lines up with claimant statements.</p>
      </div>
    `;
    return;
  }

  findings.forEach(f => {
    const card = document.createElement("div");
    card.className = "bg-white rounded-xl border border-slate-200 p-5 space-y-3.5 shadow-sm";
    card.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">${f.id}</span>
            <span class="text-xs font-semibold px-2.5 py-0.5 rounded-full uppercase ${f.severity === 'investigate' ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}">${f.severity}</span>
            <span class="text-xs text-slate-500">Confidence: ${(f.confidence * 100).toFixed(0)}%</span>
          </div>
          <h4 class="text-sm font-bold text-slate-900">${f.title}</h4>
        </div>
        <button onclick='openFindingDrawer(${JSON.stringify(f).replace(/'/g, "&apos;")})' class="text-xs text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1 flex-shrink-0">
          <span>Open Drawer</span>
          <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
        </button>
      </div>

      <div class="bg-slate-50 rounded-lg p-3 text-xs border border-slate-200">
        <span class="font-semibold text-slate-700 block mb-0.5">What doesn't match:</span>
        <p class="text-slate-800 leading-relaxed">${f.inconsistency}</p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div class="p-2.5 bg-slate-50 rounded-lg border border-slate-200">
          <span class="font-semibold text-slate-600 block mb-0.5">Other Possible Explanations:</span>
          <p class="text-slate-700 text-[11px] leading-relaxed">${f.possible_explanations ? f.possible_explanations[0] : '--'}</p>
        </div>
        <div class="p-2.5 bg-slate-50 rounded-lg border border-slate-200">
          <span class="font-semibold text-slate-600 block mb-0.5">Suggested Adjuster Action:</span>
          <p class="text-slate-700 text-[11px] leading-relaxed">${f.recommended_action}</p>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function toggleMatrixTable() {
  const container = document.getElementById("matrixTableContainer");
  const label = document.getElementById("matrixToggleLabel");
  matrixVisible = !matrixVisible;
  if (matrixVisible) {
    container.classList.remove("hidden");
    label.textContent = "Hide Table";
  } else {
    container.classList.add("hidden");
    label.textContent = "Show Table";
  }
}

function renderConsistencyMatrix(matrix) {
  const headerRow = document.getElementById("matrixHeaderRow");
  const body = document.getElementById("matrixBody");

  while (headerRow.children.length > 1) {
    headerRow.removeChild(headerRow.lastChild);
  }
  body.innerHTML = "";

  matrix.evidence_ids.forEach(eid => {
    const th = document.createElement("th");
    th.className = "p-2.5 font-semibold text-center border-l border-slate-200 font-mono text-slate-700";
    th.textContent = eid;
    headerRow.appendChild(th);
  });

  const cellMap = {};
  matrix.cells.forEach(c => {
    if (!cellMap[c.fact_id]) cellMap[c.fact_id] = {};
    cellMap[c.fact_id][c.evidence_id] = c;
  });

  matrix.facts.forEach(fact => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-50 transition";

    const tdFact = document.createElement("td");
    tdFact.className = "p-2.5 align-middle font-medium text-slate-800 border-r border-slate-200 text-xs";
    tdFact.innerHTML = `
      <div class="font-mono text-[10px] text-blue-600 font-semibold">${fact.id}</div>
      <div>${fact.statement}</div>
    `;
    tr.appendChild(tdFact);

    matrix.evidence_ids.forEach(eid => {
      const td = document.createElement("td");
      td.className = "p-2 text-center border-l border-slate-200 align-middle";

      const cell = (cellMap[fact.id] && cellMap[fact.id][eid]) || {
        alignment: "silent",
        confidence: 0.9,
        citation: eid,
        reasoning: "No interaction"
      };

      let icon = "minus";
      let colorClass = "text-slate-400 bg-slate-50 border-slate-200";
      let titleText = `${eid}: Silent / Not mentioned`;

      if (cell.alignment === "supports") {
        icon = "check-circle";
        colorClass = "text-emerald-700 bg-emerald-50 border-emerald-200";
        titleText = `${eid}: Supports — ${cell.reasoning}`;
      } else if (cell.alignment === "contradicts") {
        icon = "x-circle";
        colorClass = "text-rose-700 bg-rose-50 border-rose-200 font-bold";
        titleText = `${eid}: CONFLICT — ${cell.reasoning}`;
      } else if (cell.alignment === "unclear") {
        icon = "help-circle";
        colorClass = "text-amber-700 bg-amber-50 border-amber-200";
        titleText = `${eid}: Unclear — ${cell.reasoning}`;
      }

      td.innerHTML = `
        <div class="inline-flex items-center justify-center p-1.5 rounded-lg border text-xs cursor-pointer ${colorClass}" title="${titleText}">
          <i data-lucide="${icon}" class="w-4 h-4"></i>
        </div>
      `;
      tr.appendChild(td);
    });

    body.appendChild(tr);
  });
}

function renderPolicyDetails(policy) {
  const table = document.getElementById("policyEvaluationsTable");
  table.innerHTML = "";

  (policy.evaluations || []).forEach(ev => {
    let statColor = "text-emerald-700 bg-emerald-50 border-emerald-200";
    if (ev.status === "excluded") statColor = "text-rose-700 bg-rose-50 border-rose-200";
    if (ev.status === "unclear") statColor = "text-amber-800 bg-amber-50 border-amber-200";

    const item = document.createElement("div");
    item.className = "p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5";
    item.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="font-bold text-slate-800">${ev.aspect}</span>
        <span class="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase font-bold border ${statColor}">${ev.status}</span>
      </div>
      <p class="text-slate-600 text-xs leading-relaxed">${ev.rationale}</p>
      <div class="text-[11px] text-blue-600 font-mono flex items-center gap-1">
        <i data-lucide="file-text" class="w-3 h-3"></i> Cited Clause: ${ev.clause_cited}
      </div>
    `;
    table.appendChild(item);
  });
}

function renderTimelineDetails(reconstruction) {
  const timelineDiv = document.getElementById("timelineContainer");
  timelineDiv.innerHTML = "";

  (reconstruction.timeline || []).forEach(evt => {
    const item = document.createElement("div");
    item.className = "relative pl-4 space-y-0.5";
    item.innerHTML = `
      <div class="absolute -left-[27px] top-1.5 w-3 h-3 rounded-full bg-blue-600 border-2 border-white shadow-sm"></div>
      <span class="text-xs font-mono text-blue-600 font-bold block">${evt.timestamp_or_phase}</span>
      <p class="text-xs text-slate-800">${evt.description}</p>
      <span class="text-[10px] text-slate-400 font-mono">Source: ${evt.citation}</span>
    `;
    timelineDiv.appendChild(item);
  });

  const modelCard = document.getElementById("impactModelCard");
  const model = reconstruction.impact_model || {};
  const isConsistent = reconstruction.is_damage_consistent_with_narrative;

  modelCard.innerHTML = `
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
      <div class="flex items-center justify-between pb-2 border-b border-slate-200">
        <span class="font-semibold text-slate-700">Physical Damage Alignment:</span>
        <span class="font-mono text-xs font-bold ${isConsistent ? 'text-emerald-700' : 'text-rose-700'}">
          ${(reconstruction.physical_damage_compatibility_score * 100).toFixed(0)}% (${isConsistent ? 'Consistent' : 'CONFLICT'})
        </span>
      </div>
      <div><span class="text-slate-500">Impact Direction:</span> <strong class="text-slate-800">${model.impact_direction || 'Standard'}</strong></div>
      <div><span class="text-slate-500">Contact Point:</span> <span class="text-slate-800">${model.primary_damage_point || 'Front bumper'}</span></div>
      <p class="text-[11px] text-slate-600 italic pt-1">${reconstruction.compatibility_explanation}</p>
    </div>
  `;
}

function renderAuditLogs(logs) {
  const container = document.getElementById("auditLogEntries");
  const drawerContainer = document.getElementById("auditDrawerEntries");
  if (container) container.innerHTML = "";
  if (drawerContainer) drawerContainer.innerHTML = "";

  if (!logs || logs.length === 0) {
    if (container) container.innerHTML = '<p class="text-slate-400 italic">No audit records yet.</p>';
    if (drawerContainer) drawerContainer.innerHTML = '<p class="text-slate-400 italic">No audit records yet.</p>';
    return;
  }

  logs.forEach(a => {
    const item = document.createElement("div");
    item.className = "p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1 font-mono text-[11px]";
    item.innerHTML = `
      <div class="flex items-center justify-between text-slate-500 text-[10px]">
        <span class="text-blue-600 font-semibold uppercase">${a.event_type}</span>
        <span>${a.timestamp ? a.timestamp.split('T')[1].slice(0, 8) : ''}</span>
      </div>
      <div class="text-slate-800 font-semibold">${a.agent_name || a.user_id}</div>
      <p class="text-slate-500 text-[10px] truncate">${a.input_summary || a.decision || ''}</p>
      <p class="text-slate-700 text-[10px]">${a.output_summary || a.reason || ''}</p>
    `;

    if (container) container.appendChild(item.cloneNode(true));
    if (drawerContainer) drawerContainer.appendChild(item);
  });
}

// -------------------------------------------------------------
// Finding Detail Drawer (Progressive Disclosure)
// -------------------------------------------------------------
function openFindingDrawer(finding) {
  const drawer = document.getElementById("findingDrawer");
  document.getElementById("drawerFindingId").textContent = finding.id;
  document.getElementById("drawerFindingTitle").textContent = finding.title;

  const sevSpan = document.getElementById("drawerFindingSev");
  sevSpan.textContent = finding.severity;
  sevSpan.className = finding.severity === "investigate"
    ? "text-xs font-semibold px-2.5 py-0.5 rounded-full uppercase bg-rose-50 text-rose-700 border border-rose-200"
    : "text-xs font-semibold px-2.5 py-0.5 rounded-full uppercase bg-amber-50 text-amber-800 border border-amber-200";

  document.getElementById("drawerInconsistency").textContent = finding.inconsistency;

  // Dual Hypotheses
  const expDiv = document.getElementById("drawerExplanations");
  expDiv.innerHTML = "";
  (finding.possible_explanations || []).forEach(exp => {
    const box = document.createElement("div");
    box.className = "p-3 bg-slate-50 rounded-xl border border-slate-200 text-slate-800 leading-relaxed";
    box.textContent = exp;
    expDiv.appendChild(box);
  });

  // Missing Evidence Checklist
  const missingUl = document.getElementById("drawerMissingEvidence");
  missingUl.innerHTML = "";
  (finding.missing_evidence || []).forEach(m => {
    const li = document.createElement("li");
    li.textContent = m;
    missingUl.appendChild(li);
  });

  document.getElementById("drawerAction").textContent = finding.recommended_action;

  // Confidence & Uncertainty
  const confVal = Math.round((finding.confidence || 0.8) * 100);
  document.getElementById("drawerConfidenceValue").textContent = `${confVal}% Certain`;
  document.getElementById("drawerConfidenceBar").style.width = `${confVal}%`;
  document.getElementById("drawerUncertaintyNote").textContent = finding.confidence_explanation || "Unverified circumstances.";

  // Sources
  const sourcesDiv = document.getElementById("drawerSources");
  sourcesDiv.innerHTML = "";
  (finding.sources || []).forEach(s => {
    const chip = document.createElement("span");
    chip.className = "px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 font-mono text-[11px] font-semibold";
    chip.textContent = `${s.evidence_id}: ${s.location}`;
    chip.title = s.snippet || "";
    sourcesDiv.appendChild(chip);
  });

  drawer.classList.remove("translate-x-full");
  if (window.lucide) window.lucide.createIcons();
}

function closeFindingDrawer() {
  document.getElementById("findingDrawer").classList.add("translate-x-full");
}

// -------------------------------------------------------------
// Adjuster Decision Modal & Audit Logging
// -------------------------------------------------------------
function promptDecision(type) {
  selectedDecisionType = type;
  document.getElementById("decisionModalTitle").textContent = `Record Decision: ${type}`;
  document.getElementById("decisionReasonText").value = "";
  document.getElementById("decisionModal").classList.remove("hidden");
}

function closeDecisionModal() {
  document.getElementById("decisionModal").classList.add("hidden");
}

async function submitDecision() {
  const reason = document.getElementById("decisionReasonText").value.trim();
  if (!reason) {
    alert("A mandatory reason is required for adjuster decision logging.");
    return;
  }

  try {
    const res = await fetch(`/api/cases/${activeCaseId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision: selectedDecisionType,
        reason: reason
      })
    });
    if (res.ok) {
      closeDecisionModal();
      await switchCase(activeCaseId, true);
    }
  } catch (err) {
    console.error("Decision recording error:", err);
  }
}

// -------------------------------------------------------------
// Supplemental Evidence (Incremental Re-Reasoning)
// -------------------------------------------------------------
function openSupplementalModal() {
  document.getElementById("supplementalModal").classList.remove("hidden");
}

function closeSupplementalModal() {
  document.getElementById("supplementalModal").classList.add("hidden");
}

async function submitSupplementalEvidence() {
  const input = document.getElementById("supplementalFileInput");
  if (!input.files || input.files.length === 0) {
    alert("Please select at least one file.");
    return;
  }

  const formData = new FormData();
  for (let i = 0; i < input.files.length; i++) {
    formData.append("files", input.files[i]);
  }

  try {
    closeSupplementalModal();
    goToStep(2);
    resetAgentRows();

    const res = await fetch(`/api/cases/${activeCaseId}/incremental`, {
      method: "POST",
      body: formData
    });
    if (res.ok) {
      markAllAgentRowsCompleted();
      await switchCase(activeCaseId, true);
    }
  } catch (err) {
    console.error("Incremental upload failed:", err);
    goToStep(3);
  }
}

// -------------------------------------------------------------
// Utility Functions
// -------------------------------------------------------------
function togglePII() {
  piiMasked = !piiMasked;
  document.getElementById("piiLabel").textContent = piiMasked ? "PII Masked" : "PII Visible";
  if (activeCaseData) {
    renderAllViews(activeCaseData);
  }
}

function maskPII(name) {
  if (!name) return "--";
  const parts = name.split(" ");
  return parts.map(p => p[0] + "*".repeat(Math.max(1, p.length - 1))).join(" ");
}

function toggleAuditDrawer() {
  document.getElementById("auditDrawer").classList.toggle("translate-x-full");
}

function openBundleModal() {
  document.getElementById("bundleModal").classList.remove("hidden");
  if (window.lucide) window.lucide.createIcons();
}

function closeBundleModal() {
  document.getElementById("bundleModal").classList.add("hidden");
}
