/* ============================================================
   SMART BLOOD DONATION MANAGEMENT SYSTEM — script.js
   ============================================================ */

// ─── TOAST ───────────────────────────────────────────────────
function showToast(msg, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  const icons = { success: "✅", error: "❌", warning: "⚠️" };
  t.innerHTML = `<span>${icons[type] || "ℹ️"}</span><span>${msg}</span>`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity 0.4s"; setTimeout(() => t.remove(), 400); }, 3500);
}

// ─── SIDEBAR ─────────────────────────────────────────────────
function toggleSidebar() {
  const sidebar  = document.getElementById("sidebar");
  const overlay  = document.getElementById("sidebar-overlay");
  if (!sidebar) return;
  sidebar.classList.toggle("open");
  if (overlay) overlay.classList.toggle("show");
}

document.addEventListener("click", function (e) {
  const overlay = document.getElementById("sidebar-overlay");
  if (overlay && overlay.classList.contains("show") && e.target === overlay) {
    toggleSidebar();
  }
});

// ─── PASSWORD TOGGLE ─────────────────────────────────────────
function togglePw(inputId, iconId) {
  const inp  = document.getElementById(inputId);
  const icon = document.getElementById(iconId);
  if (!inp) return;
  if (inp.type === "password") {
    inp.type = "text";
    if (icon) { icon.classList.remove("fa-eye"); icon.classList.add("fa-eye-slash"); }
  } else {
    inp.type = "password";
    if (icon) { icon.classList.remove("fa-eye-slash"); icon.classList.add("fa-eye"); }
  }
}

// ─── SIGNUP ──────────────────────────────────────────────────
async function handleSignup(e) {
  e.preventDefault();
  const msg = document.getElementById("signupMsg");
  const btn = document.getElementById("signupBtn");

  const phoneDigits = document.getElementById("su-phone-digits")?.value.trim() || "";
  const phone = phoneDigits ? "+91" + phoneDigits : "";

  const payload = {
    first_name:  document.getElementById("su-first")?.value.trim(),
    middle_name: document.getElementById("su-middle")?.value.trim() || "",
    last_name:   document.getElementById("su-last")?.value.trim(),
    username:    document.getElementById("su-username")?.value.trim(),
    email:       document.getElementById("su-email")?.value.trim(),
    phone:       phone,
    blood_group: document.getElementById("su-blood")?.value,
    city:        document.getElementById("su-city")?.value.trim(),
    password:    document.getElementById("su-password")?.value,
    confirm:     document.getElementById("su-confirm")?.value,
  };

  if (!payload.first_name || !payload.last_name || !payload.username || !payload.email || !payload.phone || !payload.city || !payload.password) {
    setMsg(msg, "Please fill all required fields", "error"); return;
  }
  if (payload.password !== payload.confirm) {
    setMsg(msg, "Passwords do not match", "error"); return;
  }

  btn.disabled = true; btn.innerHTML = `<i class="fa fa-spinner fa-spin"></i> Registering...`;
  try {
    const res  = await fetch("/api/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json();
    setMsg(msg, data.message, data.success ? "success" : "error");
    if (data.success) setTimeout(() => window.location.href = "/signin?from=signup", 1600);
  } catch { setMsg(msg, "Network error. Try again.", "error"); }
  finally { btn.disabled = false; btn.innerHTML = `<i class="fa fa-user-plus"></i> Create Donor Account`; }
}

// ─── LOGIN ───────────────────────────────────────────────────
async function handleLogin(e) {
  e.preventDefault();
  const msg = document.getElementById("loginMsg");
  const btn = document.getElementById("loginBtn");

  const payload = {
    username: document.getElementById("li-username")?.value.trim(),
    password: document.getElementById("li-password")?.value,
  };

  if (!payload.username || !payload.password) {
    setMsg(msg, "Please enter username and password", "error"); return;
  }

  btn.disabled = true; btn.textContent = "Signing in...";
  try {
    const res  = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    setMsg(msg, data.message, data.success ? "success" : "error");
    if (data.success) {
      // Store user profile in sessionStorage for immediate use on dashboard
      if (data.user) sessionStorage.setItem("sbdms_user", JSON.stringify(data.user));
      // Redirect to admin panel if admin, otherwise dashboard
      const target = data.redirect_to || "/dashboard";
      setTimeout(() => window.location.href = target, 1400);
    } else if (data.redirect_to === "/admin-login") {
      // Admin account tried to log in via user portal — guide them to the right place
      setMsg(msg, data.message, "error");
      setTimeout(() => window.location.href = "/admin-login", 2200);
    }
  } catch { setMsg(msg, "Network error. Try again.", "error"); }
  finally { btn.disabled = false; btn.textContent = "Sign In"; }
}

function setMsg(el, text, type) {
  if (!el) return;
  el.textContent = text;
  el.className = "msg-box " + (type === "success" ? "msg-success" : "msg-error");
}

// ─── DASHBOARD ───────────────────────────────────────────────
async function loadDashboardStats() {
  try {
    const res  = await fetch("/api/dashboard/stats");
    if (!res.ok) { console.error("Stats API error:", res.status); return; }
    const data = await res.json();
    setText("stat-units",    data.total_units   ?? "—");
    setText("stat-donors",   data.total_donors  ?? "—");
    setText("stat-avail",    data.available_donors ?? "—");
    setText("stat-emerg",    data.active_emergencies ?? "—");
    setText("stat-txn",      data.total_transactions ?? "—");
    const rev = data.total_revenue ?? 0;
    setText("stat-revenue",  "₹" + Number(rev).toLocaleString("en-IN"));
    // Show pending payments count if element exists
    if (data.pending_payments > 0) {
      const el = document.getElementById("stat-pending");
      if (el) el.textContent = data.pending_payments;
    }
  } catch (err) { console.error("Stats load failed", err); }
}

// ─── LIVE BLOOD DISTRIBUTION CHART ───────────────────────────
let bloodDistChart = null;

async function loadBloodDistributionChart(city) {
  const canvas  = document.getElementById("bloodDistChart");
  const loading = document.getElementById("chart-loading");
  if (!canvas) return;

  if (loading) loading.style.display = "block";
  canvas.style.display = "none";

  try {
    const cityParam = city || document.getElementById("chart-city-filter")?.value || "";
    const url  = cityParam
      ? `/api/inventory/stats?city=${encodeURIComponent(cityParam)}`
      : "/api/inventory/stats";
    const res  = await fetch(url);
    const data = await res.json();

    // Aggregate units per blood group across all returned cities
    const grouped = {};
    for (const item of data.items) {
      grouped[item.blood_group] = (grouped[item.blood_group] || 0) + item.units;
    }

    const labels = ["A+","A-","B+","B-","O+","O-","AB+","AB-"];
    const values = labels.map(bg => grouped[bg] || 0);

    // Colour: crimson for critical (<5), amber for low (<10), teal for ok
    const bgColors = values.map(v =>
      v < 5  ? "rgba(155,28,28,0.85)"  :
      v < 10 ? "rgba(217,119,6,0.85)"  :
               "rgba(13,148,136,0.85)"
    );
    const borderColors = values.map(v =>
      v < 5  ? "#9b1c1c" : v < 10 ? "#d97706" : "#0d9488"
    );

    if (bloodDistChart) bloodDistChart.destroy();

    bloodDistChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Units Available",
          data: values,
          backgroundColor: bgColors,
          borderColor: borderColors,
          borderWidth: 2,
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.parsed.y} unit(s)`,
              afterLabel: ctx => {
                const v = ctx.parsed.y;
                return v < 5 ? "⚠️ Critical" : v < 10 ? "⚡ Low" : "✅ OK";
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 13, weight: "700" }, color: "#334155" }
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(0,0,0,0.05)" },
            ticks: { font: { size: 12 }, color: "#64748b", stepSize: 5 },
            title: { display: true, text: "Units", font: { size: 12 }, color: "#64748b" }
          }
        }
      }
    });

    if (loading) loading.style.display = "none";
    canvas.style.display = "block";

    // Also refresh the stat-units total
    setText("stat-units", data.total_units);

  } catch (err) {
    console.error("Chart load failed", err);
    if (loading) loading.style.display = "none";
  }
}

async function loadInventoryGauges() {
  const grid = document.getElementById("inv-gauge-grid");
  if (!grid) return;
  try {
    const res  = await fetch("/api/dashboard/inventory_preview");
    const data = await res.json();
    grid.innerHTML = data.map(i => `
      <a href="/inventory" class="inv-gauge ${i.status}" title="${i.blood_group}: ${i.units} units">
        <div class="ig-label">${i.blood_group}</div>
        <div class="ig-bar-track">
          <div class="ig-bar-fill" style="width:${i.pct}%"></div>
        </div>
        <div class="ig-units">${i.units} u</div>
      </a>`).join("");
  } catch { if (grid) grid.innerHTML = `<p style="color:var(--muted);font-size:13px;grid-column:1/-1">Failed to load</p>`; }
}

async function loadRecentOrders() {
  const box = document.getElementById("recent-orders-box");
  if (!box) return;
  try {
    const res  = await fetch("/api/dashboard/recent_orders");
    const data = await res.json();
    if (!data.length) { box.innerHTML = `<p style="color:var(--muted);font-size:13px;text-align:center;padding:16px">No transactions yet</p>`; return; }
    box.innerHTML = data.map(t => `
      <a href="/payment" class="recent-order-row" style="text-decoration:none">
        <span class="blood-badge" style="flex-shrink:0">${t.blood_group}</span>
        <div style="flex:1;min-width:0">
          <div class="ro-patient">${t.patient_name}</div>
          <div class="ro-meta">${t.receipt_no} · ${t.date}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div class="ro-amount">₹${t.total.toLocaleString("en-IN")}</div>
          <span class="badge badge-${t.status}" style="font-size:10px">${t.status}</span>
        </div>
      </a>`).join("");
  } catch { box.innerHTML = `<p style="color:var(--muted);font-size:13px;text-align:center;padding:16px">Failed to load</p>`; }
}

async function loadRecentEmergencies() {
  const container = document.getElementById("recent-emergencies");
  if (!container) return;
  try {
    const res  = await fetch("/api/emergency/list");
    const list = await res.json();
    if (!list.length) { container.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">No emergency requests yet</p>'; return; }
    container.innerHTML = list.slice(0, 5).map(r => `
      <div class="emergency-item ${r.status}">
        <div class="ei-blood">${r.blood_group}</div>
        <div class="ei-info">
          <strong>${r.location} — ${r.units} unit(s)</strong>
          <span>${r.requested_at} ${r.donor_name ? "· Donor: " + r.donor_name : ""}</span>
        </div>
        <span class="badge badge-${r.status}">${r.status}</span>
      </div>`).join("");
  } catch (err) { container.innerHTML = '<p style="color:var(--muted)">Failed to load</p>'; }
}

// ─── EMERGENCY MODAL ─────────────────────────────────────────
function openEmergencyModal() {
  const modal = document.getElementById("emergency-modal");
  if (modal) modal.classList.add("show");
  resetEmergencyModal();
}

function closeEmergencyModal() {
  const modal = document.getElementById("emergency-modal");
  if (modal) modal.classList.remove("show");
}

function resetEmergencyModal() {
  // Clean up any active delivery map
  if (_deliveryMap) {
    try { _deliveryMap.remove(); } catch {}
    _deliveryMap     = null;
    _ambulanceMarker = null;
    _deliveryBankLL  = null;
    _deliveryDestLL  = null;
  }
  if (_autoSimTimer) { clearInterval(_autoSimTimer); _autoSimTimer = null; }
  const body = document.getElementById("modal-body");
  if (!body) return;

  // Blood group prices (₹1500 standard, ₹1800 for O+/O-, ₹2000 for AB+/AB-)
  const BG_PRICES = {
    "A+":1500,"A-":1500,"B+":1500,"B-":1500,
    "O+":1800,"O-":1800,"AB+":2000,"AB-":2000
  };

  body.innerHTML = `
    <div class="field-group">
      <label>Blood Group <span style="color:#dc2626">*</span></label>
      <select id="em-blood" onchange="updateEmSubtotal()">
        <option value="">Select Blood Group</option>
        ${["A+","B+","O+","AB+","A-","B-","O-","AB-"].map(b =>
          `<option value="${b}">${b} — ₹${BG_PRICES[b].toLocaleString("en-IN")} per Bag</option>`
        ).join("")}
      </select>
    </div>
    <div class="field-group">
      <label>City / Location <span style="color:#dc2626">*</span> <span style="font-size:11px;color:var(--teal)">(donors must be in this city)</span></label>
      <select id="em-location">
        <option value="">Select Location</option>
        <option>Virar</option><option>Nalasopara</option><option>Vasai</option>
        <option>Naigaon</option><option>Bhayander</option><option>Mira Road</option>
        <option>Dahisar</option><option>Borivali</option><option>Kandivali</option>
        <option>Malad</option>
      </select>
    </div>

    <div class="field-group">
      <label>Patient Name <span style="color:#dc2626">*</span> <span style="font-size:10px;color:var(--muted)">(alphabets only)</span></label>
      <input type="text" id="em-patient"
             placeholder="Full name of the patient"
             oninput="validateEmPatient(this)">
      <div id="em-patient-hint" style="font-size:11px;color:var(--muted);margin-top:3px">
        Letters and spaces only
      </div>
    </div>

    <div class="field-group">
      <label>Patient Phone <span style="color:#dc2626">*</span> <span style="font-size:10px;color:var(--muted)">(+91, 10 digits)</span></label>
      <div style="position:relative">
        <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);
                     font-size:14px;font-weight:600;color:var(--slate-600);
                     pointer-events:none;user-select:none">+91</span>
        <input type="tel" id="em-phone"
               placeholder="9XXXXXXXXX"
               maxlength="10"
               inputmode="numeric"
               style="padding-left:48px !important"
               oninput="validateEmPhone(this)">
      </div>
      <div id="em-phone-hint" style="font-size:11px;color:var(--muted);margin-top:3px">
        Start with 9, 8, 7, or 6 — 10 digits total
      </div>
    </div>

    <div class="field-group">
      <label>Detailed Address <span style="color:#dc2626">*</span></label>
      <input type="text" id="em-address" placeholder="Hospital name, ward, street, landmark...">
    </div>

    <div class="field-group">
      <label>Units Required <span style="color:#dc2626">*</span> <span style="font-size:11px;color:var(--muted)">(max 15)</span></label>
      <input type="number" id="em-units" value="1" min="1" max="15"
             oninput="updateEmSubtotal()">
      <!-- Live subtotal -->
      <div id="em-subtotal" style="margin-top:8px;padding:10px 13px;
           background:var(--crimson-pale);border:1.5px solid var(--crimson-soft);
           border-radius:var(--radius);font-size:13px;font-weight:700;
           color:var(--crimson);display:none">
        <i class="fa fa-calculator"></i>
        Base Cost: <span id="em-subtotal-val">—</span>
        <span style="font-size:11px;font-weight:400;color:var(--muted);margin-left:6px">
          (+ distance charge added after delivery)
        </span>
      </div>
    </div>

    <div class="modal-actions">
      <button class="btn btn-red" onclick="submitEmergency()">
        <i class="fa fa-bolt"></i> Raise Emergency Request
      </button>
      <button class="btn btn-gray" onclick="closeEmergencyModal()">Cancel</button>
    </div>`;
}

// ── Live subtotal: bags × price ──
function updateEmSubtotal() {
  const BG_PRICES = {
    "A+":1500,"A-":1500,"B+":1500,"B-":1500,
    "O+":1800,"O-":1800,"AB+":2000,"AB-":2000
  };
  const bg    = document.getElementById("em-blood")?.value || "";
  const units = parseInt(document.getElementById("em-units")?.value || 1);
  const box   = document.getElementById("em-subtotal");
  const val   = document.getElementById("em-subtotal-val");
  if (!bg || !box || !val) { if (box) box.style.display = "none"; return; }
  const price    = BG_PRICES[bg] || 1500;
  const subtotal = units * price;
  val.textContent = `${units} bag(s) × ₹${price.toLocaleString("en-IN")} = ₹${subtotal.toLocaleString("en-IN")}`;
  box.style.display = "block";
}

// ── Real-time: patient name — alphabets + spaces only ──
function validateEmPatient(inp) {
  const hint = document.getElementById("em-patient-hint");
  // Strip digits and special characters in real-time
  inp.value = inp.value.replace(/[^A-Za-z\s]/g, "");
  const val = inp.value.trim();
  if (!val) {
    hint.textContent = "Letters and spaces only";
    hint.style.color = "var(--muted)";
  } else if (val.length < 2) {
    hint.textContent = "Name too short";
    hint.style.color = "var(--warning)";
  } else {
    hint.textContent = "✓ Valid name";
    hint.style.color = "var(--success)";
  }
}

// ── Real-time: phone — digits only, starts 9/8/7, exactly 10 ──
function validateEmPhone(inp) {
  const hint = document.getElementById("em-phone-hint");
  // Strip non-digits in real-time
  inp.value = inp.value.replace(/\D/g, "").slice(0, 10);
  const val = inp.value;
  if (!val) {
    hint.textContent = "Start with 9, 8, 7, or 6 — 10 digits total";
    hint.style.color = "var(--muted)";
  } else if (!/^[6987]/.test(val)) {
    hint.textContent = "✗ Must start with 9, 8, 7, or 6";
    hint.style.color = "var(--crimson)";
  } else if (val.length < 10) {
    hint.textContent = `${10 - val.length} more digit(s) needed`;
    hint.style.color = "var(--warning)";
  } else {
    hint.textContent = "✓ Valid number";
    hint.style.color = "var(--success)";
  }
}

async function submitEmergency() {
  const blood   = document.getElementById("em-blood")?.value;
  const loc     = document.getElementById("em-location")?.value;
  const patient = document.getElementById("em-patient")?.value.trim();
  const phone   = document.getElementById("em-phone")?.value.trim();
  const address = document.getElementById("em-address")?.value.trim();
  const units   = parseInt(document.getElementById("em-units")?.value || 1);

  if (!blood)   { showToast("Select a blood group", "warning"); return; }
  if (!loc)     { showToast("Select a location", "warning"); return; }

  // ── Patient name: alphabets only ──
  if (!patient) { showToast("Patient name is required", "warning"); return; }
  if (/[^A-Za-z\s]/.test(patient)) {
    showToast("Patient name must contain letters only — no numbers or symbols", "warning");
    return;
  }
  if (patient.length < 2) { showToast("Patient name is too short", "warning"); return; }

  // ── Phone: exactly 10 digits, starts with 9/8/7 ──
  if (!phone) { showToast("Patient phone number is required", "warning"); return; }
  if (!/^[6987]\d{9}$/.test(phone)) {
    showToast("Phone must be exactly 10 digits and start with 9, 8, 7, or 6", "warning");
    return;
  }
  const fullPhone = "+91" + phone;   // canonical E.164

  if (!address) { showToast("Detailed address is required", "warning"); return; }
  if (units < 1 || units > 15) { showToast("Units must be between 1 and 15", "warning"); return; }

  const body = document.getElementById("modal-body");

  body.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p style="font-weight:600;color:var(--slate-700);margin-top:8px">
        🔍 Step 1: Checking Inventory for <strong>${units} unit(s) of ${blood}</strong> in <strong>${loc}</strong>...
      </p>
    </div>`;

  try {
    const res  = await fetch("/api/emergency/request", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blood_group: blood, location: loc,
        patient_name: patient, receiver_phone: fullPhone,
        address, units
      })
    });
    const data = await res.json();

    if (!data.success) {
      body.innerHTML = `
        <div style="text-align:center;padding:20px">
          <div style="font-size:36px;margin-bottom:10px">⚠️</div>
          <p style="color:var(--crimson);font-weight:600">${data.message}</p>
          <button class="btn btn-gray" style="margin-top:14px;width:100%;justify-content:center"
                  onclick="resetEmergencyModal()">← Try Again</button>
        </div>`;
      return;
    }

    data.location = loc;
    data.address  = address;

    if (data.fulfillment !== "stock" && data.units_from_donor > 0) {
      body.innerHTML = `
        <div class="loading-state">
          <div class="spinner"></div>
          <p style="font-weight:600;color:var(--slate-700);margin-top:8px">
            ⚡ Step 2: Inventory short by <strong>${data.units_from_donor} unit(s)</strong>.
            Searching for local donors in <strong>${loc}</strong>...
          </p>
        </div>`;
      await new Promise(r => setTimeout(r, 900));
    }

    showEmergencyResult(data);
  } catch {
    body.innerHTML = `
      <div style="text-align:center;padding:20px">
        <p style="color:var(--crimson)">Request failed. Please try again.</p>
        <button class="btn btn-gray" style="margin-top:14px;width:100%;justify-content:center"
                onclick="resetEmergencyModal()">← Try Again</button>
      </div>`;
  }
}

function showEmergencyResult(data) {
  const body    = document.getElementById("modal-body");
  const donors  = data.donors || [];
  const primary = data.donor;
  const f       = data.fulfillment;   // "stock" | "mixed" | "donor" | "none"

  // ── Pipeline breakdown bar ──
  const pipelineSteps = [
    {
      icon: "🏥",
      label: "Inventory Check",
      detail: data.units_from_stock > 0
        ? `${data.units_from_stock} unit(s) from ${data.stock_available} available`
        : `0 units available in ${data.blood_group} stock`,
      done: true,
      ok: data.units_from_stock > 0
    },
    {
      icon: "👤",
      label: "Donor Search",
      detail: data.units_from_donor > 0
        ? (primary ? `${data.units_from_donor} unit(s) from ${primary.name}` : `${data.units_from_donor} unit(s) needed — no donor found`)
        : "Not required",
      done: f !== "stock",
      ok: f === "donor" || f === "mixed"
    },
    {
      icon: "✅",
      label: "Fulfillment",
      detail: data.can_fulfill ? data.pipeline_msg : "Cannot fulfill — request queued",
      done: true,
      ok: data.can_fulfill
    }
  ];

  const pipelineHtml = `
    <div style="margin-bottom:18px">
      ${pipelineSteps.map((s, i) => `
        <div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;
                    border-bottom:${i < 2 ? "1px solid var(--slate-100)" : "none"}">
          <div style="font-size:20px;flex-shrink:0;margin-top:2px">${s.icon}</div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:700;color:var(--slate-700)">${s.label}</div>
            <div style="font-size:12px;color:var(--muted);margin-top:2px">${s.detail}</div>
          </div>
          <div style="flex-shrink:0;font-size:18px">${s.done ? (s.ok ? "✅" : "⚠️") : "—"}</div>
        </div>`).join("")}
    </div>`;

  // ── Status banner ──
  const bannerBg    = data.can_fulfill ? "var(--teal-pale)"    : "var(--warning-pale)";
  const bannerColor = data.can_fulfill ? "var(--teal-dark)"    : "var(--warning)";
  const bannerIcon  = data.can_fulfill ? "✅" : "⏳";
  const bannerTitle = data.can_fulfill
    ? (f === "stock"  ? "Fulfilled from Inventory"
     : f === "mixed"  ? "Fulfilled: Inventory + Donor"
     : "Fulfilled by Local Donor")
    : "Request Queued — No Stock or Donor";

  const bannerHtml = `
    <div style="text-align:center;padding:14px 16px;background:${bannerBg};
                border-radius:var(--radius);margin-bottom:16px">
      <div style="font-size:32px;margin-bottom:6px">${bannerIcon}</div>
      <h4 style="color:${bannerColor};font-size:15px;font-weight:800;margin-bottom:4px">
        ${bannerTitle}
      </h4>
      <p style="color:var(--muted);font-size:12px">${data.pipeline_msg}</p>
    </div>`;

  // ── Donor cards (only shown when donor was needed) ──
  let donorHtml = "";
  if (donors.length > 0 && f !== "stock") {
    donorHtml = `
      <p style="font-size:11px;font-weight:700;color:var(--slate-500);
                text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">
        Local Donors Found (${donors.length})
      </p>
      <div class="donor-result-list">
        ${donors.map((d, i) => `
          <div class="donor-card ${i === 0 ? "primary" : ""}"
               onclick="selectDonorForDispatch(${JSON.stringify(d).replace(/"/g,"&quot;")})">
            <div class="dc-avatar">${d.name.charAt(0)}</div>
            <div class="dc-info">
              <strong>${d.name}</strong>
              <span>${d.city} · ${d.phone} · ${d.donations} donation(s)</span>
            </div>
            <div class="dc-badge">
              <span class="blood-badge">${d.blood_group}</span>
              ${d.exact_match ? `<br><span style="font-size:10px;color:var(--teal);font-weight:600;
                display:block;text-align:center;margin-top:3px">Exact</span>` : ""}
            </div>
          </div>`).join("")}
      </div>`;
  }

  // ── ETA / Bloodhound card ──
  let etaHtml = "";
  if (data.delivery && data.can_fulfill) {
    const dv = data.delivery;
    etaHtml = `
      <div style="background:var(--teal-pale);border:1.5px solid var(--teal-soft);
                  border-radius:var(--radius);padding:12px 14px;margin:12px 0">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <span style="font-size:20px">🚑</span>
          <div>
            <strong style="color:var(--teal-dark);font-size:13px">Bloodhound Assigned</strong>
            <div style="font-size:11px;color:var(--muted)">${dv.rider_name} · ${dv.rider_phone}</div>
          </div>
          <div style="margin-left:auto;text-align:right">
            <div style="font-size:18px;font-weight:800;color:var(--teal-dark)">${dv.eta_minutes} min</div>
            <div style="font-size:10px;color:var(--muted)">ETA</div>
          </div>
        </div>
        <div style="font-size:11.5px;color:var(--slate-600)">
          <i class="fa fa-hospital" style="color:var(--crimson);margin-right:4px"></i>
          Pickup: ${dv.pickup_bank}
        </div>
      </div>`;
  }

  // ── Single "Initiate Delivery" button replaces the old dual buttons ──
  let actionsHtml = "";
  if (data.can_fulfill) {
    const eruPayload = JSON.stringify({
      blood_group:  data.blood_group  || "",
      location:     data.location     || "",
      address:      data.address      || "",
      units:        data.bags         || 1,
      patient_name: data.patient_name || "",
      donor_name:   data.donor ? data.donor.name : ""
    }).replace(/"/g, "&quot;");

    // Nearby bank options (shown when local stock is insufficient)
    let nearbyHtml = "";
    if (data.nearby_options && data.nearby_options.length > 0) {
      nearbyHtml = `
        <div style="margin-bottom:14px">
          <p style="font-size:11px;font-weight:700;color:var(--slate-500);
                    text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">
            <i class="fa fa-map-marker-alt" style="color:var(--crimson)"></i>
            Nearby Banks with Stock
          </p>
          ${data.nearby_options.map(opt => {
            const optFee  = (opt.units * 50) + (opt.distance_km * 5) + 20;
            const canFull = opt.can_cover ? "✅ Full" : `⚠️ ${opt.units} unit(s)`;
            return `
            <div style="background:var(--slate-50);border:1.5px solid var(--slate-200);
                        border-radius:var(--radius);padding:10px 13px;margin-bottom:8px;
                        font-size:12.5px">
              <div style="display:flex;justify-content:space-between;align-items:center;
                          flex-wrap:wrap;gap:6px">
                <div>
                  <strong style="color:var(--slate-800)">${opt.city}</strong>
                  <span style="color:var(--muted);margin-left:6px">${opt.bank_name}</span>
                </div>
                <span style="font-size:11px;font-weight:700;
                             color:${opt.can_cover ? "var(--success)" : "var(--warning)"}">
                  ${canFull}
                </span>
              </div>
              <div style="display:flex;gap:14px;margin-top:5px;color:var(--slate-600)">
                <span>📍 ${opt.distance_km} km</span>
                <span>⏱ ~${opt.eta_minutes} min</span>
                <span>💰 Est. ₹${Number(optFee.toFixed(0)).toLocaleString("en-IN")}</span>
              </div>
            </div>`;
          }).join("")}
        </div>`;
    }

    actionsHtml = `
      ${nearbyHtml}
      <div style="display:flex;flex-direction:column;gap:8px;margin-top:14px">
        <button class="btn btn-red" id="initiate-delivery-btn"
                style="width:100%;justify-content:center;font-size:15px;padding:14px"
                onclick="initiateDelivery(${eruPayload})">
          <i class="fa fa-ambulance"></i>&nbsp; Initiate Delivery
        </button>
        <button class="btn btn-gray" style="width:100%;justify-content:center"
                onclick="closeEmergencyModal()">Close</button>
      </div>`;
  } else {
    actionsHtml = `
      <div style="display:flex;gap:8px;margin-top:14px">
        <button class="btn btn-outline" style="flex:1;justify-content:center"
                onclick="resetEmergencyModal()">← New Request</button>
        <button class="btn btn-gray" style="flex:1;justify-content:center"
                onclick="closeEmergencyModal()">Close</button>
      </div>`;
  }

  body.innerHTML = bannerHtml + pipelineHtml + donorHtml + etaHtml + actionsHtml;

  if (data.can_fulfill) {
    showToast(data.pipeline_msg, "success");
    loadDashboardStats();
    loadRecentEmergencies();
    if (data.delivery) showDeliveryNotification(data.delivery);
    refreshInventoryStats(data.location || "");

    // ── Auto-initiate delivery immediately ──
    if (data.can_fulfill) {
      const eruPayload = {
        blood_group:  data.blood_group  || "",
        location:     data.location     || "",
        address:      data.address      || "",
        units:        data.bags         || 1,
        patient_name: data.patient_name || "",
        donor_name:   data.donor ? data.donor.name : ""
      };
      // Small delay so the user sees the result screen first
      setTimeout(() => initiateDelivery(eruPayload), 1200);
    }
  } else {
    showToast("Request queued — no stock or donor available", "warning");
  }
}

// ─── ERU — UNIFIED INITIATE DELIVERY ────────────────────────
/**
 * Workflow:
 * 1. POST /api/eru/initiate → distance, eta_minutes (realistic), eta_seconds (demo)
 * 2. Show static "Expected by HH:MM" card — no fast-ticking timer
 * 3. "Simulate Rider Movement" button runs the ~30s demo animation
 * 4. On simulation complete → POST /api/eru/complete → receipt generated
 * 5. Pay Now button unlocks — redirect to /payment?receipt=...
 * 6. Inventory deducted only when payment is confirmed (pay_bill)
 */
async function initiateDelivery(payload) {
  const body = document.getElementById("modal-body");
  const btn  = document.getElementById("initiate-delivery-btn");
  if (btn) { btn.disabled = true; btn.innerHTML = `<i class="fa fa-spinner fa-spin"></i> Initiating…`; }

  let eruData;
  try {
    const res = await fetch("/api/eru/initiate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    eruData = await res.json();
    if (!eruData.success) {
      body.innerHTML = `<div style="text-align:center;padding:20px">
        <p style="color:var(--crimson);font-weight:600">${eruData.message}</p>
        <button class="btn btn-gray" style="margin-top:14px;width:100%;justify-content:center"
                onclick="resetEmergencyModal()">← Try Again</button></div>`;
      return;
    }
  } catch {
    body.innerHTML = `<div style="text-align:center;padding:20px">
      <p style="color:var(--crimson)">Network error. Please try again.</p>
      <button class="btn btn-gray" style="margin-top:14px;width:100%;justify-content:center"
              onclick="resetEmergencyModal()">← Try Again</button></div>`;
    return;
  }

  const { eru_id, eru_code, eta_minutes, eta_seconds, distance_km, delivery_fee } = eruData;

  // "Expected by" timestamp
  const expectedBy  = new Date(Date.now() + eta_minutes * 60 * 1000);
  const expectedStr = expectedBy.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

  // Look up coordinates for this city from the CITY_COORDS map
  const cityKey = (payload.location || "").trim();
  const CITY_COORDS_MAP = {
    "Virar":      [19.4588, 72.8110], "Nalasopara": [19.4209, 72.7996],
    "Vasai":      [19.3919, 72.8397], "Naigaon":    [19.3636, 72.8530],
    "Bhayandar":  [19.3000, 72.8500], "Mira Road":  [19.2812, 72.8726],
    "Dahisar":    [19.2490, 72.8560], "Borivali":   [19.2307, 72.8567],
    "Kandivali":  [19.2043, 72.8490], "Malad":      [19.1863, 72.8484]
  };
  const CITY_DEST_MAP = {
    "Virar":      [19.4650, 72.8050], "Nalasopara": [19.4250, 72.8050],
    "Vasai":      [19.3950, 72.8450], "Naigaon":    [19.3680, 72.8580],
    "Bhayandar":  [19.3050, 72.8550], "Mira Road":  [19.2850, 72.8780],
    "Dahisar":    [19.2530, 72.8600], "Borivali":   [19.2350, 72.8620],
    "Kandivali":  [19.2080, 72.8540], "Malad":      [19.1900, 72.8530]
  };
  const bankLatLng = CITY_COORDS_MAP[cityKey] || [19.2307, 72.8567];
  const destLatLng = CITY_DEST_MAP[cityKey]   || [19.2350, 72.8620];

  body.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;
                margin-bottom:14px;flex-wrap:wrap;gap:8px">
      <div style="font-size:13px;font-weight:700;color:var(--teal-dark);
                  background:var(--teal-pale);border-radius:var(--radius);padding:8px 14px">
        ERU: <strong>${eru_code}</strong>
      </div>
      <div style="font-size:12px;color:var(--slate-600);background:var(--slate-100);
                  border-radius:var(--radius);padding:8px 14px;display:flex;gap:14px">
        <span>📍 <strong>${distance_km} km</strong></span>
        <span>💰 ₹<strong>${Number(delivery_fee).toLocaleString("en-IN")}</strong></span>
      </div>
    </div>

    <!-- Realistic ETA -->
    <div style="background:var(--crimson-pale);border:1.5px solid var(--crimson-soft);
                border-radius:var(--radius);padding:16px;text-align:center;margin-bottom:14px">
      <div style="font-size:28px;font-weight:800;color:var(--crimson);margin-bottom:4px">
        🚑 ${eta_minutes} Minutes
      </div>
      <div style="font-size:13px;color:var(--slate-700);font-weight:600">
        Estimated Arrival · ${distance_km} km at 25 km/h
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px">
        Expected by <strong>${expectedStr}</strong> &nbsp;·&nbsp; Inform your doctor now
      </div>
    </div>

    <!-- Status breadcrumb -->
    <div style="display:flex;align-items:center;justify-content:center;
                gap:6px;margin-bottom:14px;font-size:12px;font-weight:700">
      <span id="step-pickup" style="color:var(--crimson)">🏥 Picked Up</span>
      <span style="color:var(--slate-300)">──────</span>
      <span id="step-transit" style="color:var(--slate-300)">🚑 In Transit</span>
      <span style="color:var(--slate-300)">──────</span>
      <span id="step-delivered" style="color:var(--slate-300)">✅ Delivered</span>
    </div>

    <div class="progress-track" style="margin-bottom:8px">
      <div class="progress-fill" id="del-fill" style="width:0%"></div>
      <div class="ambulance-icon" id="del-amb" style="left:0%">🚑</div>
    </div>
    <div class="track-labels"><span>🏥 Blood Bank</span><span>🏨 Hospital</span></div>

    <p id="del-status" style="text-align:center;color:var(--muted);font-size:13px;
                               margin-top:10px;font-weight:600">
      Rider dispatched — awaiting movement update
    </p>

    <!-- ── Live Delivery Map ── -->
    <div style="margin-top:16px;border:1.5px solid var(--slate-200);border-radius:var(--radius);overflow:hidden">
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:10px 14px;background:var(--slate-50);border-bottom:1px solid var(--slate-200)">
        <span style="font-size:13px;font-weight:700;color:var(--slate-700)">
          <i class="fa fa-map-location-dot" style="color:#e11d48;margin-right:6px"></i>Live Delivery Map
        </span>
        <button class="btn btn-sm btn-outline" onclick="_refreshDeliveryMap()" style="padding:4px 10px;font-size:11px">
          <i class="fa fa-rotate-right"></i> Refresh
        </button>
      </div>
      <div id="eru-live-map" style="height:260px;width:100%"></div>
      <div style="padding:7px 14px;background:var(--slate-50);border-top:1px solid var(--slate-100);
                  font-size:11px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap">
        <span><i class="fa fa-circle" style="color:#e11d48"></i> Blood Bank</span>
        <span><i class="fa fa-circle" style="color:#16a34a"></i> Hospital</span>
        <span>🚑 Ambulance in transit</span>
      </div>
    </div>
`;

  // ── Initialise Leaflet map after HTML is injected ──
  // Small delay so the div is in the DOM and has dimensions
  setTimeout(() => {
    _initDeliveryMap(bankLatLng, destLatLng, eru_code);
  }, 150);

  // ── Auto-start the real-time simulation immediately ──
  _autoSimulate(eru_id, eru_code, eta_seconds);
}

// ── Delivery map state ──
let _deliveryMap      = null;
let _ambulanceMarker  = null;
let _deliveryBankLL   = null;
let _deliveryDestLL   = null;

function _initDeliveryMap(bankLatLng, destLatLng, eruCode) {
  // Destroy previous map instance if any
  if (_deliveryMap) {
    try { _deliveryMap.remove(); } catch {}
    _deliveryMap     = null;
    _ambulanceMarker = null;
  }
  _deliveryBankLL = bankLatLng;
  _deliveryDestLL = destLatLng;

  const mapEl = document.getElementById("eru-live-map");
  if (!mapEl || typeof L === "undefined") return;

  // Centre between bank and destination
  const midLat = (bankLatLng[0] + destLatLng[0]) / 2;
  const midLng = (bankLatLng[1] + destLatLng[1]) / 2;

  _deliveryMap = L.map("eru-live-map", { zoomControl: true, attributionControl: true })
    .setView([midLat, midLng], 14);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18
  }).addTo(_deliveryMap);

  // Blood bank marker (red)
  const bankIcon = L.divIcon({
    html: `<div style="background:#e11d48;color:white;border-radius:50%;
                       width:32px;height:32px;display:flex;align-items:center;
                       justify-content:center;font-size:15px;
                       box-shadow:0 2px 8px rgba(225,29,72,0.5)">🏥</div>`,
    className: "", iconSize: [32, 32], iconAnchor: [16, 16]
  });
  L.marker(bankLatLng, { icon: bankIcon })
    .addTo(_deliveryMap)
    .bindPopup(`<strong>Blood Bank</strong><br>Dispatching ${eruCode}`);

  // Hospital marker (green)
  const hospIcon = L.divIcon({
    html: `<div style="background:#16a34a;color:white;border-radius:50%;
                       width:32px;height:32px;display:flex;align-items:center;
                       justify-content:center;font-size:15px;
                       box-shadow:0 2px 8px rgba(22,163,74,0.5)">🏨</div>`,
    className: "", iconSize: [32, 32], iconAnchor: [16, 16]
  });
  L.marker(destLatLng, { icon: hospIcon })
    .addTo(_deliveryMap)
    .bindPopup("<strong>Destination Hospital</strong>");

  // Route line (crimson dashed)
  L.polyline([bankLatLng, destLatLng], {
    color: "#e11d48", weight: 3, dashArray: "8 6", opacity: 0.7
  }).addTo(_deliveryMap);

  // Ambulance marker — starts at blood bank
  const ambIcon = L.divIcon({
    html: `<div id="map-amb-icon" style="font-size:26px;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.4));
                transition:none;transform:scaleX(-1)">🚑</div>`,
    className: "", iconSize: [32, 32], iconAnchor: [16, 16]
  });
  _ambulanceMarker = L.marker(bankLatLng, { icon: ambIcon, zIndexOffset: 1000 })
    .addTo(_deliveryMap)
    .bindPopup(`<strong>Ambulance</strong><br>${eruCode} — In Transit`);

  // Force map to render correctly inside modal
  setTimeout(() => { if (_deliveryMap) _deliveryMap.invalidateSize(); }, 250);
}

// ── Move ambulance marker on the map to the current simulation % ──
function _updateAmbulanceOnMap(pct) {
  if (!_ambulanceMarker || !_deliveryBankLL || !_deliveryDestLL) return;
  const t      = Math.min(pct / 100, 1);
  const newLat = _deliveryBankLL[0] + (_deliveryDestLL[0] - _deliveryBankLL[0]) * t;
  const newLng = _deliveryBankLL[1] + (_deliveryDestLL[1] - _deliveryBankLL[1]) * t;
  _ambulanceMarker.setLatLng([newLat, newLng]);
  // Keep map centred on ambulance
  if (_deliveryMap) _deliveryMap.panTo([newLat, newLng], { animate: true, duration: 0.4 });
}

// ── Refresh button handler ──
function _refreshDeliveryMap() {
  if (_deliveryMap) _deliveryMap.invalidateSize();
}

// ── Auto-simulation: runs at real speed (eta_seconds), updates UI ──
// Separate from simulateRiderMovement so Fast-Forward can override it
let _autoSimTimer = null;

function _autoSimulate(eruId, eruCode, etaSeconds) {
  if (_autoSimTimer) { clearInterval(_autoSimTimer); _autoSimTimer = null; }

  // Location waypoints shown as rider moves through the city
  const waypoints = [
    "Leaving blood bank…",
    "Passing main junction…",
    "Crossing railway station area…",
    "Entering residential zone…",
    "Approaching delivery address…",
    "Arriving at destination…"
  ];

  const totalMs    = etaSeconds * 1000;
  const tickMs     = 500;
  const totalTicks = Math.round(totalMs / tickMs);
  let tick = 0, halfwayDone = false;

  _autoSimTimer = setInterval(async () => {
    tick++;
    const pct    = Math.min((tick / totalTicks) * 100, 100);
    const ambPos = Math.min(pct * 0.90, 90);
    const wpIdx  = Math.min(Math.floor((pct / 100) * waypoints.length), waypoints.length - 1);

    const fillEl   = document.getElementById("del-fill");
    const ambEl    = document.getElementById("del-amb");
    const statusEl = document.getElementById("del-status");

    if (fillEl)  fillEl.style.width = pct + "%";
    if (ambEl)   ambEl.style.left   = ambPos + "%";
    if (statusEl) statusEl.textContent = `📍 ${waypoints[wpIdx]}`;

    // ── Move ambulance on live map in sync ──
    _updateAmbulanceOnMap(pct);

    if (pct >= 50 && !halfwayDone) {
      halfwayDone = true;
      const s1 = document.getElementById("step-pickup");
      const s2 = document.getElementById("step-transit");
      if (s1) { s1.style.color = "var(--success)"; s1.textContent = "✅ Picked Up"; }
      if (s2) s2.style.color = "var(--teal-dark)";
    }

    if (tick >= totalTicks) {
      clearInterval(_autoSimTimer);
      _autoSimTimer = null;
      if (ambEl)   { ambEl.style.left = "90%"; ambEl.classList.remove("siren"); }
      if (fillEl)  fillEl.style.width = "100%";
      if (statusEl) statusEl.textContent = "✅ Delivered successfully!";
      ["step-pickup","step-transit","step-delivered"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.color = "var(--success)";
      });
      const s3 = document.getElementById("step-delivered");
      if (s3) s3.textContent = "✅ Delivered";
      // Snap ambulance to destination on map
      _updateAmbulanceOnMap(100);
      await _completeDelivery(eruId);
    }
  }, tickMs);
}

// ── Fast-Forward: cancels auto-sim and runs at 400ms ticks ──
async function simulateRiderMovement(eruId, eruCode, etaSeconds) {
  // Cancel the real-time auto-sim
  if (_autoSimTimer) { clearInterval(_autoSimTimer); _autoSimTimer = null; }

  const simBtn = document.getElementById("simulate-btn");
  if (simBtn) { simBtn.disabled = true; simBtn.innerHTML = `<i class="fa fa-spinner fa-spin"></i> Fast-Forwarding…`; }

  const waypoints = [
    "Leaving blood bank…",
    "Passing main junction…",
    "Crossing railway station area…",
    "Entering residential zone…",
    "Approaching delivery address…",
    "Arriving at destination…"
  ];

  const totalMs    = etaSeconds * 1000;
  const tickMs     = 400;   // faster than real-time
  const totalTicks = Math.round(totalMs / tickMs);
  let tick = 0, halfwayDone = false;

  const ambEl = document.getElementById("del-amb");
  if (ambEl) ambEl.classList.add("siren");

  await new Promise(resolve => {
    const iv = setInterval(() => {
      tick++;
      const pct    = Math.min((tick / totalTicks) * 100, 100);
      const ambPos = Math.min(pct * 0.90, 90);
      const wpIdx  = Math.min(Math.floor((pct / 100) * waypoints.length), waypoints.length - 1);

      const fillEl   = document.getElementById("del-fill");
      const ambEl2   = document.getElementById("del-amb");
      const statusEl = document.getElementById("del-status");

      if (fillEl)  fillEl.style.width = pct + "%";
      if (ambEl2)  ambEl2.style.left  = ambPos + "%";
      if (statusEl) statusEl.textContent = `📍 ${waypoints[wpIdx]}`;

      // ── Move ambulance on live map in sync ──
      _updateAmbulanceOnMap(pct);

      if (pct >= 50 && !halfwayDone) {
        halfwayDone = true;
        const s1 = document.getElementById("step-pickup");
        const s2 = document.getElementById("step-transit");
        if (s1) { s1.style.color = "var(--success)"; s1.textContent = "✅ Picked Up"; }
        if (s2) s2.style.color = "var(--teal-dark)";
      }

      if (tick >= totalTicks) {
        clearInterval(iv);
        if (ambEl2)  { ambEl2.style.left = "90%"; ambEl2.classList.remove("siren"); }
        if (fillEl)  fillEl.style.width = "100%";
        if (statusEl) statusEl.textContent = "✅ Delivered successfully!";
        ["step-pickup","step-transit","step-delivered"].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.color = "var(--success)";
        });
        const s3 = document.getElementById("step-delivered");
        if (s3) s3.textContent = "✅ Delivered";
        // Snap ambulance to destination on map
        _updateAmbulanceOnMap(100);
        resolve();
      }
    }, tickMs);
  });

  const simWrap = document.getElementById("sim-wrap");
  if (simWrap) simWrap.style.display = "none";
  await _completeDelivery(eruId);
}

// ── Shared completion: called by both auto-sim and fast-forward ──
async function _completeDelivery(eruId) {
  const simWrap = document.getElementById("sim-wrap");
  if (simWrap) simWrap.style.display = "none";

  const statusEl = document.getElementById("del-status");
  if (statusEl) statusEl.textContent = "Finalising delivery & generating receipt…";

  try {
    const res  = await fetch("/api/eru/complete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ eru_id: eruId })
    });
    const data = await res.json();

    if (!data.success) {
      if (statusEl) statusEl.textContent = `Error: ${data.message}`;
      return;
    }

    showToast(`✅ Delivery complete! Receipt ${data.receipt_no}`, "success");
    loadDashboardStats();
    loadRecentEmergencies();

    const body = document.getElementById("modal-body");
    if (body) {
      body.innerHTML = `
        <div style="text-align:center;padding:16px;background:var(--teal-pale);
                    border-radius:var(--radius);margin-bottom:14px">
          <div style="font-size:40px;margin-bottom:8px">✅</div>
          <h4 style="color:var(--teal-dark);font-size:16px;font-weight:800;margin-bottom:4px">
            Delivery Successful!
          </h4>
          <p style="font-size:12px;color:var(--muted)">Receipt <strong>${data.receipt_no}</strong></p>
        </div>
        <!-- Itemised invoice -->
        <div style="background:var(--slate-50);border:1px solid var(--slate-200);
                    border-radius:var(--radius);padding:12px 14px;margin-bottom:14px;
                    font-size:13px;color:var(--slate-600)">
          <div style="display:flex;justify-content:space-between;padding:4px 0">
            <span>Blood bags (${data.bags} × ₹1,500)</span>
            <strong>₹${Number(data.bag_cost || 0).toLocaleString("en-IN")}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;padding:4px 0">
            <span>Distance charge (${data.distance_km} km × ₹5)</span>
            <strong>₹${Number(data.dist_charge || 0).toLocaleString("en-IN")}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;padding:4px 0">
            <span>Service fee (flat)</span>
            <strong>₹20</strong>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0 0;
                      border-top:1px solid var(--slate-200);margin-top:4px;
                      font-weight:800;color:var(--slate-800);font-size:14px">
            <span>Total</span>
            <span>₹${Number(data.total).toLocaleString("en-IN")}</span>
          </div>
        </div>
        <p style="font-size:12px;color:var(--teal-dark);font-weight:600;
                  text-align:center;margin-bottom:10px">
          Redirecting in <strong id="pay-redirect-count">3</strong>s…
        </p>
        <a href="${data.payment_url}" class="btn btn-success"
           style="width:100%;justify-content:center;text-decoration:none">
          <i class="fa fa-credit-card"></i> Pay Now — ₹${Number(data.total).toLocaleString("en-IN")}
        </a>`;

      let secs = 3;
      const cd = setInterval(() => {
        secs--;
        const el = document.getElementById("pay-redirect-count");
        if (el) el.textContent = secs;
        if (secs <= 0) { clearInterval(cd); window.location.href = data.payment_url; }
      }, 1000);
    }
  } catch {
    const statusEl2 = document.getElementById("del-status");
    if (statusEl2) statusEl2.textContent = "Completion failed. Please check the Rider page.";
  }
}
async function loadInventory() {
  const grid  = document.getElementById("inv-grid");
  const tbody = document.getElementById("inv-tbody");
  if (!grid && !tbody) return;

  try {
    const res  = await fetch("/api/inventory");
    const data = await res.json();

    if (grid) {
      grid.innerHTML = data.map(i => `
        <div class="inv-item ${i.status}">
          <div class="bg-label">${i.blood_group}</div>
          <div class="units-val">${i.units}</div>
          <div class="units-label">units</div>
          <span class="badge badge-${i.status}" style="margin-top:6px">${i.status}</span>
        </div>`).join("");
    }

    if (tbody) {
      tbody.innerHTML = data.map(i => `
        <tr>
          <td><span class="blood-badge">${i.blood_group}</span></td>
          <td><strong>${i.units}</strong></td>
          <td>₹${i.cost_per_bag.toLocaleString("en-IN")}</td>
          <td><span class="badge badge-${i.status}">${i.status}</span></td>
          <td>
            <button class="btn btn-sm btn-outline" onclick="adjustStock('${i.blood_group}', 1)">+1</button>
            <button class="btn btn-sm btn-gray" onclick="adjustStock('${i.blood_group}', -1)" style="margin-left:4px">-1</button>
          </td>
        </tr>`).join("");
    }

    renderInventoryChart(data);
  } catch (err) { console.error("Inventory load failed", err); }
}

async function adjustStock(bg, delta) {
  try {
    const res  = await fetch("/api/inventory/update", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blood_group: bg, delta })
    });
    const data = await res.json();
    if (data.success) { showToast(`${bg} updated: ${data.units} units`, "success"); loadInventory(); }
  } catch { showToast("Update failed", "error"); }
}

let invChart = null;

// ── Central lock: prevents concurrent city-switch renders ──
let _invLoadId = 0;

/**
 * updateInventoryUI(data, loadId)
 * Single source of truth for rendering both the grid cards and the
 * doughnut chart. Checks loadId to discard stale responses that
 * arrive after a newer city was already selected.
 */
function updateInventoryUI(data, loadId) {
  // Discard if a newer request has already started
  if (loadId !== _invLoadId) return;

  const ALL_BG = ["A+","A-","B+","B-","O+","O-","AB+","AB-"];

  // Normalise: build a map keyed by blood_group, defaulting units to 0
  const map = {};
  for (const bg of ALL_BG) map[bg] = 0;
  for (const item of data) {
    map[item.blood_group] = item.units !== undefined && item.units !== null
      ? Number(item.units) : 0;
  }

  // ── Grid cards ──
  const grid = document.getElementById("inv-grid");
  if (grid) {
    grid.innerHTML = ALL_BG.map(bg => {
      const units  = map[bg];
      const status = units < 5 ? "critical" : units < 10 ? "low" : "ok";
      return `
        <div class="inv-item ${status}">
          <div class="bg-label">${bg}</div>
          <div class="units-val">${units}</div>
          <div class="units-label">units</div>
          <span class="badge badge-${status}" style="margin-top:6px">${status}</span>
        </div>`;
    }).join("");
  }

  // ── Admin table ──
  const tbody = document.getElementById("inv-tbody");
  if (tbody) {
    const hasAdmin = data.length > 0 && data[0].cost_per_bag !== undefined;
    if (hasAdmin) {
      tbody.innerHTML = data.map(i => {
        const units  = i.units !== null && i.units !== undefined ? Number(i.units) : 0;
        const status = units < 5 ? "critical" : units < 10 ? "low" : "ok";
        return `
          <tr>
            <td><span class="blood-badge">${i.blood_group}</span></td>
            <td>${i.city || ""}</td>
            <td><strong>${units}</strong></td>
            <td>₹${Number(i.cost_per_bag || 0).toLocaleString("en-IN")}</td>
            <td><span class="badge badge-${status}">${status}</span></td>
            <td>
              <button class="btn btn-sm btn-outline"
                      onclick="adjustStockCity('${i.blood_group}','${i.city}',1)">+1</button>
              <button class="btn btn-sm btn-gray"
                      onclick="adjustStockCity('${i.blood_group}','${i.city}',-1)"
                      style="margin-left:4px">-1</button>
            </td>
          </tr>`;
      }).join("");
    } else {
      // Non-admin: units are now always present in the response
      tbody.innerHTML = data.map(i => {
        const units  = Number(i.units ?? 0);
        const status = units < 5 ? "critical" : units < 10 ? "low" : "ok";
        return `
          <tr>
            <td><span class="blood-badge">${i.blood_group}</span></td>
            <td>${i.city || ""}</td>
            <td><strong>${units}</strong></td>
            <td><span class="badge badge-${status}">${status}</span></td>
            <td>${units > 0 ? "✓ Available" : "✗ Unavailable"}</td>
          </tr>`;
      }).join("");
    }
  }

  // ── Doughnut chart — always destroy & recreate ──
  const canvas  = document.getElementById("inv-chart");
  const loading = document.getElementById("inv-chart-loading");
  if (canvas && typeof Chart !== "undefined") {
    if (invChart) { invChart.destroy(); invChart = null; }

    const labels = ALL_BG;
    const values = labels.map(bg => map[bg]);

    invChart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: [
            "#9b1c1c","#dc2626","#b91c1c","#d35400",
            "#8e44ad","#2980b9","#0d9488","#f39c12"
          ],
          borderWidth: 3,
          borderColor: "#fff",
          hoverOffset: 8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            position: "bottom",
            labels: { font: { size: 12, weight: "600" }, padding: 14, color: "#334155" }
          },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.label}: ${ctx.parsed} unit(s)`,
              afterLabel: ctx => {
                const v = ctx.parsed;
                return v < 5 ? "⚠️ Critical" : v < 10 ? "⚡ Low" : "✅ OK";
              }
            }
          }
        },
        cutout: "55%"
      }
    });

    canvas.style.display = "block";
    if (loading) loading.style.display = "none";
  }
}

function renderInventoryChart(data) {
  // Legacy shim — delegate to updateInventoryUI so there's one code path
  if (!data || !data.length) return;
  _invLoadId++;
  updateInventoryUI(data, _invLoadId);
}

// ─── DONORS ──────────────────────────────────────────────────
async function loadDonors(bg = "", city = "") {
  const tbody = document.getElementById("donors-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:20px"><div class="spinner" style="width:28px;height:28px;border-width:3px"></div></td></tr>`;
  try {
    const params = new URLSearchParams();
    if (bg)   params.set("blood_group", bg);
    if (city) params.set("city", city);
    const res  = await fetch("/api/donors/search?" + params);
    const data = await res.json();
    if (!data.length) { tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:20px">No donors found</td></tr>`; return; }
    tbody.innerHTML = data.map(d => `
      <tr>
        <td>${d.name}</td>
        <td><span class="blood-badge">${d.blood_group}</span></td>
        <td>${d.city}</td>
        <td>${d.phone || "—"}</td>
        <td>${d.donations}</td>
        <td><span class="badge ${d.is_available ? "badge-available" : "badge-unavailable"}">${d.is_available ? "Available" : "Unavailable"}</span></td>
        <td>
          <button class="btn btn-sm btn-outline" id="cert-btn-${d.id}"
                  onclick="getCertificate(${d.id})"
                  title="Certificate available after a Completed donation">
            <i class="fa fa-certificate"></i> Cert
          </button>
        </td>
      </tr>`).join("");
    // Check cert lock status for each donor
    data.forEach(d => checkCertificateStatus(d.id, document.getElementById(`cert-btn-${d.id}`)));
  } catch { tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger);text-align:center;padding:20px">Failed to load donors</td></tr>`; }
}

function filterDonors() {
  const bg   = document.getElementById("filter-blood")?.value || "";
  const city = document.getElementById("filter-city")?.value  || "";
  loadDonors(bg, city);
}

// ─── ERU — LEGACY CREATE (kept for Rider page direct use) ────
async function createDeliveryRequest(payload) {
  // This is now only used if called directly; the modal uses initiateDelivery()
  const body = document.getElementById("modal-body");
  if (body) {
    body.innerHTML = `<div class="loading-state"><div class="spinner"></div>
      <p style="margin-top:8px;font-weight:600">Creating delivery request…</p></div>`;
  }
  try {
    const res  = await fetch("/api/eru/create", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast(`ERU ${data.eru_code} created`, "success");
      loadDashboardStats();
      loadRecentEmergencies();
    }
  } catch { showToast("Failed to create delivery request", "error"); }
}

// ─── CERTIFICATE ─────────────────────────────────────────────
async function getCertificate(donorId) {
  try {
    const res  = await fetch(`/api/certificate/${donorId}`);
    const data = await res.json();
    if (data.locked) {
      showToast(data.message, "warning");
      return;
    }
    showCertificateModal(data);
  } catch { showToast("Failed to generate certificate", "error"); }
}

async function checkCertificateStatus(donorId, btnEl) {
  try {
    const res  = await fetch(`/api/donation/check/${donorId}`);
    const data = await res.json();
    if (!data.has_completed) {
      btnEl.disabled = true;
      btnEl.title    = "Locked — awaiting Completed donation record";
      btnEl.style.opacity = "0.45";
    }
  } catch { /* silently ignore */ }
}

function showCertificateModal(c) {
  let modal = document.getElementById("cert-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "cert-modal";
    modal.className = "modal-overlay";
    modal.innerHTML = `<div class="modal" style="max-width:480px"><div id="cert-content"></div></div>`;
    modal.addEventListener("click", e => { if (e.target === modal) modal.classList.remove("show"); });
    document.body.appendChild(modal);
  }
  document.getElementById("cert-content").innerHTML = `
    <div class="certificate">
      <h2>🩸 Certificate of Appreciation</h2>
      <p class="cert-no">Certificate No: ${c.certificate_no}</p>
      <p class="cert-msg">This is to certify that</p>
      <p class="cert-name">${c.donor_name}</p>
      <p class="cert-msg">${c.message}</p>
      <p><span class="blood-badge">${c.blood_group}</span> &nbsp; ${c.city}</p>
      <p class="cert-date">Issued on: ${c.issued_date}</p>
    </div>
    <button class="btn btn-gray" style="width:100%;justify-content:center;margin-top:16px" onclick="document.getElementById('cert-modal').classList.remove('show')">Close</button>`;
  modal.classList.add("show");
}

// ─── FINANCE ─────────────────────────────────────────────────
async function calculateCost() {
  const bg   = document.getElementById("fin-blood")?.value  || "A+";
  const bags = Math.min(parseInt(document.getElementById("fin-bags")?.value  || 1), 15);

  // Clamp input to 15
  const bagsInput = document.getElementById("fin-bags");
  if (bagsInput && parseInt(bagsInput.value) > 15) bagsInput.value = 15;

  try {
    const res  = await fetch("/api/finance/calculate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blood_group: bg, bags })
    });
    const data = await res.json();
    setText("calc-subtotal",  "₹" + (data.bags * data.cost_per_bag).toLocaleString("en-IN"));
    setText("calc-delivery",  "₹" + data.delivery_fee.toLocaleString("en-IN"));
    setText("calc-total",     "₹" + data.total.toLocaleString("en-IN"));
    setText("calc-per-bag",   "₹" + data.cost_per_bag.toLocaleString("en-IN"));

    const flagBox = document.getElementById("fraud-flags");
    if (flagBox) {
      if (data.fraud_flags.length) {
        flagBox.innerHTML = `<div class="fraud-alert"><i class="fa fa-exclamation-triangle"></i><strong>Alerts:</strong><ul style="margin:6px 0 0 18px">${data.fraud_flags.map(f => `<li>${f}</li>`).join("")}</ul></div>`;
      } else {
        flagBox.innerHTML = "";
      }
    }
  } catch (err) { console.error("Calc failed", err); }
}

async function generateReceipt() {
  const bg      = document.getElementById("fin-blood")?.value  || "A+";
  const bags    = Math.min(parseInt(document.getElementById("fin-bags")?.value  || 1), 15);
  const patient = document.getElementById("fin-patient")?.value.trim();
  const city    = document.getElementById("fin-city")?.value || "";

  if (!patient) { showToast("Patient name is required", "warning"); return; }

  const btn = document.querySelector('[onclick="generateReceipt()"]');
  if (btn) { btn.disabled = true; btn.innerHTML = `<i class="fa fa-spinner fa-spin"></i> Processing...`; }

  try {
    const res  = await fetch("/api/finance/receipt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blood_group: bg, bags, patient_name: patient, city })
    });
    const data = await res.json();

    if (!data.success) {
      showToast(data.message, "error");
      if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fa fa-file-invoice"></i> &nbsp; Generate Receipt`; }
      return;
    }

    // ── 1. Render receipt preview ──
    renderReceipt(data.receipt);
    loadTransactions();

    // ── 2. Immediately refresh inventory stock levels in the DB display ──
    refreshInventoryStats(city || "");

    // ── 3. Show redirect banner then navigate to Payment Portal ──
    const receiptBox = document.getElementById("receipt-box");
    if (receiptBox) {
      const banner = document.createElement("div");
      banner.id = "pay-redirect-banner";
      banner.style.cssText = `
        background:var(--success-pale);border:1.5px solid #6ee7b7;
        border-radius:var(--radius);padding:14px 18px;margin-top:14px;
        text-align:center;font-size:13.5px;color:var(--success);font-weight:600`;
      banner.innerHTML = `
        <i class="fa fa-check-circle"></i>
        Receipt generated &amp; inventory updated.
        Redirecting to Payment Portal in <strong id="pay-countdown">3</strong>s…
        <br><a href="${data.payment_url}"
               style="color:var(--success);text-decoration:underline;font-size:12px">
          Go now →
        </a>`;
      receiptBox.appendChild(banner);

      let secs = 3;
      const iv = setInterval(() => {
        secs--;
        const el = document.getElementById("pay-countdown");
        if (el) el.textContent = secs;
        if (secs <= 0) { clearInterval(iv); window.location.href = data.payment_url; }
      }, 1000);
    } else {
      window.location.href = data.payment_url;
    }

    showToast("Receipt created — inventory updated — redirecting to payment", "success");
  } catch {
    showToast("Receipt generation failed", "error");
    if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fa fa-file-invoice"></i> &nbsp; Generate Receipt`; }
  }
}

// ── Dedicated pie chart loader — delegates to updateInventoryUI ──
async function loadInventoryPieChart(city) {
  const canvas  = document.getElementById("inv-chart");
  const loading = document.getElementById("inv-chart-loading");
  if (!canvas) return;

  if (loading) loading.style.display = "block";
  canvas.style.display = "none";

  const loadId = ++_invLoadId;

  try {
    const url  = city
      ? `/api/inventory/stats?city=${encodeURIComponent(city)}`
      : "/api/inventory/stats";
    const res  = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (loadId !== _invLoadId) return;   // stale — newer city already loading

    const cityLabel = document.getElementById("chart-city-label");
    if (cityLabel) cityLabel.textContent = city || "All Locations";

    // items already have units guaranteed as integers from the backend
    updateInventoryUI(data.items, loadId);

  } catch (err) {
    if (loadId !== _invLoadId) return;
    console.error("Pie chart load failed:", err);
    if (loading) loading.style.display = "none";
  }
}

// ── Fetch live inventory stats and refresh all inventory UI elements ──
async function refreshInventoryStats(city) {
  try {
    const url  = city
      ? `/api/inventory/stats?city=${encodeURIComponent(city)}`
      : "/api/inventory/stats";
    const res  = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    // Update dashboard stat card if present
    setText("stat-units", data.total_units ?? 0);

    // Refresh blood distribution chart if on dashboard
    if (document.getElementById("bloodDistChart")) {
      const cityFilter = document.getElementById("chart-city-filter")?.value || "";
      loadBloodDistributionChart(cityFilter);
    }

    // Refresh inventory page UI if present
    if (document.getElementById("inv-chart") || document.getElementById("inv-grid")) {
      const loadId = ++_invLoadId;
      updateInventoryUI(data.items, loadId);
      const cityLabel = document.getElementById("chart-city-label");
      if (cityLabel) cityLabel.textContent = city || "All Locations";
    }

    // Refresh dashboard inventory gauges if present
    const gaugeGrid = document.getElementById("inv-gauge-grid");
    if (gaugeGrid && data.items.length) {
      const maxUnits = Math.max(...data.items.map(i => i.units), 1);
      gaugeGrid.innerHTML = data.items.map(i => `
        <a href="/inventory" class="inv-gauge ${i.status}"
           title="${i.blood_group}: ${i.units} units">
          <div class="ig-label">${i.blood_group}</div>
          <div class="ig-bar-track">
            <div class="ig-bar-fill"
                 style="width:${Math.round((i.units / maxUnits) * 100)}%"></div>
          </div>
          <div class="ig-units">${i.units} u</div>
        </a>`).join("");
    }
  } catch (err) { console.warn("Inventory refresh failed:", err); }
}

function renderReceipt(r) {
  const box = document.getElementById("receipt-box");
  if (!box) return;
  box.innerHTML = `
    <div class="receipt">
      <div class="receipt-header">
        <h3>🩸 Smart Blood System</h3>
        <p>Official Receipt</p>
      </div>
      <div class="receipt-row"><span class="label">Receipt No</span><span class="value">${r.receipt_no}</span></div>
      <div class="receipt-row"><span class="label">Date</span><span class="value">${r.date}</span></div>
      <div class="receipt-row"><span class="label">Patient</span><span class="value">${r.patient_name}</span></div>
      <div class="receipt-row"><span class="label">Blood Group</span><span class="value"><span class="blood-badge">${r.blood_group}</span></span></div>
      <div class="receipt-row"><span class="label">Bags</span><span class="value">${r.bags}</span></div>
      <div class="receipt-row"><span class="label">Cost / Bag</span><span class="value">₹${r.cost_per_bag.toLocaleString("en-IN")}</span></div>
      <div class="receipt-row"><span class="label">Delivery Fee</span><span class="value">₹${r.delivery_fee.toLocaleString("en-IN")}</span></div>
      ${r.city ? `<div class="receipt-row"><span class="label">Delivery City</span><span class="value">${r.city}</span></div>` : ""}
      <div class="receipt-total"><span>Total</span><span>₹${r.total.toLocaleString("en-IN")}</span></div>
      <div style="text-align:center;margin-top:12px">
        <span class="badge badge-${r.status}">${r.status.toUpperCase()}</span>
      </div>
      ${r.fraud_flags.length ? `<div class="fraud-alert"><i class="fa fa-exclamation-triangle"></i> ${r.fraud_flags.join(" | ")}</div>` : ""}
    </div>`;
}

async function loadTransactions() {
  const tbody = document.getElementById("txn-tbody");
  if (!tbody) return;
  try {
    const res  = await fetch("/api/finance/transactions");
    const data = await res.json();
    if (!data.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:16px">No transactions yet</td></tr>`;
      return;
    }
    tbody.innerHTML = data.map(t => `
      <tr class="${t.status === "pending" ? "txn-row-pending" : ""}">
        <td><code style="font-size:12px">${t.receipt_no}</code></td>
        <td>${t.patient_name}</td>
        <td><span class="blood-badge">${t.blood_group}</span></td>
        <td>${t.bags}</td>
        <td>₹${t.total.toLocaleString("en-IN")}</td>
        <td><span class="badge badge-${t.status}">${t.status.toUpperCase()}</span></td>
        <td>${t.date}</td>
        <td>
          ${t.status === "paid"
            ? `<span style="color:var(--success);font-size:12px;font-weight:700">
                 <i class="fa fa-check-circle"></i> Paid
               </span>`
            : `<a href="/payment?receipt=${t.receipt_no}"
                  class="btn btn-sm btn-success">
                 <i class="fa fa-credit-card"></i> Pay Now
               </a>`}
        </td>
      </tr>`).join("");
  } catch { console.error("Transactions load failed"); }
}

// ─── HEALTH ELIGIBILITY CHECK ────────────────────────────────
async function runEligibilityCheck(e) {
  if (e) e.preventDefault();
  const btn    = document.getElementById("elig-btn");
  const result = document.getElementById("elig-result");
  if (!result) return;

  // ── Auto-fill from SQL user record if available ──
  const currentUser = window.CURRENT_USER
    || JSON.parse(sessionStorage.getItem("sbdms_user") || "null");
  if (currentUser) {
    const lastDateEl = document.getElementById("elig-last-date");
    if (lastDateEl && !lastDateEl.value && currentUser.last_donated) {
      lastDateEl.value = currentUser.last_donated;
    }
  }

  const dobVal  = document.getElementById("elig-dob")?.value || "";
  const lastVal = document.getElementById("elig-last-date")?.value || "";

  // ── Client-side age-gate before hitting the API ──
  if (dobVal && lastVal) {
    const dob  = new Date(dobVal);
    const last = new Date(lastVal);
    let ageAtDonation = last.getFullYear() - dob.getFullYear();
    const md = last.getMonth() - dob.getMonth();
    if (md < 0 || (md === 0 && last.getDate() < dob.getDate())) ageAtDonation--;

    if (ageAtDonation < 18) {
      result.innerHTML = `
        <div class="elig-result ineligible" style="margin-top:20px">
          <div class="elig-result-header">
            <div class="elig-result-icon">❌</div>
            <div>
              <h3>Not Eligible at This Time</h3>
              <p style="font-size:13px;color:var(--muted);margin-top:3px">1 issue found. Please review before booking.</p>
            </div>
          </div>
          <div class="elig-checks">
            <div class="elig-check-item fail">
              <i class="fa fa-times-circle"></i>
              <span>Ineligible: You must have been at least 18 years old at the time of your last donation.</span>
            </div>
          </div>
        </div>`;
      result.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
  }

  const payload = {
    dob:            dobVal,
    age:            parseInt(document.getElementById("elig-age")?.value || 0),
    weight:         parseFloat(document.getElementById("elig-weight")?.value || 0),
    hemoglobin:     parseFloat(document.getElementById("elig-hb")?.value || 0),
    bp_systolic:    parseInt(document.getElementById("elig-bp-sys")?.value || 0),
    bp_diastolic:   parseInt(document.getElementById("elig-bp-dia")?.value || 0),
    last_donation:  lastVal,
    recent_illness: document.getElementById("elig-illness")?.checked || false,
    recent_surgery: document.getElementById("elig-surgery")?.checked || false,
    on_medication:  document.getElementById("elig-medication")?.checked || false,
  };

  if (btn) { btn.disabled = true; btn.innerHTML = `<i class="fa fa-spinner fa-spin"></i> Checking...`; }

  try {
    const res  = await fetch("/api/eligibility/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderEligibilityResult(data);
  } catch { result.innerHTML = `<p style="color:var(--crimson)">Check failed. Try again.</p>`; }
  finally {
    if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fa fa-stethoscope"></i> Check Eligibility`; }
  }
}

function renderEligibilityResult(data) {
  const result = document.getElementById("elig-result");
  if (!result) return;

  const cls = data.eligible ? "eligible" : "ineligible";
  const icon = data.eligible ? "✅" : "❌";
  const title = data.eligible ? "You Are Eligible to Donate!" : "Not Eligible at This Time";

  const passedHtml = data.passed.map(p => `
    <div class="elig-check-item pass"><i class="fa fa-check-circle"></i><span>${p}</span></div>`).join("");

  const issuesHtml = data.issues.map(i => `
    <div class="elig-check-item fail"><i class="fa fa-times-circle"></i><span>${i}</span></div>`).join("");

  result.innerHTML = `
    <div class="elig-result ${cls}">
      <div class="elig-result-header">
        <div class="elig-result-icon">${icon}</div>
        <div>
          <h3>${title}</h3>
          <p style="font-size:13px;color:var(--muted);margin-top:3px">${data.summary}</p>
        </div>
      </div>
      <div class="elig-checks">
        ${passedHtml}
        ${issuesHtml}
      </div>
      ${data.eligible ? `
      <div class="book-btn-wrap">
        <button type="button" class="btn btn-teal btn-lg" style="display:inline-flex;margin-top:6px"
                onclick="saveEligibilityAndRedirect()">
          <i class="fa fa-calendar-check"></i> Book Donation Appointment
        </button>
      </div>` : `
      <div class="book-btn-wrap">
        <p style="font-size:13px;color:var(--muted);margin-top:8px">Please resolve the above issues before donating. Consult your doctor if needed.</p>
      </div>`}
    </div>`;

  result.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ─── SAVE ELIGIBILITY TO SESSION & REDIRECT ──────────────────
async function saveEligibilityAndRedirect() {
  const dob        = document.getElementById("elig-dob")?.value || "";
  const lastDate   = document.getElementById("elig-last-date")?.value || "";
  const bloodGroup = document.getElementById("elig-blood-group")?.value || "";

  if (!dob || !bloodGroup) {
    showToast("Please fill in Date of Birth and Blood Group before proceeding.", "error");
    return;
  }

  try {
    const res = await fetch("/api/eligibility/pass", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dob, last_donation: lastDate, blood_group: bloodGroup })
    });
    const data = await res.json();
    if (data.success) {
      window.location.href = "/book_appointment";
    } else {
      showToast(data.message || "Could not save eligibility data.", "error");
    }
  } catch {
    showToast("Network error. Please try again.", "error");
  }
}

// ─── UTILITY ─────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// Auto-capitalize: converts "rahul kumar sharma" → "Rahul Kumar Sharma"
function autoCapitalize(str) {
  return str.replace(/\b\w/g, c => c.toUpperCase());
}

// Sanitize name: strip digits and special chars, then capitalize
function sanitizeName(str) {
  return autoCapitalize(str.replace(/[^A-Za-z\s\-]/g, ""));
}

// Apply auto-capitalize on blur for name inputs
function bindNameCapitalize(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return;
  el.addEventListener("blur", () => { el.value = sanitizeName(el.value); });
  el.addEventListener("input", () => {
    // Strip digits/symbols in real-time
    const pos = el.selectionStart;
    el.value = el.value.replace(/[^A-Za-z\s\-]/g, "");
    el.setSelectionRange(pos, pos);
  });
}

// ─── CITY-FILTERED INVENTORY ─────────────────────────────────
async function loadInventoryByCity(city) {
  if (!city) return;

  // Increment the load ID — any in-flight response with an older ID will be discarded
  const loadId = ++_invLoadId;

  const grid    = document.getElementById("inv-grid");
  const canvas  = document.getElementById("inv-chart");
  const loading = document.getElementById("inv-chart-loading");

  // ── Show loading state immediately ──
  if (grid) {
    grid.innerHTML = `<div class="loading-state" style="grid-column:1/-1">
      <div class="spinner"></div>
      <p style="margin-top:8px;color:var(--muted);font-size:13px">Loading ${city}…</p>
    </div>`;
  }
  if (canvas) canvas.style.display = "none";
  if (loading) loading.style.display = "block";

  // Update chart city label
  const cityLabel = document.getElementById("chart-city-label");
  if (cityLabel) cityLabel.textContent = city;

  try {
    const res  = await fetch(`/api/inventory/city/${encodeURIComponent(city)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Stale-response guard: another city was selected while this was in flight
    if (loadId !== _invLoadId) return;

    updateInventoryUI(data, loadId);

  } catch (err) {
    if (loadId !== _invLoadId) return;   // still discard stale errors
    console.error("City inventory load failed:", err);
    if (grid) grid.innerHTML = `<p style="color:var(--crimson);grid-column:1/-1;text-align:center;padding:20px">
      Failed to load inventory for ${city}. <button class="btn btn-sm btn-outline" onclick="loadInventoryByCity('${city}')">Retry</button>
    </p>`;
    if (loading) loading.style.display = "none";
  }
}

async function adjustStockCity(bg, city, delta) {
  try {
    const res  = await fetch("/api/inventory/update", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blood_group: bg, city, delta })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`${bg} (${city}) updated: ${data.units} units`, "success");
      const cityFilter = document.getElementById("city-filter")?.value || city;
      loadInventoryByCity(cityFilter);
    }
  } catch { showToast("Update failed", "error"); }
}

// ─── DELIVERY NOTIFICATION AREA ──────────────────────────────
function showDeliveryNotification(delivery) {
  const area = document.getElementById("delivery-notification");
  if (!area || !delivery) return;

  area.style.display = "block";
  area.innerHTML = `
    <div class="delivery-notif">
      <div class="dn-header">
        <span class="dn-icon">🚑</span>
        <div>
          <strong>Bloodhound Dispatched!</strong>
          <span class="badge badge-available" style="margin-left:8px">${delivery.status}</span>
        </div>
        <div class="dn-eta">ETA: <strong>${delivery.eta_minutes} min</strong></div>
      </div>
      <div class="dn-details">
        <div><i class="fa fa-user" style="color:var(--teal);width:16px"></i> Rider: <strong>${delivery.rider_name}</strong> · ${delivery.rider_phone}</div>
        <div><i class="fa fa-hospital" style="color:var(--crimson);width:16px"></i> Pickup: <strong>${delivery.pickup_bank}</strong></div>
      </div>
      <div class="dn-progress">
        <div class="dn-step ${delivery.status === "At Bank" || delivery.status === "In Transit" || delivery.status === "Delivered" ? "done" : ""}">
          <span>🏥</span><small>At Bank</small>
        </div>
        <div class="dn-line ${delivery.status === "In Transit" || delivery.status === "Delivered" ? "done" : ""}"></div>
        <div class="dn-step ${delivery.status === "In Transit" || delivery.status === "Delivered" ? "done" : ""}">
          <span>🚑</span><small>In Transit</small>
        </div>
        <div class="dn-line ${delivery.status === "Delivered" ? "done" : ""}"></div>
        <div class="dn-step ${delivery.status === "Delivered" ? "done" : ""}">
          <span>🏨</span><small>Delivered</small>
        </div>
      </div>
    </div>`;
}

// ─── PAGE INIT ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname;

  // Bind auto-capitalize to all name fields on any page
  ["su-first","su-middle","su-last","appt-name","fin-patient"].forEach(bindNameCapitalize);

  if (path === "/dashboard") {
    // Dashboard data is loaded by guardSession() in dashboard.html after auth check
    // No-op here to avoid loading before authentication is confirmed
  }

  if (path === "/inventory") {
    // inventory.html has its own DOMContentLoaded that calls loadInventoryByCity
    // script.js only needs to handle the case where city-filter exists but
    // inventory.html's inline script hasn't run (e.g. admin-only loadInventory path)
    const cityFilter = document.getElementById("city-filter");
    if (!cityFilter) {
      // No city filter present — load full admin inventory
      loadInventory();
    }
    // city-filter path is handled by inventory.html's inline onCityChange / DOMContentLoaded
  }

  if (path === "/finance") {
    calculateCost();
    loadTransactions();
  }

  if (path === "/dashboard" || path === "/inventory") {
    if (document.getElementById("donors-tbody")) loadDonors();
  }
});
