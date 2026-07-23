/* popup.js — สถานะ + ใส่คีย์องค์กรได้ในตัว */
const $ = (id) => document.getElementById(id);
const DEFAULT_BACKEND = "https://sentinelai.help";

function send(type) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type }, (res) => resolve(res || { ok: false }));
  });
}

/* สลับหน้าตากล่องคีย์: มีคีย์แล้ว → แสดงแบบย่อ, ยังไม่มี → แสดงช่องกรอก */
function renderKey(hasKey) {
  $("keyDone").hidden = !hasKey;
  $("keyForm").hidden = hasKey;
}

async function loadStats() {
  const stats = await send("stats");
  if (stats.ok) {
    $("det").textContent = (stats.data.detections_30d || 0).toLocaleString("th-TH");
    $("blk").textContent = (stats.data.blocks_30d || 0).toLocaleString("th-TH");
  }
}

async function init() {
  chrome.storage.local.get({ enabled: true, backendUrl: DEFAULT_BACKEND, orgKey: "" }, (v) => {
    $("enabled").checked = v.enabled !== false;
    $("orgKey").value = v.orgKey || "";
    renderKey(!!(v.orgKey && v.orgKey.trim()));
  });

  $("enabled").addEventListener("change", (e) => {
    chrome.storage.local.set({ enabled: e.target.checked });
  });

  // บันทึกคีย์ในตัว popup
  $("saveKey").addEventListener("click", () => {
    const key = $("orgKey").value.trim();
    if (!key) { $("orgKey").focus(); return; }
    const btn = $("saveKey");
    chrome.storage.local.set({ orgKey: key }, () => {
      renderKey(true);
      btn.textContent = "บันทึก & เชื่อมต่อ";
      loadStats();
    });
  });
  $("orgKey").addEventListener("keydown", (e) => { if (e.key === "Enter") $("saveKey").click(); });
  $("editKey").addEventListener("click", () => renderKey(false));

  $("openDash").addEventListener("click", () => {
    chrome.storage.local.get({ backendUrl: DEFAULT_BACKEND }, (v) => {
      chrome.tabs.create({ url: v.backendUrl || DEFAULT_BACKEND });
    });
  });
  $("openOpts").addEventListener("click", () => chrome.runtime.openOptionsPage());

  // เชื่อมต่อ backend
  const health = await send("health");
  if (health.ok) {
    $("connDot").className = "dot ok";
    $("connText").textContent = "เชื่อมต่อเซิร์ฟเวอร์แล้ว";
    $("ver").textContent = health.data.version || "1.0";
    const ai = health.data.ai_enabled;
    $("aiDot").className = "ai-dot " + (ai ? "on" : "off");
    $("aiText").textContent = ai
      ? "ระบบ AI พร้อมป้องกัน"
      : "โหมดพื้นฐาน: Regex/Fingerprint";
  } else {
    $("connDot").className = "dot err";
    $("connText").textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — ลองใหม่ภายหลัง";
    $("aiText").textContent = "ระบบ AI: ไม่ทราบสถานะ";
  }

  loadStats();
}

init();
