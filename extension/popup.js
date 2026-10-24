/**
 * HDM Browser Extension Popup Script
 */

const statusBadge = document.getElementById("status-badge");
const chkIntercept = document.getElementById("chk-intercept");
const chkVideoPanel = document.getElementById("chk-video-panel");
const activeTasksEl = document.getElementById("active-tasks");
const totalSpeedEl = document.getElementById("total-speed");
const btnOpenHdm = document.getElementById("btn-open-hdm");

function formatSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return "0 KB/s";
  if (bytesPerSec < 1024) return Math.round(bytesPerSec) + " B/s";
  if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + " KB/s";
  return (bytesPerSec / (1024 * 1024)).toFixed(2) + " MB/s";
}

async function init() {
  // Load settings
  const settings = await chrome.storage.local.get({
    autoIntercept: true,
    enableVideoPanel: true,
  });
  chkIntercept.checked = settings.autoIntercept;
  if (chkVideoPanel) {
    chkVideoPanel.checked = settings.enableVideoPanel;
    chkVideoPanel.addEventListener("change", async () => {
      await chrome.storage.local.set({ enableVideoPanel: chkVideoPanel.checked });
    });
  }

  chkIntercept.addEventListener("change", async () => {
    await chrome.storage.local.set({ autoIntercept: chkIntercept.checked });
  });

  btnOpenHdm.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "show_hdm" });
  });

  // Query HDM status
  checkStatus();
}

function checkStatus() {
  chrome.runtime.sendMessage({ action: "ping" }, (res) => {
    if (res && res.status === "ok") {
      statusBadge.textContent = "Đã kết nối";
      statusBadge.className = "badge connected";
      activeTasksEl.textContent = `${res.active_tasks} tác vụ`;
      totalSpeedEl.textContent = formatSpeed(res.total_speed);
    } else {
      statusBadge.textContent = "Mất kết nối";
      statusBadge.className = "badge disconnected";
      activeTasksEl.textContent = "--";
      totalSpeedEl.textContent = "--";
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
