/*
 * interceptor.js — ดักจับก่อนข้อมูลถูกส่งไป AI (หัวใจของ Browser Extension, โมดูล M2/M4)
 * จับ 2 ช่องทาง: (1) การวาง (paste)  (2) การกดส่ง (Enter / ปุ่ม Send)
 * ส่งเนื้อหาให้ background -> backend /inspect -> บังคับตามผล (allow/warn/redact/block)
 */
(function () {
  "use strict";

  const SITE = (window.__SENTINEL_SITES && window.__SENTINEL_SITES.currentSite()) || null;
  if (!SITE) return; // ไม่ใช่เว็บ AI ที่รองรับ
  const OV = window.__SENTINEL_OVERLAY;

  const cfg = {
    enabled: true,
    backendUrl: "http://127.0.0.1:8000",
    user: "unknown",
    department: "",
    device: "",
    failOpen: true, // เชื่อม backend ไม่ได้ = ปล่อยผ่าน (ไม่ขวางงาน) + เตือน
  };

  // โหลด/ติดตามการตั้งค่า
  try {
    chrome.storage.local.get(cfg, (v) => Object.assign(cfg, v || {}));
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      for (const k in changes) if (k in cfg) cfg[k] = changes[k].newValue;
    });
  } catch (e) { /* storage อาจไม่พร้อมในบางเฟรม */ }

  let bypassOnce = false;   // อนุญาตให้ส่งผ่าน 1 ครั้งหลังผู้ใช้ยืนยัน
  let inFlight = false;

  // ---------- utils ----------
  function findEditor() {
    const active = document.activeElement;
    for (const sel of SITE.input) {
      if (active && active.matches && active.matches(sel)) return active;
    }
    for (const sel of SITE.input) {
      const el = document.querySelector(sel);
      if (el && isVisible(el)) return el;
    }
    // fallback: ถ้า active element แก้ไขได้
    if (active && (active.isContentEditable || active.tagName === "TEXTAREA")) return active;
    return null;
  }

  function isVisible(el) {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function readText(el) {
    if (!el) return "";
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return el.value || "";
    return el.innerText || el.textContent || "";
  }

  function setText(el, text) {
    if (!el) return;
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      setter.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      el.focus();
      try {
        document.execCommand("selectAll", false, null);
        document.execCommand("insertText", false, text);
      } catch (e) {
        el.textContent = text;
        el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      }
    }
  }

  function insertAtCaret(el, text) {
    if (!el) return;
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      setter.call(el, el.value.slice(0, start) + text + el.value.slice(end));
      const pos = start + text.length;
      el.setSelectionRange(pos, pos);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      try { document.execCommand("insertText", false, text); }
      catch (e) { el.textContent += text; el.dispatchEvent(new InputEvent("input", { bubbles: true })); }
    }
  }

  function findSendButton() {
    for (const sel of SITE.send) {
      const btns = document.querySelectorAll(sel);
      for (const b of btns) {
        if (isVisible(b) && b.getAttribute("aria-disabled") !== "true" && !b.disabled) return b;
      }
    }
    return null;
  }

  function reallySend(editor) {
    bypassOnce = true;
    setTimeout(() => (bypassOnce = false), 1500); // กันค้าง
    const btn = findSendButton();
    if (btn) {
      btn.click();
    } else if (editor) {
      // fallback: ยิง Enter
      const ev = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true };
      editor.dispatchEvent(new KeyboardEvent("keydown", ev));
      editor.dispatchEvent(new KeyboardEvent("keyup", ev));
    }
  }

  // ---------- เรียก backend ผ่าน background (เลี่ยง mixed-content/CORS) ----------
  async function inspect(text, actionType, images) {
    const payload = {
      text: text || "",
      channel: SITE.channel,
      destination_url: location.href,
      action_type: actionType,
      user: cfg.user, department: cfg.department, device: cfg.device,
      images: images || [],
    };
    try {
      const res = await chrome.runtime.sendMessage({ type: "inspect", payload });
      if (res && res.ok) return res.data;
      throw new Error(res && res.error ? res.error : "no response");
    } catch (e) {
      if (OV) OV.toast("เชื่อมต่อเซิร์ฟเวอร์ SentinelAI ไม่ได้ — ปล่อยผ่านชั่วคราว", "err");
      return null; // fail-open
    }
  }

  function channelName() { return SITE.name || SITE.channel; }

  // ---------- ตัดสินและบังคับ ----------
  async function enforceSubmit(editor, text) {
    if (inFlight) return;
    inFlight = true;
    const result = await inspect(text, "submit");
    inFlight = false;
    if (!result) { reallySend(editor); return; } // fail-open

    const d = result.decision;
    const c = result.classification || {};
    if (d === "allow") { reallySend(editor); return; }
    if (d === "monitor") {
      if (OV) OV.toast(`บันทึกเหตุการณ์ (${c.label || "Internal"})`);
      reallySend(editor);
      return;
    }
    if (!OV) { if (d !== "block") reallySend(editor); return; }

    const opts = {
      decision: d, channelName: channelName(), label: c.label, risk: c.risk_score,
      reasons: c.reasons, coaching: result.coaching, requireApproval: false,
      redactedPreview: result.redacted_text,
    };
    const choice = await OV.showModal(opts);
    if (d === "redact") {
      if (choice === "confirm-redacted") { setText(editor, result.redacted_text || text); reallySend(editor); }
    } else if (d === "warn") {
      if (choice === "confirm") reallySend(editor);
      else if (choice === "request-approval") OV.toast("ส่งคำขออนุมัติถึงหัวหน้าแล้ว (เดโม)");
    } else if (d === "block") {
      if (choice === "request-approval") OV.toast("ส่งคำขออนุมัติถึงหัวหน้าแล้ว (เดโม)");
      // ไม่ส่ง
    }
  }

  async function enforcePaste(editor, pastedText, images) {
    const result = await inspect(pastedText, "paste", images);
    if (!result) { if (pastedText) insertAtCaret(editor, pastedText); return; }
    const d = result.decision;
    const c = result.classification || {};

    if (d === "allow") { if (pastedText) insertAtCaret(editor, pastedText); return; }
    if (d === "monitor") { if (pastedText) insertAtCaret(editor, pastedText); if (OV) OV.toast(`บันทึกการวาง (${c.label})`); return; }
    if (d === "redact") {
      insertAtCaret(editor, result.redacted_text || "");
      if (OV) OV.toast("ปิดบังข้อมูลลับในสิ่งที่วางให้แล้ว 🛡️");
      return;
    }
    if (!OV) { if (d !== "block" && pastedText) insertAtCaret(editor, pastedText); return; }

    const choice = await OV.showModal({
      decision: d, channelName: channelName(), label: c.label, risk: c.risk_score,
      reasons: c.reasons, coaching: result.coaching, redactedPreview: result.redacted_text,
    });
    if (d === "warn") {
      if (choice === "confirm") insertAtCaret(editor, pastedText);
      else if (choice === "request-approval") OV.toast("ส่งคำขออนุมัติถึงหัวหน้าแล้ว (เดโม)");
    } else if (d === "block") {
      if (choice === "request-approval") OV.toast("ส่งคำขออนุมัติถึงหัวหน้าแล้ว (เดโม)");
      // ไม่วางเนื้อหา
    }
  }

  // ---------- Event listeners (capture phase) ----------
  document.addEventListener("paste", (e) => {
    if (!cfg.enabled) return;
    const editor = e.target.closest && e.target.closest("[contenteditable],textarea,input")
      ? e.target : findEditor();
    if (!editor) return;
    const dt = e.clipboardData;
    if (!dt) return;

    // ภาพ (screenshot/สลิป/บัตร) — ตรวจด้วย Vision ถ้าเปิด AI
    const imgFiles = Array.from(dt.files || []).filter((f) => f.type.startsWith("image/"));
    const text = dt.getData("text/plain");

    if (imgFiles.length) {
      e.preventDefault();
      readImages(imgFiles).then((imgs) => enforcePaste(editor, text || "", imgs));
      return;
    }
    if (!text) return; // ไม่มีข้อความ = ปล่อย
    e.preventDefault();
    enforcePaste(editor, text, []);
  }, true);

  document.addEventListener("keydown", (e) => {
    if (!cfg.enabled) return;
    if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229 || e.ctrlKey || e.metaKey) return;
    if (bypassOnce) { bypassOnce = false; return; }
    const editor = findEditor();
    if (!editor) return;
    // ต้องกำลังโฟกัสในช่องพิมพ์
    if (document.activeElement !== editor && !(editor.contains && editor.contains(document.activeElement))) return;
    const text = readText(editor).trim();
    if (!text) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    enforceSubmit(editor, text);
  }, true);

  document.addEventListener("click", (e) => {
    if (!cfg.enabled) return;
    if (bypassOnce) { bypassOnce = false; return; }
    const btn = e.target.closest && e.target.closest(SITE.send.join(","));
    if (!btn) return;
    const editor = findEditor();
    const text = readText(editor).trim();
    if (!text) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    enforceSubmit(editor, text);
  }, true);

  function readImages(files) {
    return Promise.all(files.slice(0, 3).map((f) => new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => resolve(null);
      r.readAsDataURL(f);
    }))).then((arr) => arr.filter(Boolean));
  }

  if (OV) OV.toast(`SentinelAI พร้อมป้องกันบน ${channelName()}`);
  console.log("%c🛡️ SentinelAI", "color:#10b981;font-weight:bold", "active on", channelName());
})();
