/*
 * background.js — Service Worker (MV3)
 * เป็นตัวกลางเรียก backend ของ SentinelAI (มี host_permission ให้ localhost)
 * เพื่อเลี่ยงปัญหา mixed-content (หน้า https เรียก http://127.0.0.1) และ CORS
 */

const DEFAULTS = {
  enabled: true,
  backendUrl: "http://127.0.0.1:8000",
  orgKey: "",          // API key ขององค์กร (SaaS) — จากหน้า "ตั้งค่า & เชื่อมต่อ" ใน Dashboard
  user: "unknown",
  department: "",
  device: "",
  failOpen: true,
};

async function getCfg() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULTS, (v) => resolve(Object.assign({}, DEFAULTS, v || {})));
  });
}

function apiBase(cfg) {
  return (cfg.backendUrl || DEFAULTS.backendUrl).replace(/\/+$/, "") + "/api/v1";
}

async function callInspect(payload) {
  const cfg = await getCfg();
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
