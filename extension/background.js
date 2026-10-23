/**
 * HDM Browser Extension - Background Service Worker
 * Intercepts downloads and communicates with HDM desktop server at 127.0.0.1:9618
 */

const HDM_URL = "http://127.0.0.1:9618";

// Cache processed downloads to avoid re-interception loops
const processedDownloads = new Set();

/**
 * Check if HDM desktop app is currently running.
 */
async function pingHDM() {
  try {
    const res = await fetch(`${HDM_URL}/api/v1/status`, {
      method: "GET",
      headers: { "X-HDM-Client": "extension" },
      signal: AbortSignal.timeout(1500),
    });
    return res.ok ? await res.json() : null;
  } catch (e) {
    return null;
  }
}

/**
 * Send download request to HDM desktop application.
 */
async function sendToHDM(data) {
  try {
    const res = await fetch(`${HDM_URL}/api/v1/download`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-HDM-Client": "extension",
      },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(8000),
    });
    return res.ok ? await res.json() : null;
  } catch (e) {
    return null;
  }
}

/**
 * Request HDM to bring its window to the foreground.
 */
async function showHDMWindow() {
  try {
    await fetch(`${HDM_URL}/api/v1/show`, {
      method: "POST",
      headers: { "X-HDM-Client": "extension" },
    });
  } catch (e) {
    // Ignore error
  }
}

/**
 * Collect cookie string for the specific download URL.
 */
async function getCookiesForUrl(url) {
  try {
    const cookies = await chrome.cookies.getAll({ url });
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

/**
 * Core download interception listener.
 */
chrome.downloads.onCreated.addListener(async (item) => {
  if (processedDownloads.has(item.id)) return;

  const settings = await chrome.storage.local.get({ autoIntercept: true });
  if (!settings.autoIntercept) return;

  const url = item.finalUrl || item.url;
  if (!url || !url.startsWith("http")) return;

  // Mark processed to prevent duplicates
  processedDownloads.add(item.id);

  // 1. Pause download in browser first
  try {
    await chrome.downloads.pause(item.id);
  } catch (e) {
    // If cannot pause, proceed anyway
  }

  // 2. Prepare payload for HDM
  const cookies = await getCookiesForUrl(url);
  const payload = {
    url: url,
    filename: item.filename ? item.filename.split(/[\/\\]/).pop() : "",
    referer: item.referrer || "",
    cookies: cookies,
    user_agent: navigator.userAgent,
  };

  // 3. Send to HDM Desktop
  const response = await sendToHDM(payload);

  if (response && response.ok) {
    // HDM took over! Cancel and clean browser download entry
    try {
      await chrome.downloads.cancel(item.id);
      await chrome.downloads.erase({ id: item.id });
    } catch (e) {
      // Ignore
    }
  } else {
    // HDM is not running or rejected: Resume in browser smoothly
    try {
      await chrome.downloads.resume(item.id);
    } catch (e) {
      // Ignore
    }
  }
});

// Setup Context Menus
function setupMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "hdm-download-link",
      title: "Tải liên kết này với HDM",
      contexts: ["link"],
    });

    chrome.contextMenus.create({
      id: "hdm-download-media",
      title: "Tải đa phương tiện (Video/Audio) với HDM",
      contexts: ["video", "audio", "image"],
    });
  });
}

chrome.runtime.onInstalled.addListener(() => {
  setupMenus();
});

chrome.runtime.onStartup.addListener(() => {
  setupMenus();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const targetUrl = info.linkUrl || info.srcUrl || info.pageUrl;
  if (!targetUrl || !targetUrl.startsWith("http")) return;

  const cookies = await getCookiesForUrl(targetUrl);
  const payload = {
    url: targetUrl,
    referer: tab ? tab.url : "",
    cookies: cookies,
    user_agent: navigator.userAgent,
  };

  const res = await sendToHDM(payload);
  if (res && res.ok) {
    showHDMWindow();
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "HDM Download Manager",
      message: "Không thể kết nối với ứng dụng HDM. Vui lòng mở HDM trên máy tính của bạn.",
    });
  }
});

// Listen to popup messages
chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === "ping") {
    pingHDM().then(sendResponse);
    return true;
  } else if (req.action === "show_hdm") {
    showHDMWindow().then(() => sendResponse({ ok: true }));
    return true;
  }
});
