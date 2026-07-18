/*
 * overlay.js — กล่องแจ้งเตือนในหน้าเว็บ (Shadow DOM กัน CSS ชนกับเว็บ AI)
 * ให้ window.__SENTINEL_OVERLAY = { showModal, toast }
 * showModal(opts) -> Promise<'confirm'|'confirm-redacted'|'request-approval'|'cancel'>
 */
(function () {
  "use strict";

  const LABEL_TH = {
    Public: "ทั่วไป (Public)",
    Internal: "ภายในองค์กร (Internal)",
    Confidential: "ลับ (Confidential)",
    Restricted: "ลับที่สุด (Restricted)",
  };
  const LABEL_COLOR = {
    Public: "#64748b", Internal: "#3b82f6", Confidential: "#f59e0b", Restricted: "#ef4444",
  };
  const DECISION_THEME = {
    block: { icon: "⛔", color: "#ef4444", title: "ตรวจพบข้อมูลลับ — ถูกบล็อก" },
    warn: { icon: "⚠️", color: "#f59e0b", title: "ตรวจพบข้อมูลที่อาจเป็นความลับ" },
    redact: { icon: "🛡️", color: "#8b5cf6", title: "ปิดบังข้อมูลลับก่อนส่ง" },
  };

  const STYLE = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", "Sarabun", Tahoma, sans-serif; }
  .sa-backdrop {
    position: fixed; inset: 0; z-index: 2147483647;
    background: rgba(2,6,23,.55); backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center; padding: 20px;
    animation: sa-fade .15s ease;
  }
  @keyframes sa-fade { from { opacity: 0 } to { opacity: 1 } }
  @keyframes sa-pop { from { transform: translateY(8px) scale(.98); opacity: 0 } to { transform: none; opacity: 1 } }
  .sa-card {
    width: 460px; max-width: 100%; background: #0f172a; color: #e2e8f0;
    border: 1px solid #1e293b; border-radius: 16px; overflow: hidden;
    box-shadow: 0 24px 60px rgba(0,0,0,.5); animation: sa-pop .18s ease;
  }
  .sa-top { height: 5px; }
  .sa-body { padding: 20px 22px 8px; }
  .sa-head { display: flex; gap: 12px; align-items: flex-start; }
  .sa-icon { font-size: 26px; line-height: 1; }
  .sa-brand { font-size: 12px; letter-spacing: .5px; color: #10b981; font-weight: 700; }
  .sa-title { font-size: 17px; font-weight: 700; margin: 2px 0 0; color: #f8fafc; }
  .sa-msg { font-size: 14px; line-height: 1.55; margin: 14px 0 0; color: #cbd5e1; }
  .sa-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .sa-badge { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; }
  .sa-chan { background: #1e293b; color: #94a3b8; }
  .sa-reasons { margin: 14px 0 0; padding: 12px 14px; background: #0b1220;
    border: 1px solid #1e293b; border-radius: 10px; font-size: 13px; color: #cbd5e1; }
  .sa-reasons b { color: #f1f5f9; font-weight: 600; }
  .sa-reasons ul { margin: 6px 0 0; padding-left: 18px; }
  .sa-reasons li { margin: 3px 0; }
  .sa-coach { margin-top: 12px; font-size: 13px; line-height: 1.5; color: #a7f3d0;
    background: rgba(16,185,129,.08); border-left: 3px solid #10b981;
    padding: 10px 12px; border-radius: 8px; }
  .sa-redact { margin-top: 12px; font-size: 13px; color: #ddd6fe; background: rgba(139,92,246,.08);
    border: 1px dashed #7c3aed; border-radius: 8px; padding: 10px 12px; max-height: 120px; overflow: auto;
    white-space: pre-wrap; word-break: break-word; }
  .sa-actions { display: flex; gap: 10px; padding: 16px 22px 20px; flex-wrap: wrap; }
  .sa-btn { flex: 1; min-width: 120px; padding: 10px 14px; border-radius: 10px; border: 1px solid transparent;
    font-size: 14px; font-weight: 600; cursor: pointer; transition: filter .12s; }
  .sa-btn:hover { filter: brightness(1.1); }
  .sa-btn-danger { background: #ef4444; color: #fff; }
  .sa-btn-primary { background: #10b981; color: #052e1a; }
  .sa-btn-warn { background: #f59e0b; color: #3a2606; }
  .sa-btn-ghost { background: transparent; color: #94a3b8; border-color: #334155; }
  .sa-foot { font-size: 11px; color: #64748b; padding: 0 22px 16px; text-align: center; }
  .sa-toast-wrap { position: fixed; z-index: 2147483647; right: 18px; bottom: 18px; display: flex;
    flex-direction: column; gap: 8px; }
  .sa-toast { background: #0f172a; color: #e2e8f0; border: 1px solid #1e293b; border-left: 3px solid #10b981;
    border-radius: 10px; padding: 10px 14px; font-size: 13px; box-shadow: 0 10px 30px rgba(0,0,0,.4);
    animation: sa-pop .18s ease; max-width: 320px; }
  .sa-toast.err { border-left-color: #ef4444; }
  .sa-toast .t { font-weight: 700; color: #10b981; font-size: 11px; letter-spacing: .4px; }
  .sa-toast.err .t { color: #ef4444; }
  `;

  let host = null;
  function ensureHost() {
    if (host && document.documentElement.contains(host)) return host.shadowRoot;
    host = document.createElement("div");
    host.id = "sentinelai-overlay-host";
    (document.documentElement || document.body).appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    root.appendChild(style);
    const toastWrap = document.createElement("div");
    toastWrap.className = "sa-toast-wrap";
    root.appendChild(toastWrap);
    return root;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function showModal(opts) {
    const root = ensureHost();
    const theme = DECISION_THEME[opts.decision] || DECISION_THEME.warn;
    const labelColor = LABEL_COLOR[opts.label] || "#64748b";

    return new Promise((resolve) => {
      const backdrop = document.createElement("div");
      backdrop.className = "sa-backdrop";

      const reasons = (opts.reasons || []).slice(0, 5);
      const reasonsHtml = reasons.length
        ? `<div class="sa-reasons"><b>เหตุผล:</b><ul>${reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`
        : "";
      const coachHtml = opts.coaching ? `<div class="sa-coach">💡 ${esc(opts.coaching)}</div>` : "";
      const redactHtml =
        opts.decision === "redact" && opts.redactedPreview
          ? `<div class="sa-redact">${esc(opts.redactedPreview)}</div>`
          : "";

      // ปุ่มตามชนิดการตัดสิน
      let buttons = "";
      if (opts.decision === "block") {
        if (opts.requireApproval)
          buttons += `<button class="sa-btn sa-btn-warn" data-act="request-approval">ขออนุมัติจากหัวหน้า</button>`;
        buttons += `<button class="sa-btn sa-btn-danger" data-act="cancel">รับทราบ / ยกเลิกการส่ง</button>`;
      } else if (opts.decision === "redact") {
        buttons += `<button class="sa-btn sa-btn-primary" data-act="confirm-redacted">ส่งฉบับที่ปิดบังแล้ว</button>`;
        buttons += `<button class="sa-btn sa-btn-ghost" data-act="cancel">ยกเลิก</button>`;
      } else {
        // warn
        buttons += `<button class="sa-btn sa-btn-warn" data-act="confirm">ยืนยัน ส่งต่อ</button>`;
        if (opts.requireApproval)
          buttons += `<button class="sa-btn sa-btn-ghost" data-act="request-approval">ขออนุมัติหัวหน้า</button>`;
        buttons += `<button class="sa-btn sa-btn-ghost" data-act="cancel">ยกเลิก</button>`;
      }

      backdrop.innerHTML = `
        <div class="sa-card" role="dialog" aria-modal="true">
          <div class="sa-top" style="background:${theme.color}"></div>
          <div class="sa-body">
            <div class="sa-head">
              <div class="sa-icon">${theme.icon}</div>
              <div>
                <div class="sa-brand">🛡️ SENTINELAI</div>
                <div class="sa-title">${esc(theme.title)}</div>
              </div>
            </div>
            <div class="sa-msg">เนื้อหาที่คุณกำลังจะส่งไปยัง <b>${esc(opts.channelName || "AI")}</b>
              ถูกจัดเป็น <b style="color:${labelColor}">${esc(LABEL_TH[opts.label] || opts.label)}</b></div>
            <div class="sa-badges">
              <span class="sa-badge" style="background:${labelColor}22;color:${labelColor}">ความเสี่ยง ${opts.risk ?? "-"}/100</span>
              <span class="sa-badge sa-chan">ปลายทาง: ${esc(opts.channelName || "-")}</span>
            </div>
            ${reasonsHtml}
            ${coachHtml}
            ${redactHtml}
          </div>
          <div class="sa-actions">${buttons}</div>
          <div class="sa-foot">🔒 เหตุการณ์นี้ถูกบันทึกเพื่อการตรวจสอบตามนโยบายองค์กร (PDPA-compliant)</div>
        </div>`;

      function close(result) {
        backdrop.remove();
        document.removeEventListener("keydown", onKey, true);
        resolve(result);
      }
      function onKey(e) {
        if (e.key === "Escape") { e.stopPropagation(); close("cancel"); }
      }
      backdrop.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-act]");
        if (btn) { e.preventDefault(); close(btn.getAttribute("data-act")); return; }
        if (e.target === backdrop) close("cancel");
      });
      document.addEventListener("keydown", onKey, true);
      root.appendChild(backdrop);
    });
  }

  function toast(msg, kind) {
    const root = ensureHost();
    const wrap = root.querySelector(".sa-toast-wrap");
    const el = document.createElement("div");
    el.className = "sa-toast" + (kind === "err" ? " err" : "");
    el.innerHTML = `<div class="t">🛡️ SENTINELAI</div><div>${esc(msg)}</div>`;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3200);
    setTimeout(() => el.remove(), 3600);
  }

  window.__SENTINEL_OVERLAY = { showModal, toast };
})();
