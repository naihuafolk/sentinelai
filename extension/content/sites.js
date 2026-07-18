/*
 * sites.js — ตัวปรับต่อเว็บ AI แต่ละราย (Site Adapters)
 * ระบุ: channel, ตัวเลือก (selector) ของช่องพิมพ์ และปุ่มส่ง
 * ใช้ selector หลายตัวเผื่อ UI เปลี่ยน (fallback) — ระบบยังพยายามทำงานต่อ
 */
(function () {
  "use strict";

  const SITES = {
    "chatgpt.com": {
      channel: "chatgpt",
      name: "ChatGPT",
      input: ["#prompt-textarea", "div[contenteditable='true']", "textarea"],
      send: ["button[data-testid='send-button']", "button[aria-label*='Send']", "button[aria-label*='ส่ง']"],
    },
    "chat.openai.com": {
      channel: "chatgpt",
      name: "ChatGPT",
      input: ["#prompt-textarea", "div[contenteditable='true']", "textarea"],
      send: ["button[data-testid='send-button']", "button[aria-label*='Send']"],
    },
    "gemini.google.com": {
      channel: "gemini",
      name: "Gemini",
      input: ["div.ql-editor[contenteditable='true']", "rich-textarea div[contenteditable='true']", "div[contenteditable='true']", "textarea"],
      send: ["button.send-button", "button[aria-label*='Send']", "button[aria-label*='ส่ง']", "button[mattooltip*='Send']"],
    },
    "claude.ai": {
      channel: "claude",
      name: "Claude",
      input: ["div[contenteditable='true'].ProseMirror", "div[contenteditable='true']", "textarea"],
      send: ["button[aria-label*='Send']", "button[aria-label*='send']", "fieldset button[type='button']:last-of-type"],
    },
    "copilot.microsoft.com": {
      channel: "copilot",
      name: "Copilot",
      input: ["textarea#userInput", "textarea[aria-label]", "div[contenteditable='true']", "textarea"],
      send: ["button[data-testid='submit-button']", "button[aria-label*='Submit']", "button[aria-label*='Send']"],
    },
    "m365.cloud.microsoft": {
      channel: "copilot",
      name: "Microsoft 365 Copilot",
      input: ["div[contenteditable='true']", "textarea"],
      send: ["button[aria-label*='Send']", "button[aria-label*='Submit']"],
    },
    "chat.deepseek.com": {
      channel: "deepseek",
      name: "DeepSeek",
      input: ["textarea#chat-input", "textarea", "div[contenteditable='true']"],
      send: ["div[role='button'][aria-disabled]", "button[type='submit']", "button[aria-label*='Send']"],
    },
    "www.perplexity.ai": {
      channel: "perplexity",
      name: "Perplexity",
      input: ["textarea[placeholder]", "div[contenteditable='true']", "textarea"],
      send: ["button[aria-label*='Submit']", "button[aria-label*='Send']"],
    },
    "grok.com": {
      channel: "grok",
      name: "Grok",
      input: ["textarea", "div[contenteditable='true']"],
      send: ["button[type='submit']", "button[aria-label*='Send']"],
    },
  };

  function currentSite() {
    const host = location.hostname;
    if (SITES[host]) return SITES[host];
    // เผื่อ subdomain
    const key = Object.keys(SITES).find((h) => host === h || host.endsWith("." + h));
    return key ? SITES[key] : null;
  }

  window.__SENTINEL_SITES = { SITES, currentSite };
})();
