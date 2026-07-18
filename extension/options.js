/* options.js — บันทึกการตั้งค่าลง chrome.storage.local */
const DEFAULTS = {
  enabled: true,
  backendUrl: "http://127.0.0.1:8000",
  orgKey: "",
  user: "unknown",
  department: "",
  device: "",
  failOpen: true,
};
const $ = (id) => document.getElementById(id);

function load() {
  chrome.storage.local.get(DEFAULTS, (v) => {
    $("backendUrl").value = v.backendUrl || DEFAULTS.backendUrl;
    $("orgKey").value = v.orgKey || "";
    $("user").value = v.user && v.user !== "unknown" ? v.user : "";
    $("department").value = v.department || "";
    $("device").value = v.device || "";
    $("enabled").checked = v.enabled !== false;
    $("failOpen").checked = v.failOpen !== false;
  });
}

function save() {
  const data = {
    backendUrl: ($("backendUrl").value || DEFAULTS.backendUrl).trim().replace(/\/+$/, ""),
    orgKey: $("orgKey").value.trim(),
    user: ($("user").value || "unknown").trim() || "unknown",
    department: $("department").value.trim(),
    device: $("device").value.trim(),
    enabled: $("enabled").checked,
    failOpen: $("failOpen").checked,
  };
  chrome.storage.local.set(data, () => {
    const ok = $("ok");
    ok.classList.add("show");
    setTimeout(() => ok.classList.remove("show"), 1600);
  });
}

$("save").addEventListener("click", save);
load();
