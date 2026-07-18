/* popup.js — สถานะและควบคุมด่วน */
const $ = (id) => document.getElementById(id);

function send(type) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type }, (res) => resolve(res || { ok: false }));
  });
}

async function init() {
  // สถานะเปิด/ปิด
  chrome.storage.local.get({ enabled: true, backendUrl: "http://127.0.0.1:8000" }, (v) => {
    $("enabled").checked = v.enabled !== false;
  });
  $("enabled").addEventListener("change", (e) => {
    chrome.storage.local.set({ enabled: e.target.checked });
  });

  $("openDash").addEventListener("click", () => {
    chrome.storage.local.get({ backendUrl: "http://127.0.0.1:8000" }, (v) => {
      chrome.tabs.create({ url: v.backendUrl });
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
      ? "AI: เชื่อมต่อ BytePlus ModelArk แล้ว"
      : "AI: ใช้ Regex/Fingerprint (ยังไม่ตั้งค่าคีย์)";
  } else {
    $("connDot").className = "dot err";
    $("connText").textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — รัน backend หรือยัง?";
    $("aiText").textContent = "AI: ไม่ทราบสถานะ";
  }

  const stats = await send("stats");
  if (stats.ok) {
    $("det").textContent = (stats.data.detections_30d || 0).toLocaleString("th-TH");
    $("blk").textContent = (stats.data.blocks_30d || 0).toLocaleString("th-TH");
  }
}

init();
