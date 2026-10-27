/**
 * HDM Browser Extension Popup Script
 * Real-time connection status & Network Media Sniffer list
 */

const statusBadge = document.getElementById("status-badge");
const chkIntercept = document.getElementById("chk-intercept");
const chkVideoPanel = document.getElementById("chk-video-panel");
const activeTasksEl = document.getElementById("active-tasks");
const totalSpeedEl = document.getElementById("total-speed");
const btnOpenHdm = document.getElementById("btn-open-hdm");
const inputPort = document.getElementById("input-port");
const btnSavePort = document.getElementById("btn-save-port");

const mediaCard = document.getElementById("media-card");
const mediaCountEl = document.getElementById("media-count");
const mediaListEl = document.getElementById("media-list");

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
    serverPort: 9618,
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

  if (inputPort) {
    inputPort.value = settings.serverPort || 9618;
  }

  async function savePort() {
    let port = parseInt(inputPort.value, 10);
    if (isNaN(port) || port < 1024 || port > 65535) {
      port = 9618;
      inputPort.value = port;
    }
    await chrome.storage.local.set({ serverPort: port });
    chrome.runtime.sendMessage({ action: "update_port", port: port }, () => {
      checkStatus();
    });
    if (btnSavePort) {
      btnSavePort.textContent = "✓";
      btnSavePort.classList.add("saved");
      setTimeout(() => {
        btnSavePort.textContent = "Lưu";
        btnSavePort.classList.remove("saved");
      }, 1200);
    }
  }

  if (btnSavePort) {
    btnSavePort.addEventListener("click", savePort);
  }
  if (inputPort) {
    inputPort.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        savePort();
      }
    });
  }

  btnOpenHdm.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "show_hdm" });
  });

  // Query HDM status
  checkStatus();

  // Query sniffed media for active tab
  loadCapturedMedia();
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

async function loadCapturedMedia() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tabs || !tabs.length || !tabs[0].id) return;
    const tab = tabs[0];

    chrome.runtime.sendMessage({ action: "get_captured_media", tabId: tab.id }, (res) => {
      if (chrome.runtime.lastError || !res || !res.ok) return;

      const mediaItems = res.media || [];
      if (mediaItems.length === 0) {
        mediaCard.style.display = "none";
        return;
      }

      mediaCard.style.display = "block";
      mediaCountEl.textContent = String(mediaItems.length);
      mediaListEl.innerHTML = "";

      mediaItems.forEach((item) => {
        const row = document.createElement("div");
        row.className = "media-item";

        const info = document.createElement("div");
        info.className = "media-item-info";

        const title = document.createElement("div");
        title.className = "media-item-title";
        title.textContent = item.title || "Video Stream";
        title.setAttribute("title", item.title || item.url);

        const meta = document.createElement("div");
        meta.className = "media-item-meta";

        const typeBadge = document.createElement("span");
        typeBadge.className = "badge-stream";
        typeBadge.textContent = item.type.toUpperCase();

        const urlText = document.createElement("span");
        urlText.className = "media-url";
        try {
          const parsed = new URL(item.url);
          urlText.textContent = parsed.hostname + parsed.pathname.slice(-25);
        } catch (e) {
          urlText.textContent = item.url.slice(0, 30);
        }
        urlText.setAttribute("title", item.url);

        meta.appendChild(typeBadge);
        meta.appendChild(urlText);
        info.appendChild(title);
        info.appendChild(meta);

        const dlBtn = document.createElement("button");
        dlBtn.className = "btn-dl-media";
        dlBtn.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3">
            <path d="M12 4v11m-5-5 5 5 5-5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
          </svg>
          Tải
        `;

        dlBtn.addEventListener("click", () => {
          dlBtn.disabled = true;
          dlBtn.textContent = "Đang gửi...";

          chrome.runtime.sendMessage(
            {
              action: "download_media",
              data: {
                url: item.url,
                pageUrl: tab.url,
                title: item.title,
                format: "mp4",
                ext: item.ext || "mp4",
                isStreaming: true,
              },
            },
            (dlRes) => {
              if (dlRes && dlRes.ok) {
                dlBtn.textContent = "✓ Đã gửi";
                dlBtn.style.backgroundColor = "#10b981";
                dlBtn.style.color = "#ffffff";
              } else {
                dlBtn.disabled = false;
                dlBtn.textContent = "Thử lại";
                dlBtn.style.backgroundColor = "#ef4444";
                dlBtn.style.color = "#ffffff";
              }
            }
          );
        });

        row.appendChild(info);
        row.appendChild(dlBtn);
        mediaListEl.appendChild(row);
      });
    });
  } catch (err) {
    // Ignore error
  }
}

document.addEventListener("DOMContentLoaded", init);
