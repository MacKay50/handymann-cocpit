/**
 * nav.js — Navigationsindsprøjtning for alle sider.
 *
 * Layout: Topbar (sektioner) + venstre sidebar (underpunkter).
 * Mønster: e-conomic-inspireret. KISS — ingen dubletter.
 * Sikkerhed: textContent (aldrig innerHTML) på brugerdata (RISK-01).
 */

(function () {
  "use strict";

  // ── Navigationshierarki ───────────────────────────────────────────────────
  // Ét sted at definere alt. Ingen overlap mellem sektioner.

  var SECTIONS = [
    {
      id: "overblik", label: "Overblik",
      match: function (p, t) { return p === "/ui" && (!t || t === "overview"); },
      subs: [],
      defaultHref: "/ui?tab=overview",
    },
    {
      id: "indbakke", label: "Indbakke",
      match: function (p, t) { return p === "/ui" && (t === "inbox" || t === "deadlines"); },
      subs: [
        { label: "Beskeder",  href: "/ui?tab=inbox" },
        { label: "Kalender",  href: "/ui?tab=deadlines" },
      ],
      defaultHref: "/ui?tab=inbox",
    },
    {
      id: "projekter", label: "Projekter",
      match: function (p, t) { return p === "/ui" && (t === "projects" || t === "customers"); },
      subs: [
        { label: "Projekter", href: "/ui?tab=projects" },
        { label: "Kunder",    href: "/ui?tab=customers" },
      ],
      defaultHref: "/ui?tab=projects",
    },
    {
      id: "oekonomi", label: "Økonomi",
      match: function (p, t) {
        return (p === "/ui" && (t === "invoices" || t === "quotes" || t === "reminders"))
          || p === "/reconciliation" || p === "/betalingsradar";
      },
      subs: [
        { label: "Fakturaer",       href: "/ui?tab=invoices" },
        { label: "Tilbud",          href: "/ui?tab=quotes" },
        { label: "Rykkere",         href: "/ui?tab=reminders" },
        { label: "Bankafstemning",  href: "/reconciliation" },
        { label: "Betalingsradar",  href: "/betalingsradar" },
      ],
      defaultHref: "/ui?tab=invoices",
    },
    {
      id: "tid", label: "Tid & Udlæg",
      match: function (p, t) {
        return (p === "/ui" && t === "employees") || p === "/export";
      },
      subs: [
        { label: "Medarbejdere", href: "/ui?tab=employees" },
        { label: "Eksport",      href: "/export" },
      ],
      defaultHref: "/ui?tab=employees",
    },
    {
      id: "intake", label: "Guided Intake",
      match: function (p) { return p === "/wizard"; },
      subs: [
        { label: "📞 Guided Intake", href: "/wizard" },
      ],
      defaultHref: "/wizard",
    },
    {
      id: "indstillinger", label: "Indstillinger",
      match: function (p) { return p === "/settings"; },
      subs: [],
      defaultHref: "/settings",
    },
  ];

  var TAB_TO_INTAKE = {
    inbox: "message", projects: "project_task",
    customers: "project_task", invoices: "internal_task",
    quotes: "internal_task", employees: "internal_task",
  };

  // ── CSS ───────────────────────────────────────────────────────────────────

  var css = [
    // Topbar
    "#nav-top{position:fixed;top:0;left:0;right:0;height:44px;background:#1a1a2e;display:flex;align-items:center;padding:0 1rem;gap:.5rem;z-index:1000;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:.82rem;}",
    "#nav-logo{font-weight:700;font-size:.95rem;color:#fff;text-decoration:none;margin-right:.75rem;white-space:nowrap;}",
    ".nav-sec{color:rgba(255,255,255,.65);font-size:.82rem;font-weight:500;text-decoration:none;padding:.3rem .65rem;border-radius:5px;white-space:nowrap;cursor:pointer;background:none;border:none;}",
    ".nav-sec:hover{color:#fff;background:rgba(255,255,255,.1);}",
    ".nav-sec.active{color:#fff;background:rgba(255,255,255,.18);}",
    "#nav-right{margin-left:auto;display:flex;align-items:center;gap:.5rem;}",
    "#nav-company-name{color:#e2e8f0;font-size:.8rem;font-weight:600;white-space:nowrap;}",
    "#nav-switch-btn{background:none;border:1px solid rgba(255,255,255,.25);color:#a0aec0;padding:.18rem .5rem;border-radius:4px;cursor:pointer;font-size:.72rem;}",
    "#nav-switch-btn:hover{color:#fff;border-color:rgba(255,255,255,.5);}",
    "#nav-new-btn{background:#48bb78;color:#fff;border:none;padding:.3rem .85rem;border-radius:5px;font-size:.8rem;font-weight:600;cursor:pointer;}",
    "#nav-new-btn:hover{background:#38a169;}",
    // Venstre sidebar
    "#nav-sidebar{position:fixed;top:44px;left:0;width:170px;bottom:0;background:#f7fafc;border-right:1px solid #e2e8f0;padding:.75rem 0;z-index:999;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;overflow-y:auto;}",
    "#nav-sidebar.empty{display:none;}",
    ".nav-sub-hdr{padding:.35rem 1rem .15rem;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#a0aec0;}",
    ".nav-sub{display:block;padding:.42rem 1rem;font-size:.83rem;color:#4a5568;text-decoration:none;border-left:3px solid transparent;white-space:nowrap;}",
    ".nav-sub:hover{background:#edf2f7;color:#2b6cb0;}",
    ".nav-sub.active{border-left-color:#2b6cb0;color:#2b6cb0;background:#ebf8ff;font-weight:600;}",
    // Sidelayout — skyv indhold til højre for sidebar
    "body{padding-top:44px!important;}",
    ".nav-has-sidebar body{padding-left:170px!important;}",
    ".nav-has-sidebar .page{padding-left:1.5rem;}",
    // Modals
    ".nav-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;align-items:center;justify-content:center;}",
    ".nav-overlay.open{display:flex;}",
    ".nav-modal-box{background:#fff;border-radius:10px;padding:1.5rem 2rem;min-width:320px;max-width:480px;width:100%;}",
    ".nav-modal-box h3{font-size:1rem;font-weight:700;margin-bottom:.75rem;}",
    ".nav-modal-box p{font-size:.87rem;color:#4a5568;margin-bottom:1.2rem;line-height:1.5;}",
    ".nav-row{display:flex;gap:.5rem;margin-bottom:.6rem;}",
    ".nav-row label{font-size:.82rem;color:#718096;width:110px;flex-shrink:0;padding-top:.4rem;}",
    ".nav-row select,.nav-row input{flex:1;padding:.4rem .6rem;border:1.5px solid #cbd5e0;border-radius:6px;font-size:.82rem;}",
    ".nav-btns{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1rem;}",
    ".nav-btns button{padding:.4rem 1rem;border-radius:6px;border:none;cursor:pointer;font-size:.82rem;font-weight:600;}",
    ".nav-btn-cancel{background:#e2e8f0;color:#4a5568;}",
    ".nav-btn-primary{background:#2b6cb0;color:#fff;}",
    ".nav-btn-danger{background:#e53e3e;color:#fff;}",
    ".nav-btn-danger:hover{background:#c53030;}",
    "#nav-modal-fields .nav-row{margin-bottom:.5rem;}",
  ].join("");

  var styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ── Aktiv sektion ─────────────────────────────────────────────────────────

  function getActiveSection() {
    var p = window.location.pathname;
    var t = window._currentTab || new URLSearchParams(window.location.search).get("tab") || "";
    for (var i = 0; i < SECTIONS.length; i++) {
      if (SECTIONS[i].match(p, t)) return SECTIONS[i];
    }
    return SECTIONS[0]; // fallback: Overblik
  }

  function getActiveSub() {
    var p = window.location.pathname;
    var t = window._currentTab || new URLSearchParams(window.location.search).get("tab") || "";
    var sec = getActiveSection();
    for (var i = 0; i < sec.subs.length; i++) {
      var s = sec.subs[i];
      var href = s.href || "";
      var tabParam = new URLSearchParams(href.split("?")[1] || "").get("tab") || "";
      if (href.split("?")[0] === p && (tabParam === t || (!tabParam && !t))) return s;
      if (tabParam && tabParam === t) return s;
      if (!tabParam && href === p) return s;
    }
    return sec.subs[0] || null;
  }

  // ── Topbar ────────────────────────────────────────────────────────────────

  var topbar = document.createElement("div");
  topbar.id = "nav-top";

  var logo = document.createElement("a");
  logo.id = "nav-logo";
  logo.href = "/ui?tab=overview";
  logo.textContent = "HVS";
  topbar.appendChild(logo);

  var activeSec = getActiveSection();

  SECTIONS.forEach(function (sec) {
    var btn = document.createElement("a");
    btn.className = "nav-sec" + (sec.id === activeSec.id ? " active" : "");
    btn.href = sec.defaultHref;
    btn.textContent = sec.label;
    topbar.appendChild(btn);
  });

  var right = document.createElement("div");
  right.id = "nav-right";

  var companyName = document.createElement("span");
  companyName.id = "nav-company-name";
  companyName.textContent = "…";

  var switchBtn = document.createElement("button");
  switchBtn.id = "nav-switch-btn";
  switchBtn.textContent = "Skift virksomhed";
  switchBtn.addEventListener("click", openSwitchModal);

  var newBtn = document.createElement("button");
  newBtn.id = "nav-new-btn";
  newBtn.textContent = "+ Ny";
  newBtn.addEventListener("click", openIntakeModal);

  right.appendChild(companyName);
  right.appendChild(switchBtn);
  right.appendChild(newBtn);
  topbar.appendChild(right);

  // ── Venstre sidebar ───────────────────────────────────────────────────────

  var sidebar = document.createElement("nav");
  sidebar.id = "nav-sidebar";

  function buildSidebar() {
    sidebar.innerHTML = "";
    var sec = getActiveSection();
    if (!sec.subs.length) {
      sidebar.className = "empty";
      document.documentElement.classList.remove("nav-has-sidebar");
      return;
    }
    sidebar.className = "";
    document.documentElement.classList.add("nav-has-sidebar");

    var hdr = document.createElement("div");
    hdr.className = "nav-sub-hdr";
    hdr.textContent = sec.label;
    sidebar.appendChild(hdr);

    var activeSub = getActiveSub();
    sec.subs.forEach(function (sub) {
      var a = document.createElement("a");
      a.className = "nav-sub" + (activeSub && sub.label === activeSub.label ? " active" : "");
      a.href = sub.href || "#";
      a.textContent = sub.label;
      // Hvis det er en ui.html tab-link, skift tab direkte uden page reload
      var tabParam = new URLSearchParams((sub.href || "").split("?")[1] || "").get("tab");
      if (tabParam && window.location.pathname === "/ui" && typeof window.showTab === "function") {
        a.addEventListener("click", function (e) {
          e.preventDefault();
          window.showTab(tabParam);
          // Opdater active state
          sidebar.querySelectorAll(".nav-sub").forEach(function (el) {
            el.classList.remove("active");
          });
          a.classList.add("active");
        });
      }
      sidebar.appendChild(a);
    });
  }

  // Genbyg sidebar når _currentTab ændres (ui.html kalder window._navRefresh)
  window._navRefresh = buildSidebar;

  // ── DOM indsættelse ───────────────────────────────────────────────────────

  document.body.insertBefore(sidebar, document.body.firstChild);
  document.body.insertBefore(topbar, document.body.firstChild);

  buildSidebar();

  // ── Skift-virksomhed modal ────────────────────────────────────────────────

  var switchOverlay = document.createElement("div");
  switchOverlay.className = "nav-overlay";

  var switchBox = document.createElement("div");
  switchBox.className = "nav-modal-box";

  var switchH = document.createElement("h3");
  switchH.textContent = "Skift virksomhed?";
  switchBox.appendChild(switchH);

  var switchP = document.createElement("p");
  switchP.textContent = "Du er ved at forlade den nuværende virksomhed og vende tilbage til virksomhedsvælgeren. Husk at gemme eventuelle ændringer inden du skifter.";
  switchBox.appendChild(switchP);

  var switchBtns = document.createElement("div");
  switchBtns.className = "nav-btns";

  var stayBtn = document.createElement("button");
  stayBtn.className = "nav-btn-cancel";
  stayBtn.textContent = "Forbliv her";
  stayBtn.addEventListener("click", function () { switchOverlay.classList.remove("open"); });

  var goBtn = document.createElement("button");
  goBtn.className = "nav-btn-danger";
  goBtn.textContent = "Skift virksomhed →";
  goBtn.addEventListener("click", doSwitch);

  switchBtns.appendChild(stayBtn);
  switchBtns.appendChild(goBtn);
  switchBox.appendChild(switchBtns);
  switchOverlay.appendChild(switchBox);
  document.body.appendChild(switchOverlay);

  function openSwitchModal() { switchOverlay.classList.add("open"); }
  async function doSwitch() {
    await fetch("/session/logout", { method: "DELETE", credentials: "include" });
    window.location.href = "/ui";
  }

  // ── Intake modal ──────────────────────────────────────────────────────────

  var intakeOverlay = document.createElement("div");
  intakeOverlay.className = "nav-overlay";

  var intakeBox = document.createElement("div");
  intakeBox.className = "nav-modal-box";

  var intakeH = document.createElement("h3");
  intakeH.textContent = "Opret ny";
  intakeBox.appendChild(intakeH);

  var typeRow = document.createElement("div");
  typeRow.className = "nav-row";
  var typeLbl = document.createElement("label");
  typeLbl.textContent = "Hvad er det?";
  var typeSelect = document.createElement("select");
  [
    ["message",       "📨  Kundehenvendelse"],
    ["project_task",  "✅  Opgave på projekt"],
    ["internal_task", "📋  Intern opgave"],
  ].forEach(function (v) {
    var o = document.createElement("option");
    o.value = v[0]; o.textContent = v[1];
    typeSelect.appendChild(o);
  });
  typeRow.appendChild(typeLbl);
  typeRow.appendChild(typeSelect);
  intakeBox.appendChild(typeRow);

  var fieldsDiv = document.createElement("div");
  fieldsDiv.id = "nav-modal-fields";
  intakeBox.appendChild(fieldsDiv);

  var intakeBtns = document.createElement("div");
  intakeBtns.className = "nav-btns";
  var cancelBtn = document.createElement("button");
  cancelBtn.className = "nav-btn-cancel";
  cancelBtn.textContent = "Annuller";
  cancelBtn.addEventListener("click", function () { intakeOverlay.classList.remove("open"); fieldsDiv.innerHTML = ""; });
  var submitBtn = document.createElement("button");
  submitBtn.className = "nav-btn-primary";
  submitBtn.textContent = "Opret";
  submitBtn.addEventListener("click", submitIntake);
  intakeBtns.appendChild(cancelBtn);
  intakeBtns.appendChild(submitBtn);
  intakeBox.appendChild(intakeBtns);
  intakeOverlay.appendChild(intakeBox);
  document.body.appendChild(intakeOverlay);

  // ── Intake: felter per type ───────────────────────────────────────────────

  function mkInput(id, placeholder, type) {
    var el = document.createElement("input");
    el.id = "nmi-" + id; el.type = type || "text"; el.placeholder = placeholder || "";
    return el;
  }
  function mkSelect(id, opts) {
    var el = document.createElement("select"); el.id = "nmi-" + id;
    opts.forEach(function (o) { var opt = document.createElement("option"); opt.value = o[0]; opt.textContent = o[1]; el.appendChild(opt); });
    return el;
  }
  function mkRow(lbl, input) {
    var row = document.createElement("div"); row.className = "nav-row";
    var l = document.createElement("label"); l.textContent = lbl;
    row.appendChild(l); row.appendChild(input); return row;
  }
  function val(id) { var el = document.getElementById("nmi-" + id); return el ? el.value.trim() : ""; }

  function renderFields(type) {
    fieldsDiv.innerHTML = "";
    if (type === "message") {
      fieldsDiv.appendChild(mkRow("Emne *",        mkInput("subject", "Beskriv henvendelsen kort")));
      fieldsDiv.appendChild(mkRow("Fra",            mkInput("sender_name", "Navn")));
      fieldsDiv.appendChild(mkRow("Telefon",        mkInput("sender_phone", "+45 12 34 56 78")));
      fieldsDiv.appendChild(mkRow("E-mail",         mkInput("sender_email", "navn@firma.dk", "email")));
      fieldsDiv.appendChild(mkRow("Kanal",          mkSelect("source", [["phone","Telefon"],["email","E-mail"],["walk_in","Personlig"],["referral","Anbefaling"],["website","Hjemmeside"],["other","Andet"]])));
    } else if (type === "project_task") {
      fieldsDiv.appendChild(mkRow("Titel *",        mkInput("title", "Hvad skal laves?")));
      fieldsDiv.appendChild(mkRow("Projekt-ID *",   mkInput("project_id", "Kopier fra projektsiden")));
      fieldsDiv.appendChild(mkRow("Beskrivelse",    mkInput("description", "Yderligere detaljer")));
      fieldsDiv.appendChild(mkRow("Tildelt til",    mkInput("assigned_to", "Medarbejdernavn")));
      fieldsDiv.appendChild(mkRow("Prioritet",      mkSelect("priority", [["normal","Normal"],["high","Høj"],["urgent","Akut"],["low","Lav"]])));
    } else {
      fieldsDiv.appendChild(mkRow("Titel *",        mkInput("title", "Hvad skal gøres?")));
      fieldsDiv.appendChild(mkRow("Beskrivelse",    mkInput("description", "Yderligere detaljer")));
      fieldsDiv.appendChild(mkRow("Tildelt til",    mkInput("assigned_to", "Medarbejdernavn")));
      fieldsDiv.appendChild(mkRow("Prioritet",      mkSelect("priority", [["normal","Normal"],["high","Høj"],["urgent","Akut"],["low","Lav"]])));
    }
  }

  typeSelect.addEventListener("change", function () { renderFields(typeSelect.value); });

  function openIntakeModal() {
    var tab = window._currentTab || new URLSearchParams(window.location.search).get("tab") || "";
    var suggested = TAB_TO_INTAKE[tab] || "internal_task";
    typeSelect.value = suggested;
    renderFields(suggested);
    intakeOverlay.classList.add("open");
  }

  function fmtError(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(function (e) { return ((e.loc||[]).slice(1).join("→")||"felt") + ": " + (e.msg||""); }).join("\n");
    if (detail && detail.message) return detail.message;
    return JSON.stringify(detail);
  }

  async function submitIntake() {
    var type = typeSelect.value;
    var payload = { type: type };
    if (type === "message") {
      var subj = val("subject"); if (!subj) { alert("Emne er påkrævet."); return; }
      payload.subject = subj; payload.source = val("source") || "phone";
      if (val("sender_name"))  payload.sender_name  = val("sender_name");
      if (val("sender_phone")) payload.sender_phone = val("sender_phone");
      if (val("sender_email")) payload.sender_email = val("sender_email");
    } else if (type === "project_task") {
      var t1 = val("title"), pid = val("project_id");
      if (!t1) { alert("Titel er påkrævet."); return; }
      if (!pid) { alert("Projekt-ID er påkrævet."); return; }
      payload.title = t1; payload.project_id = pid; payload.priority = val("priority") || "normal";
      if (val("description")) payload.description = val("description");
      if (val("assigned_to")) payload.assigned_to = val("assigned_to");
    } else {
      var t2 = val("title"); if (!t2) { alert("Titel er påkrævet."); return; }
      payload.title = t2; payload.priority = val("priority") || "normal";
      if (val("description")) payload.description = val("description");
      if (val("assigned_to")) payload.assigned_to = val("assigned_to");
    }
    try {
      var res = await fetch("/intake/", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: JSON.stringify(payload) });
      if (!res.ok) { var err = await res.json(); alert("Fejl:\n" + fmtError(err.detail || err)); return; }
      intakeOverlay.classList.remove("open");
      fieldsDiv.innerHTML = "";
      alert("Oprettet!");
    } catch (e) { alert("Netværksfejl: " + e.message); }
  }

  // ── Session / virksomhedsnavn ─────────────────────────────────────────────

  async function initNav() {
    try {
      var res = await fetch("/session/current", { credentials: "include" });
      if (res.ok) {
        var data = await res.json();
        companyName.textContent = data.company_name || "Virksomhed";
        if (data.company_id) {
          var coRes = await fetch("/companies/" + data.company_id, { credentials: "include" });
          if (coRes.ok) {
            var co = await coRes.json();
            if (co.logo_url) {
              var img = document.createElement("img");
              img.src = co.logo_url;
              img.alt = data.company_name || "Logo";
              img.style.cssText = "height:28px;max-width:110px;object-fit:contain;vertical-align:middle;";
              logo.textContent = "";
              logo.appendChild(img);
            }
          }
        }
      } else {
        companyName.textContent = "Ikke valgt";
      }
    } catch (_e) { /* vis default */ }
  }

  initNav();

})();
