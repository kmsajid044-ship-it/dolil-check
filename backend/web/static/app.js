// Shared helpers for the Dolil Check pages. Plain JS, no build step.

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
const bn = (v) => String(v ?? "").replace(/[0-9]/g, (d) => BN_DIGITS[d]);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel) => document.querySelector(sel);

const SEAL_ICON = `<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
  <circle cx="16" cy="13" r="9"/><path d="M11 13l3.5 3.5L21 10"/><path d="M11 21l-2 8 7-3 7 3-2-8"/></svg>`;

function renderHeader(active) {
  const links = [["/", "home", "ড্যাশবোর্ড"], ["/register", "register", "দলিল নিবন্ধন"], ["/mutation", "mutation", "নামজারি"], ["/v", "verify", "যাচাই"], ["/guide", "guide", "গাইড"]];
  document.body.insertAdjacentHTML("afterbegin", `
    <a class="skip" href="#main">মূল অংশে যান</a>
    <div class="sample">প্রোটোটাইপ: সব তথ্য কাল্পনিক, এটি কোনো সরকারি সেবা নয়। LandTech 2026, টিম এন্ট্রপি।</div>
    <header class="top"><div class="wrap">
      <a class="brand" href="/">${SEAL_ICON}<span>দলিল চেক</span></a>
      <div class="tools">
        <button type="button" class="iconbtn lang" id="lang-btn" lang="${LANG === "en" ? "bn" : "en"}">${LANG === "en" ? "বাংলা" : "EN"}</button>
        <button type="button" class="iconbtn" id="theme-btn"></button>
      </div>
      <nav>${links.map(([h, k, t]) => `<a href="${h}" class="${k === active ? "on" : ""}"${k === active ? ' aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
    </div></header>`);
  document.body.insertAdjacentHTML("beforeend", `
    <footer class="foot"><div class="wrap">
      <div><b>দলিল চেক</b><br>LandTech 2026 প্রোটোটাইপ, টিম এন্ট্রপি। সব নাম, জমি ও দলিল কাল্পনিক।</div>
      <div>Ed25519 স্বাক্ষর, SHA-256 হ্যাশ ও RFC 6962 মার্কেল লগ<br><a href="/api">API</a></div>
    </div></footer>`);
  revealOnScroll();
  themeSwitch();
  if (LANG === "en") translatePage();
}

// One icon button flips light/dark. Until it is clicked the page follows the system setting.
// The choice is a per-browser convenience, so localStorage is enough.
const MOON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>`;
const SUN = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`;
function themeSwitch() {
  const root = document.documentElement, btn = $("#theme-btn");
  const isDark = () => root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const show = () => {
    btn.innerHTML = isDark() ? SUN : MOON;
    btn.setAttribute("aria-label", tr(isDark() ? "আলো মোডে যান" : "অন্ধকার মোডে যান"));
    btn.title = btn.getAttribute("aria-label");
  };
  btn.onclick = () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("dolil-theme", root.dataset.theme); } catch {}
    show();
  };
  show();
  $("#lang-btn").onclick = () => {
    try { localStorage.setItem("dolil-lang", LANG === "en" ? "bn" : "en"); } catch {}
    location.reload();
  };
}

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Sections marked data-reveal fade up once when they scroll into view.
function revealOnScroll() {
  const items = document.querySelectorAll("[data-reveal]");
  if (REDUCED || !("IntersectionObserver" in window)) { items.forEach((el) => el.classList.add("shown")); return; }
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("shown"); io.unobserve(e.target); }
  }), { rootMargin: "0px 0px -8% 0px" });
  items.forEach((el) => io.observe(el));
}

// Counts a figure up from zero, in Bangla digits. Plain text when motion is reduced.
function countUp(el, n) {
  if (REDUCED || !n) { el.textContent = bn(n); return; }
  const start = performance.now(), dur = 1100;
  const step = (t) => {
    const k = Math.min(1, (t - start) / dur), eased = 1 - Math.pow(1 - k, 3);
    el.textContent = bn(Math.round(n * eased));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  let data;
  try { data = await res.json(); } catch { data = { error: "BAD_RESPONSE", message: `HTTP ${res.status}` }; }
  return { ok: res.ok, status: res.status, data };
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1]);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

const ERROR_BN = {
  DOUBLE_SALE: "দ্বিতীয় বিক্রি আটকানো হয়েছে: বিক্রেতা এই জমি আগেই বিক্রি করেছেন",
  OVER_SHARE: "বিক্রেতার অংশের চেয়ে বেশি জমি বিক্রির চেষ্টা আটকানো হয়েছে",
  NOT_OWNER: "বিক্রেতা এই জমির মালিক নন",
  UNKNOWN_PLOT: "এই জমি নিবন্ধনে নেই",
  UNKNOWN_DEED: "এই দলিল নিবন্ধনে নেই",
  INVALID_INPUT: "তথ্যে ভুল আছে",
  ALREADY_MUTATED: "এই দলিলের নামজারি আগেই হয়েছে",
};

const CHECK_BN = {
  qr_format: "QR কোডের ধরন",
  qr_signature: "QR-এর ডিজিটাল স্বাক্ষর",
  found: "নিবন্ধনে দলিলটি আছে",
  record_intact: "রেকর্ড সিলের পর অপরিবর্তিত",
  qr_matches_record: "QR ও নিবন্ধনের রেকর্ড মিলেছে",
  office_signature: "সাব-রেজিস্ট্রি অফিসের স্বাক্ষর",
  in_public_log: "পাবলিক লগে প্রমাণসহ আছে",
  document: "দলিলের ফাইল হুবহু একই",
};

// Verdict -> [colour class, stamp word, stamp sub-line]. The stamp is the first thing a buyer reads.
const VERDICT_STYLE = {
  GENUINE_CURRENT: ["good", "আসল", "সর্বশেষ হস্তান্তর"],
  GENUINE_SUPERSEDED: ["warn", "আসল", "পরে আবার বিক্রি হয়েছে"],
  ALTERED: ["bad", "পরিবর্তিত", "এই কপি বদলানো"],
  INVALID: ["bad", "অবৈধ", "নিবন্ধিত দলিল নয়"],
};

// One rubber-stamp result block, shared by verify, register and mutation pages.
// `say` is trusted HTML built by the caller (already escaped).
function stampHtml(cls, word, sub, say) {
  return `<div class="verdict ${cls}" role="status"><div class="stamp"><b>${esc(word)}</b><small>${esc(sub)}</small></div>
    <div class="say">${say}</div></div>`;
}

function plotLabel(pid) {
  const [m, jl, sv, dag] = String(pid).split("|");
  return `${m} · ${bn((jl || "").replace("JL ", "জেএল "))} · ${sv || ""} ${bn((dag || "").replace("dag ", "দাগ "))}`;
}

function areaBn(a) { return `${bn(a)} শতাংশ`; }

function partiesHtml(list) {
  return list.map((p) => `${esc(p.name)} <span class="muted mono">${esc(p.party_id)}</span> · ${areaBn((p.area_milli / 1000).toFixed(3))}`).join("<br>");
}

function deedSummaryHtml(d) {
  return `<table>
    <tr><th>দলিল নং</th><td class="mono">${esc(d.deed_id)}</td></tr>
    <tr><th>নিবন্ধনের তারিখ</th><td>${bn(d.reg_date)}</td></tr>
    <tr><th>জমি</th><td>মৌজা ${esc(d.mouza)} · জেএল ${bn(d.jl_no)} · ${esc(d.survey)} দাগ ${bn(d.dag_no)} · খতিয়ান ${bn(d.khatian_no)}</td></tr>
    <tr><th>বিক্রেতা</th><td>${partiesHtml(d.sellers)}</td></tr>
    <tr><th>ক্রেতা</th><td>${partiesHtml(d.buyers)}</td></tr>
    <tr><th>মূল্য</th><td>${bn(Number(d.consideration_bdt).toLocaleString("en-IN"))} টাকা</td></tr>
  </table>`;
}

function renderVerdict(el, r) {
  const [cls, word, sub] = VERDICT_STYLE[r.verdict] || VERDICT_STYLE.INVALID;
  let html = stampHtml(cls, word, sub, LANG === "en" ? `<p class="bn">${esc(r.message_en)}</p>`
    : `<p class="bn">${esc(r.message_bn)}</p><p class="en">${esc(r.message_en)}</p>`) + `
    <div class="grid two">
      <div class="card"><h2 style="margin-top:0">যা যাচাই হয়েছে</h2><ul class="checks">
        ${r.checks.map((c) => `<li><span class="${c.ok ? "ok" : "no"}">${c.ok ? "✓" : "✗"}</span>
          <span><b>${esc(CHECK_BN[c.check] || c.check)}</b><br><span class="muted" style="font-size:13px">${esc(c.detail)}</span></span></li>`).join("")}
      </ul></div>`;
  if (r.deed) {
    const m = r.mutation;
    html += `<div class="card"><h2 style="margin-top:0">দলিলের তথ্য</h2>${deedSummaryHtml(r.deed)}
      <h2>নামজারি</h2><p>${m ? `<span class="pill good">সম্পন্ন</span> ${bn(m.date)} · <span class="mono">${esc(m.mutation_id)}</span>`
        : `<span class="pill warn">এখনো হয়নি</span>`}</p></div>`;
  }
  html += `</div>`;
  if (r.current_holders) {
    html += `<div class="card" style="margin-top:16px"><h2 style="margin-top:0">এই জমির বর্তমান মালিক</h2><table>
      <tr><th>নাম</th><th>আইডি</th><th>অংশ</th></tr>
      ${r.current_holders.map((h) => `<tr><td>${esc(h.name)}</td><td class="mono">${esc(h.party_id)}</td><td>${areaBn(h.area)}</td></tr>`).join("")}
    </table>
    ${r.later_transfers_by_buyers?.length ? `<p class="muted">পরের হস্তান্তর: ${r.later_transfers_by_buyers.map((x) => `<a class="mono" href="/v?deed=${encodeURIComponent(x)}">${esc(x)}</a>`).join(", ")}</p>` : ""}
    </div>`;
  }
  el.innerHTML = html;
}

function renderError(el, data) {
  const d = data.detail || {};
  let extra = "";
  if (d.earlier_sale) extra += `<p>আগের বিক্রির দলিল: <a class="mono" href="/v?deed=${encodeURIComponent(d.earlier_sale)}">${esc(d.earlier_sale)}</a></p>`;
  if (d.holds && d.tried_to_sell) extra += `<p>বিক্রেতার আছে ${areaBn(d.holds)}, বিক্রি করতে চেয়েছেন ${areaBn(d.tried_to_sell)}।</p>`;
  if (d.current_holders?.length) extra += `<p class="muted">বর্তমান মালিক: ${d.current_holders.map((h) => `${esc(h.name)} (${areaBn(h.area)})`).join(", ")}</p>`;
  el.innerHTML = stampHtml("bad", "বাতিল", "সিল করা হয়নি",
    `<p class="bn">${esc(ERROR_BN[data.error] || "অনুরোধটি বাতিল হয়েছে")}</p>
     <p class="en">${esc(data.error || "")}: ${esc(data.message || "")}</p>${extra}`);
}


// ---------------------------------------------------------------- English / Bangla
// Pages are written in Bangla. In English mode we translate the rendered page with one phrase
// dictionary, so there is a single place to add a translation. Data (names, mouzas) stays as entered.
const LANG = (() => { try { return localStorage.getItem("dolil-lang") === "en" ? "en" : "bn"; } catch { return "bn"; } })();
document.documentElement.lang = LANG;

const EN = {
  // shell
  "প্রোটোটাইপ: সব তথ্য কাল্পনিক, এটি কোনো সরকারি সেবা নয়। LandTech 2026, টিম এন্ট্রপি।": "Prototype: all data is fictional and this is not a government service. LandTech 2026, Team Entropy.",
  "মূল অংশে যান": "Skip to content", "দলিল চেক": "Dolil Check", "ড্যাশবোর্ড": "Dashboard", "দলিল নিবন্ধন": "Register deed",
  "নামজারি": "Mutation", "যাচাই": "Verify", "আলো মোডে যান": "Switch to light mode", "অন্ধকার মোডে যান": "Switch to dark mode",
  "LandTech 2026 প্রোটোটাইপ, টিম এন্ট্রপি। সব নাম, জমি ও দলিল কাল্পনিক।": "LandTech 2026 prototype, Team Entropy. All names, land and deeds are fictional.",
  "Ed25519 স্বাক্ষর, SHA-256 হ্যাশ ও RFC 6962 মার্কেল লগ": "Ed25519 signatures, SHA-256 hashes and an RFC 6962 Merkle log",
  // guide
  "ও": "and", "গাইড": "Guide", "দলিল নং, নামজারি কেস নং ও তারিখ লিখুন।": "Enter the deed no., the mutation case no. and the date.", "ব্যবহার নির্দেশিকা": "User guide", "সবার জন্য": "For everyone", "কীভাবে ব্যবহার করবেন": "How to use Dolil Check",
  "সাইটে তিন ধরনের ব্যবহারকারী আছেন, প্রত্যেকের কাজ আলাদা। আপনার অফিস বা ভূমিকা বেছে নিন।": "The site has three kinds of users, each with a different job. Pick your office or role.",
  "দলিল নিবন্ধন ও সিল": "Register and seal a deed", "নামজারি সিল ও বাকি নামজারির তালিকা": "Seal mutations and see the pending list",
  "দলিল যাচাই ও ফলাফল বোঝা": "Verify a deed and read the result",
  "সাব-রেজিস্ট্রি অফিস: দলিল নিবন্ধন ও সিল": "Sub-registry office: register and seal a deed",
  "মেনু থেকে": "From the menu, open", "খুলুন। ফর্মে চারটি ধাপ আছে:": ". The form has four steps:", "খুলুন।": ".",
  "মৌজা ও দাগ নং বাছুন, খতিয়ান নং দিন। নিচে জমির মোট পরিমাণ দেখাবে।": "Pick the mouza and dag no., and enter the khatian no. The plot's total area appears below.",
  "তালিকায় শুধু এই জমির বর্তমান মালিকরাই আছেন। একজনকে বেছে কতটুকু বিক্রি হচ্ছে লিখুন।": "The list only shows this plot's current holders. Pick one and enter how much is being sold.",
  "ক্রেতার নাম ও পরিচয় নং দিন।": "Enter the buyer's name and ID no.",
  "তারিখ, মূল্য ও স্ক্যান করা দলিলের PDF দিন। PDF দিলে পরে একটি অক্ষর বদলালেও ধরা পড়বে।": "Enter the date, price and the scanned deed PDF. With the PDF, even one changed character is caught later.",
  "তারপর": "Then press", "চাপুন।": ".",
  "সফল হলে QR কোড আসবে।": "On success a QR code appears.", "চেপে QR-সহ সনদ প্রিন্ট করে ক্রেতাকে দিন।": "to print the certificate with its QR and hand it to the buyer.",
  "নিবন্ধন আটকে গেলে কারণ দেখাবে। নিচের তালিকায় তিনটি কারণের মানে দেওয়া আছে।": "If registration is blocked, the reason is shown. The table below explains the three reasons.",
  "কারণ": "Reason", "মানে": "Meaning",
  "বিক্রেতা এই জমি আগেই বিক্রি করেছেন। আগের দলিলের নম্বরও দেখাবে।": "The seller already sold this land. The earlier deed number is shown too.",
  "বিক্রেতার যতটুকু আছে, তার চেয়ে বেশি বিক্রির চেষ্টা।": "An attempt to sell more than the seller holds.", "বিক্রেতা এই জমির মালিকই নন।": "The seller does not own this land at all.",
  "এসি ল্যান্ড অফিস: নামজারি": "AC Land office: mutation",
  "সহজ উপায়: নিচের": "Shortcut: in the", "তালিকা থেকে": "list below, press", "চাপলে দলিল নং নিজেই বসে যায়। নিবন্ধনের ৬০ দিন পরেও যেসব দলিলের নামজারি হয়নি, সেগুলো এই তালিকায় থাকে।": "and the deed number fills itself in. Deeds still without a mutation 60 days after registration are on this list.",
  "সফল হলে দলিলের সাথে যুক্ত হয়ে নামজারি সিল হয়। এরপর দলিলটি যাচাই করলে নামজারি সম্পন্ন দেখাবে।": "On success the mutation is sealed together with its deed. Verifying the deed then shows the mutation as done.",
  "দলিলটি নিবন্ধনে না থাকলে, বা আগেই নামজারি হয়ে থাকলে নামজারি বাতিল হয়। বাতিলগুলো পেজের নিচে জমা থাকে।": "A mutation is refused if the deed is not registered or already has a mutation. Refusals are listed at the bottom of the page.",
  "ক্রেতা, ব্যাংক বা আদালত: দলিল যাচাই": "Buyer, bank or court: verify a deed",
  "সবচেয়ে সহজ:": "Easiest:", "ফোনের ক্যামেরায় দলিলে ছাপা QR কোড স্ক্যান করুন। যাচাই পাতা নিজেই খুলবে।": "Scan the QR code printed on the deed with a phone camera. The verify page opens by itself.",
  "হাতে লিখে:": "By hand:", "খুলে দলিল নং বা QR-এর লেখা দিন, তারপর": "and enter the deed number or the QR text, then press",
  "কপি মেলাতে:": "To check a copy:", "হাতের দলিলের PDF দিন। ফাইলটি শুধু মেলানোর জন্য যায়, কোথাও জমা থাকে না।": "Add the PDF of the deed you hold. It is only used for comparison and is not stored.",
  "ফলাফল কীভাবে পড়বেন": "How to read the result",
  "দলিল আসল, আর এটিই জমির সর্বশেষ বিক্রি। নিশ্চিন্তে এগোতে পারেন।": "The deed is genuine and it is the latest sale of this land. Safe to proceed.",
  "দলিল আসল, কিন্তু জমিটি পরে আবার বিক্রি হয়েছে। নিচে বর্তমান মালিক দেখে নিন।": "The deed is genuine, but the land was sold again later. Check the current holders below it.",
  "দলিল নিবন্ধিত, কিন্তু আপনার হাতের কপিটি বদলানো। এই কপিতে ভরসা করবেন না।": "The deed is registered, but the copy you hold was changed. Do not rely on this copy.",
  "এটি নিবন্ধিত দলিলই নয়, বা QR নকল। লেনদেন করবেন না।": "This is not a registered deed, or the QR is fake. Do not go ahead.",
  "ফলাফলের নিচে দেখা যায়: কী কী যাচাই হয়েছে, দলিলের সব তথ্য, নামজারি হয়েছে কি না, আর": "Under the result you see what was checked, the full deed details, whether the mutation is done, and",
  "এই জমির এখনকার মালিক কারা": "who holds this land now",
  "ভাষা:": "Language:", "উপরে ডানদিকের EN বা বাংলা বোতাম চাপুন।": "press the EN or বাংলা button at the top right.",
  "আলো বা অন্ধকার:": "Light or dark:", "পাশের চাঁদ বা সূর্য আইকন চাপুন।": "press the moon or sun icon next to it.",
  "ড্যাশবোর্ড:": "Dashboard:", "কতগুলো দলিল সিল হয়েছে, কতগুলো জালিয়াতি আটকানো হয়েছে, কতগুলো নামজারি বাকি, এক নজরে দেখায়।": "shows at a glance how many deeds are sealed, how many frauds were blocked and how many mutations are pending.",
  "এই সাইটের সব নাম, জমি ও দলিল কাল্পনিক। এটি একটি প্রোটোটাইপ, কোনো সরকারি সেবা নয়।": "Every name, plot and deed on this site is fictional. This is a prototype, not a government service.",
  "নামজারি কেস নং": "Mutation case no.",
  // dashboard
  "জমির দলিল আসল কি না, এক স্ক্যানে জানুন": "Know if a land deed is genuine, in one scan",
  "প্রতিটি নিবন্ধিত দলিলে একটি স্বাক্ষরিত QR কোড থাকে। স্ক্যান করলে দেখা যায় দলিলটি আসল কি না, কেউ বদলেছে কি না, আর এটিই সর্বশেষ হস্তান্তর কি না। একই জমি দ্বিতীয়বার বিক্রির চেষ্টা নিবন্ধনের সময়ই আটকে যায়।": "Every registered deed carries a signed QR code. One scan shows whether the deed is genuine, whether anyone changed it, and whether it is the latest transfer. A second sale of the same land is stopped at registration.",
  "দলিল নং বা QR-এর লেখা": "Deed number or QR text", "দলিল নং, যেমন SRO-NDP-2026-00227": "Deed number, e.g. SRO-NDP-2026-00227",
  "যাচাই করুন": "Verify", "সিল করা দলিল": "Sealed deeds", "পাবলিক লগের এন্ট্রি": "Public log entry",
  "আটকানো জালিয়াতির চেষ্টা": "Fraud attempts blocked", "নামজারি বাকি,": "Mutation pending,", "দিনের বেশি": "days or more",
  "কোন অফিস থেকে কাজ করছেন?": "Which office are you working from?",
  "সাব-রেজিস্ট্রি অফিস": "Sub-registry office", "এসি ল্যান্ড অফিস": "AC Land office", "ক্রেতা, ব্যাংক বা আদালত": "Buyer, bank or court",
  "বিক্রেতার অংশ মিলিয়ে দলিল সিল করুন, QR-সহ সনদ প্রিন্ট করুন।": "Check the seller's share, seal the deed and print a certificate with its QR.",
  "দলিলের সাথে যুক্ত করে নামজারি সিল করুন, বাকি নামজারির তালিকা দেখুন।": "Seal a mutation linked to its deed and see pending mutations.",
  "QR স্ক্যান বা দলিলের ফাইল দিয়ে কয়েক সেকেন্ডে যাচাই করুন।": "Verify in seconds with a QR scan or the deed file.",
  "সম্প্রতি আটকানো চেষ্টা": "Recently blocked attempts", "নামজারি বাকি থাকা দলিল": "Deeds awaiting mutation",
  "পাবলিক লগ": "Public log", "টি এন্ট্রি আছে সর্বশেষ স্বাক্ষরিত ট্রি হেডে। এর রুট হ্যাশ:": " entries in the latest signed tree head. Its root hash:",
  "এই রুট হ্যাশ প্রতিদিন বাইরে প্রকাশ হলে অফিস নিজেও গোপনে পুরোনো রেকর্ড বদলাতে পারে না।": "Once this root hash is published daily, not even the office can quietly rewrite old records.",
  "এখনো কোনো চেষ্টা নেই": "No attempts yet", "দ্বিতীয় বিক্রি": "Second sale", "অংশের বেশি বিক্রি": "Sold more than held",
  "মালিক নন": "Not the owner", "দলিলহীন নামজারি": "Mutation without deed", "দ্বিতীয় নামজারি": "Second mutation",
  // table heads and common words
  "সময়": "Time", "ধরন": "Type", "বিবরণ": "Details", "দলিল নং": "Deed no.", "বাকি": "Pending", "জমি": "Land",
  "নিবন্ধন": "Registered", "নাম": "Name", "আইডি": "ID", "অংশ": "Share", "কিছু নেই": "Nothing here",
  // register
  "সাব-রেজিস্ট্রি অফিস, SRO-NDP (কাল্পনিক)": "Sub-registry office, SRO-NDP (fictional)", "দলিল নিবন্ধন ও সিল": "Register and seal a deed",
  "বিক্রেতার বর্তমান অংশ মিলিয়ে দলিল সিল হয়। বেশি জমি বা আগেই বিক্রি করা জমি নিবন্ধন হয় না।": "A deed is sealed only after the seller's current share is checked. Land sold twice, or more than the seller holds, cannot be registered.",
  "মৌজা": "Mouza", "দাগ নং": "Dag no.", "খতিয়ান নং": "Khatian no.", "বিক্রেতা": "Seller", "ক্রেতা": "Buyer", "দলিল": "Deed",
  "বর্তমান মালিকদের মধ্যে থেকে": "From the current holders", "বিক্রির পরিমাণ (শতাংশ)": "Area sold (decimal)",
  "পরিচয় নং (কাল্পনিক)": "ID no. (fictional)", "যেমন: করিম মিয়া": "e.g. Karim Mia", "নিবন্ধনের তারিখ": "Registration date",
  "মূল্য (টাকা)": "Price (Tk)", "স্ক্যান করা দলিল (PDF, ঐচ্ছিক)": "Scanned deed (PDF, optional)",
  "ফাইলের ফিঙ্গারপ্রিন্ট (SHA-256) দলিলের সাথে সিল হয়। পরে একটি অক্ষর বদলালেও যাচাইয়ে ধরা পড়বে।": "The file's fingerprint (SHA-256) is sealed with the deed. Changing even one character later is caught at verification.",
  "দলিল সিল করুন": "Seal deed", "দলিল সিল হয়েছে": "Deed sealed", "দলিলের ফাইলও সিল হয়েছে।": "The deed file was sealed too.",
  "কোনো ফাইল দেওয়া হয়নি।": "No file was attached.", "রেকর্ড হ্যাশ": "Record hash", "সনদ প্রিন্ট করুন": "Print certificate",
  "এখনই যাচাই করুন": "Verify now", "একই জমি আবার বিক্রির চেষ্টা (ডেমো)": "Try selling the same land again (demo)",
  "দ্বিতীয় দলিল সিল হয়েছে:": "Second deed sealed:", "বিক্রেতার আরও জমি ছিল": "the seller had more land",
  "এই বিক্রেতার আছে": "This seller holds", "মোট": "Total",
  // mutation
  "এসি ল্যান্ড অফিস, ACL-NDP (কাল্পনিক)": "AC Land office, ACL-NDP (fictional)", "নামজারি এন্ট্রি": "Record a mutation",
  "নামজারি শুধু নিবন্ধিত দলিলের জন্যই হয়। প্রতিটি নামজারি দলিলের হ্যাশের সাথে যুক্ত হয়ে সিল হয়।": "A mutation is only possible for a registered deed, and each one is sealed together with that deed's hash.",
  "নামজারি কেস নং": "Mutation case no.", "তারিখ": "Date", "নামজারি সিল করুন": "Seal mutation", "নামজারি সিল হয়েছে": "Mutation sealed",
  "দলিলটি যাচাই করে দেখুন": "Verify the deed", "নামজারি করুন": "Record mutation", "বাতিল হওয়া নামজারি": "Refused mutations",
  "দলিল নেই, বা আগেই নামজারি হয়েছে।": "No such deed, or the mutation was already done.",
  // verify
  "ক্রেতা, ব্যাংক ও আদালতের জন্য": "For buyers, banks and courts", "দলিল যাচাই": "Verify a deed",
  "ফোনের ক্যামেরায় দলিলের QR স্ক্যান করলে এই পাতা নিজেই খোলে। দলিলের ফাইল দিলে মিলিয়ে দেখা হয়, একটি অক্ষর বদলালেও ধরা পড়ে।": "Scanning the deed's QR with a phone camera opens this page. Add the deed file to compare it too; a single changed character is caught.",
  "QR কোডের লেখা, লিংক, বা দলিল নং": "QR text, link or deed number", "ক্যামেরায় QR স্ক্যান": "Scan QR with camera",
  "QR-এর ছবি থেকে": "From a photo of the QR", "দলিলের ফাইল (ঐচ্ছিক)": "Deed file (optional)",
  "ফাইলটি এই ব্রাউজার থেকে সার্ভারে যায় শুধু ফিঙ্গারপ্রিন্ট মেলানোর জন্য; সংরক্ষণ করা হয় না।": "The file is sent to the server only to compare fingerprints; it is not stored.",
  "যাচাই হচ্ছে…": "Verifying…", "ছবিতে QR কোড পাওয়া যায়নি।": "No QR code found in the photo.", "ক্যামেরা চালু করা যায়নি।": "Could not start the camera.",
  "যা যাচাই হয়েছে": "What was checked", "দলিলের তথ্য": "Deed details", "এই জমির বর্তমান মালিক": "Current holders of this land",
  "সম্পন্ন": "Done", "এখনো হয়নি": "Not yet", "পরের হস্তান্তর:": "Later transfers:", "নিবন্ধনের": "Registration",
  "বিক্রয় দলিলের সিল সনদ": "Sale deed seal certificate", "প্রিন্ট / PDF হিসেবে সেভ": "Print / save as PDF", "যাচাই পাতা": "Verify page",
  "দলিল চেক প্রোটোটাইপ": "Dolil Check prototype", "কাল্পনিক তথ্য": "fictional data", "ফোনের ক্যামেরায় স্ক্যান করে": "Scan with a phone camera",
  "ডিজিটাল সিল": "Digital seal", "পাবলিক লগ এন্ট্রি": "Public log entry", "লগে মোট": "log size", "রেকর্ড হ্যাশ (SHA-256)": "Record hash (SHA-256)",
  "দলিলের ফাইলের ফিঙ্গারপ্রিন্ট": "Deed file fingerprint", "অফিসের কী": "Office key", "স্বাক্ষর": "Signature", "নমুনা": "SAMPLE",
  "এই সনদের কোনো তথ্য বদলালে QR স্ক্যানে তা ধরা পড়বে। একই জমি আবার বিক্রির চেষ্টা নিবন্ধনের সময়ই আটকে যায়।": "Any change to this certificate is caught by a QR scan. A second sale of the same land is stopped at registration.",
  "অথবা": "or", "লোড হচ্ছে…": "Loading…", "দলিল চেক ·": "Dolil Check ·", "সিল সনদ": "Seal certificate",
  // deed summary rows
  "বিক্রেতা ": "Seller ", "মূল্য": "Price", "টাকা": "Tk", "শতাংশ": "decimal", "জেএল": "JL", "দাগ": "dag", "খতিয়ান": "khatian", "দিন": "days",
  // verdicts, stamps and errors
  "আসল": "Genuine", "সর্বশেষ হস্তান্তর": "latest transfer", "পরে আবার বিক্রি হয়েছে": "sold again later",
  "পরিবর্তিত": "Altered", "এই কপি বদলানো": "this copy was changed", "অবৈধ": "Invalid", "নিবন্ধিত দলিল নয়": "not a registered deed",
  "বাতিল": "Refused", "সিল করা হয়নি": "nothing was sealed", "সিল": "Sealed", "দলিল নিবন্ধিত": "deed registered", "সিল হয়েছে": "sealed",
  "অনুরোধটি বাতিল হয়েছে": "The request was refused",
  "দ্বিতীয় বিক্রি আটকানো হয়েছে: বিক্রেতা এই জমি আগেই বিক্রি করেছেন": "Second sale blocked: the seller already sold this land",
  "বিক্রেতার অংশের চেয়ে বেশি জমি বিক্রির চেষ্টা আটকানো হয়েছে": "Blocked: the seller tried to sell more than they hold",
  "বিক্রেতা এই জমির মালিক নন": "The seller does not own this land", "এই জমি নিবন্ধনে নেই": "This land is not in the registry",
  "এই দলিল নিবন্ধনে নেই": "This deed is not in the registry", "তথ্যে ভুল আছে": "Some details are wrong",
  "এই দলিলের নামজারি আগেই হয়েছে": "This deed already has a mutation", "আগের বিক্রির দলিল:": "Earlier sale deed:",
  "বিক্রেতার আছে": "The seller holds", "বিক্রি করতে চেয়েছেন": "tried to sell", "বর্তমান মালিক:": "Current holders:",
  "QR কোডের ধরন": "QR code format", "QR-এর ডিজিটাল স্বাক্ষর": "QR digital signature", "নিবন্ধনে দলিলটি আছে": "Deed is in the registry",
  "রেকর্ড সিলের পর অপরিবর্তিত": "Record unchanged since sealing", "QR ও নিবন্ধনের রেকর্ড মিলেছে": "QR matches the registry record",
  "সাব-রেজিস্ট্রি অফিসের স্বাক্ষর": "Sub-registry office signature", "পাবলিক লগে প্রমাণসহ আছে": "Proven in the public log",
  "দলিলের ফাইল হুবহু একই": "Deed file is byte-for-byte the same",
};
// Longest phrases first, matched only at Bangla word edges so "দিন" never touches a name like "উদ্দিন".
const EN_RULES = [
  [/আরও ([০-৯0-9]+)টি/g, "$1 more"], [/([০-৯0-9]+)টি রেকর্ড/g, "$1 records"],
  ...Object.keys(EN).sort((a, b) => b.length - a.length).map((k) => [
    new RegExp(`(?<![\\u0980-\\u09E5])${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\u0980-\\u09E5])`, "g"), EN[k]]),
];
function tr(text) {
  if (LANG !== "en" || !/[ঀ-৿]/.test(text)) return text;
  let out = text;
  for (const [re, en] of EN_RULES) out = out.replace(re, en);
  return out.replace(/[০-৯]/g, (d) => "০১২৩৪৫৬৭৮৯".indexOf(d)).replace(/।/g, ".").replace(/ +([.,])/g, "$1");
}
function translateNode(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.parentElement?.closest("script, style, textarea, .mono")) continue;
    const t = tr(n.nodeValue);
    if (t !== n.nodeValue) n.nodeValue = t;
  }
  if (root.querySelectorAll) root.querySelectorAll("[placeholder], [aria-label], [alt], [title]").forEach((el) => {
    for (const a of ["placeholder", "aria-label", "alt", "title"]) {
      const v = el.getAttribute(a);
      if (v && tr(v) !== v) el.setAttribute(a, tr(v));
    }
  });
}
// Translate now, then keep translating whatever the page renders later (results, tables, counters).
function translatePage() {
  document.title = tr(document.title);
  translateNode(document.body);
  new MutationObserver((muts) => muts.forEach((m) => {
    if (m.type === "characterData") { const t = tr(m.target.nodeValue); if (t !== m.target.nodeValue) m.target.nodeValue = t; }
    m.addedNodes.forEach((n) => n.nodeType === 3 ? (n.nodeValue = tr(n.nodeValue)) : n.nodeType === 1 && translateNode(n));
  })).observe(document.body, { childList: true, subtree: true, characterData: true });
}
