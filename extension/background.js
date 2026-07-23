/*
 * background.js — Service Worker (MV3)
 * เป็นตัวกลางเรียก backend ของ SentinelAI (มี host_permission ให้ localhost)
 * เพื่อเลี่ยงปัญหา mixed-content (หน้า https เรียก http://127.0.0.1) และ CORS
 */

const DEFAULTS = {
  enabled: true,
  backendUrl: "https://sentinelai.help",
  orgKey: "",          // API key ขององค์กร (SaaS) — จากหน้า "ตั้งค่า & เชื่อมต่อ" ใน Dashboard
  user: "unknown",
  department: "",
  device: "",
  failOpen: true,
};

// อ่านค่านโยบายองค์กร (ตั้งผ่าน Group Policy / Google Admin) — ผู้ใช้แก้ไม่ได้
function getManaged() {
  return new Promise((resolve) => {
    try {
      chrome.storage.managed.get(null, (v) =>
        resolve(!chrome.runtime.lastError && v ? v : {}));
    } catch (e) { resolve({}); }
  });
}

async function getCfg() {
  const [local, managed] = await Promise.all([
    new Promise((r) => chrome.storage.local.get(DEFAULTS, (v) => r(v || {}))),
    getManaged(),
  ]);
  // นโยบายองค์กร (managed) มีอำนาจเหนือค่าที่ผู้ใช้ตั้งเอง (local) — ปิด/แก้ไม่ได้
  const cfg = Object.assign({}, DEFAULTS, local, managed);
  cfg.enforced = managed.enforced === true;
  if (cfg.enforced) {
    cfg.enabled = managed.enabled !== false;                    // บังคับเปิด (เว้นแอดมินสั่งปิดเอง)
    cfg.failOpen = managed.failOpen === true;                   // โหมดบังคับ = fail-closed เป็นค่าเริ่มต้น
  }
  return cfg;
}

function apiBase(cfg) {
  return (cfg.backendUrl || DEFAULTS.backendUrl).replace(/\/+$/, "") + "/api/v1";
}

// ลายนิ้วมือเบราว์เซอร์แบบคงที่ (กันแชร์คีย์: 1 โปรไฟล์ = 1 สิทธิ์)
async function getDeviceFp() {
  const got = await chrome.storage.local.get("deviceFp");
  if (got && got.deviceFp) return got.deviceFp;
  const rand = (self.crypto && crypto.randomUUID)
    ? crypto.randomUUID().replace(/-/g, "")
    : (Date.now().toString(36) + Math.random().toString(36).slice(2, 12));
  const fp = "ext_" + rand;
  await chrome.storage.local.set({ deviceFp: fp });
  return fp;
}

async function callInspect(payload) {
  const cfg = await getCfg();
  const fp = await getDeviceFp();
  // ผูก identity จริงของเครื่อง/โปรไฟล์ + เติมค่าตัวตนจากการตั้งค่า (กันเว้นว่าง)
  payload = Object.assign({}, payload, {
    device_fp: fp,
    device: (payload && payload.device) || cfg.device || fp,
    user: (payload && payload.user) || cfg.user,
    department: (payload && payload.department) || cfg.department,
  });
  const headers = { "Content-Type": "application/json" };
  if (cfg.orgKey) headers["X-Sentinel-Key"] = cfg.orgKey;  // ส่งเข้าองค์กรที่ถูกต้อง (SaaS)
  const res = await fetch(apiBase(cfg) + "/inspect", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function callGet(path, query) {
  const cfg = await getCfg();
  let url = apiBase(cfg) + path;
  if (query) url += "?" + new URLSearchParams(query).toString();
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

let sessionInterventions = 0;
function bumpBadge(decision) {
  if (["warn", "redact", "block"].includes(decision)) {
    sessionInterventions++;
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
    chrome.action.setBadgeText({ text: String(sessionInterventions) });
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "inspect") {
        const data = await callInspect(msg.payload);
        bumpBadge(data.decision);
        sendResponse({ ok: true, data });
      } else if (msg.type === "stats") {
        sendResponse({ ok: true, data: await callGet("/stats") });
      } else if (msg.type === "config") {
        sendResponse({ ok: true, data: await callGet("/config") });
      } else if (msg.type === "health") {
        sendResponse({ ok: true, data: await callGet("/health") });
      } else {
        sendResponse({ ok: false, error: "unknown message type" });
      }
    } catch (e) {
      sendResponse({ ok: false, error: String(e && e.message ? e.message : e) });
    }
  })();
  return true; // ใช้ sendResponse แบบ async
});

chrome.runtime.onInstalled.addListener(async () => {
  const cur = await getCfg();
  chrome.storage.local.set(cur); // เขียนค่าเริ่มต้นถ้ายังไม่มี
  chrome.action.setBadgeText({ text: "" });
});
