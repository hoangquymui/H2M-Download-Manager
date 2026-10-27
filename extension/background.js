/**
 * HDM Browser Extension - Background Service Worker
 * Intercepts downloads, sniffs network media streams (HLS/m3u8, DASH/mpd, MP4),
 * and communicates with HDM desktop server at 127.0.0.1:9618
 */

let currentPort = 9618;

// Initialize configured port from storage
chrome.storage.local.get({ serverPort: 9618 }, (data) => {
  if (data && data.serverPort) {
    currentPort = parseInt(data.serverPort, 10) || 9618;
  }
});

// React immediately if port is changed in settings/popup
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.serverPort) {
    currentPort = parseInt(changes.serverPort.newValue, 10) || 9618;
  }
});

function getHdmUrls() {
  return [`http://127.0.0.1:${currentPort}`, `http://localhost:${currentPort}`];
}

// Cache processed downloads to avoid re-interception loops
const processedDownloads = new Set();

// In-memory media stream cache per tab: Map<tabId, Array<MediaItem>>
const capturedMediaByTab = new Map();

/**
 * Check if HDM desktop app is currently running.
 */
async function pingHDM() {
  for (const baseUrl of getHdmUrls()) {
    try {
      const res = await fetch(`${baseUrl}/api/v1/status`, {
        method: "GET",
        headers: { "X-HDM-Client": "extension" },
        signal: AbortSignal.timeout(1500),
      });
      if (res && res.ok) return await res.json();
    } catch (e) {
      // try next
    }
  }
  return null;
}

/**
 * Send download request to HDM desktop application.
 */
async function sendToHDM(data) {
  for (const baseUrl of getHdmUrls()) {
    try {
      const res = await fetch(`${baseUrl}/api/v1/download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-HDM-Client": "extension",
        },
        body: JSON.stringify(data),
        signal: AbortSignal.timeout(8000),
      });
      if (res && res.ok) return await res.json();
    } catch (e) {
      // try next
    }
  }
  return null;
}

/**
 * Request HDM to bring its window to the foreground.
 */
async function showHDMWindow() {
  for (const baseUrl of getHdmUrls()) {
    try {
      await fetch(`${baseUrl}/api/v1/show`, {
        method: "POST",
        headers: { "X-HDM-Client": "extension" },
        signal: AbortSignal.timeout(1500),
      });
      break;
    } catch (e) {
      // Ignore error
    }
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
 * Core download interception listener (for standard file downloads).
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

// =========================================================================
// Network Media Sniffer (HLS .m3u8, DASH .mpd, direct video/audio)
// =========================================================================

function detectMediaType(rawUrl, mimeType = "") {
  if (!rawUrl || !rawUrl.startsWith("http")) return null;
  const url = rawUrl.toLowerCase();
  const clean = url.split("?")[0];

  // Exclude non-media files & tiny segments
  if (
    clean.endsWith(".ts") ||
    clean.endsWith(".m4s") ||
    clean.endsWith(".vtt") ||
    clean.endsWith(".srt") ||
    clean.endsWith(".key") ||
    clean.endsWith(".js") ||
    clean.endsWith(".css") ||
    clean.endsWith(".json") ||
    clean.endsWith(".png") ||
    clean.endsWith(".jpg") ||
    clean.endsWith(".jpeg") ||
    clean.endsWith(".webp") ||
    clean.endsWith(".gif") ||
    clean.endsWith(".svg") ||
    clean.endsWith(".woff") ||
    clean.endsWith(".woff2")
  ) {
    return null;
  }

  // Exclude ad networks & analytics
  const adDomains = [
    "google-analytics.com",
    "doubleclick.net",
    "googlesyndication.com",
    "facebook.com/tr",
    "adservice.google.",
    "adnxs.com",
    "scorecardresearch.com",
    "clarity.ms",
    "hotjar.com",
    "criteo.com",
  ];
  if (adDomains.some((d) => url.includes(d))) return null;

  // 1. HLS m3u8 playlist
  if (
    clean.endsWith(".m3u8") ||
    url.includes(".m3u8?") ||
    (url.includes("/hls/") && url.includes(".m3u8")) ||
    mimeType.includes("application/vnd.apple.mpegurl") ||
    mimeType.includes("application/x-mpegurl")
  ) {
    return { type: "m3u8", label: "HLS Stream (m3u8)", ext: "mp4", format: "mp4" };
  }

  // 2. DASH mpd manifest
  if (
    clean.endsWith(".mpd") ||
    url.includes(".mpd?") ||
    mimeType.includes("application/dash+xml")
  ) {
    return { type: "mpd", label: "DASH Stream (mpd)", ext: "mp4", format: "mp4" };
  }

  // 3. Direct video files
  if (clean.endsWith(".mp4") || url.includes(".mp4?") || mimeType.includes("video/mp4")) {
    return { type: "mp4", label: "Video MP4", ext: "mp4", format: "mp4" };
  }
  if (clean.endsWith(".webm") || url.includes(".webm?") || mimeType.includes("video/webm")) {
    return { type: "webm", label: "Video WebM", ext: "mp4", format: "mp4" };
  }
  if (
    clean.endsWith(".mkv") ||
    clean.endsWith(".flv") ||
    clean.endsWith(".m4v") ||
    clean.endsWith(".mov") ||
    mimeType.startsWith("video/")
  ) {
    return { type: "video", label: "Video", ext: "mp4", format: "mp4" };
  }

  // 4. Standalone audio files
  if (
    clean.endsWith(".mp3") ||
    clean.endsWith(".m4a") ||
    clean.endsWith(".aac") ||
    clean.endsWith(".wav") ||
    clean.endsWith(".flac") ||
    clean.endsWith(".ogg") ||
    mimeType.startsWith("audio/")
  ) {
    return { type: "audio", label: "Audio", ext: "mp3", format: "mp3" };
  }

  return null;
}

// Sniff headers of completed network requests
chrome.webRequest.onHeadersReceived.addListener(
  async (details) => {
    const tabId = details.tabId;
    if (tabId < 0) return;

    let mimeType = "";
    if (details.responseHeaders) {
      const ct = details.responseHeaders.find(
        (h) => h.name.toLowerCase() === "content-type"
      );
      if (ct && ct.value) {
        mimeType = ct.value.toLowerCase();
      }
    }

    const mediaInfo = detectMediaType(details.url, mimeType);
    if (!mediaInfo) return;

    try {
      const tab = await chrome.tabs.get(tabId);
      if (!tab) return;

      // Skip internal YouTube chunks since HDM handles full YouTube pages natively
      if (tab.url && (tab.url.includes("youtube.com") || tab.url.includes("youtu.be"))) {
        return;
      }

      let list = capturedMediaByTab.get(tabId);
      if (!list) {
        list = [];
        capturedMediaByTab.set(tabId, list);
      }

      // Deduplicate: avoid duplicate streams
      const isDup = list.some((item) => item.url === details.url);
      if (isDup) return;

      // Clean title from tab or URL
      let rawTitle = tab.title || "";
      rawTitle = rawTitle
        .replace(/\s*[-–|]\s*(Xem phim|Phim HD|Trang chủ|Official Website|Thuyết minh|Vietsub).*$/i, "")
        .replace(/\s*[-–|]\s*YouTube$/i, "")
        .trim();

      if (!rawTitle) {
        const uParts = details.url.split("/").pop().split("?")[0];
        rawTitle = uParts.replace(/\.[a-zA-Z0-9]+$/, "") || "video";
      }

      const mediaItem = {
        id: `${tabId}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        url: details.url,
        pageUrl: tab.url || "",
        title: rawTitle,
        type: mediaInfo.type,
        label: mediaInfo.label,
        ext: mediaInfo.ext,
        format: mediaInfo.format,
        timestamp: Date.now(),
      };

      list.unshift(mediaItem);
      if (list.length > 25) list.pop();

      // Update extension toolbar badge
      chrome.action.setBadgeText({ tabId, text: String(list.length) });
      chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" });

      // Notify content script in the tab
      chrome.tabs.sendMessage(tabId, {
        action: "hdm_media_detected",
        media: mediaItem,
        totalCount: list.length,
      }).catch(() => {});
    } catch (err) {
      // Tab may have closed or navigated
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Clean up captured media when a tab navigates or closes
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    capturedMediaByTab.delete(tabId);
    chrome.action.setBadgeText({ tabId, text: "" }).catch(() => {});
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  capturedMediaByTab.delete(tabId);
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

function sanitizeFilename(name) {
  return (name || "video")
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/\s+/g, " ")
    .trim();
}

async function handleMediaDownload(data) {
  const targetUrl = data.url || data.pageUrl;
  const cookies = await getCookiesForUrl(targetUrl);
  const ext = data.format === "mp3" ? "mp3" : (data.ext || "mp4");
  const filename = data.title ? `${sanitizeFilename(data.title)}.${ext}` : "";

  const payload = {
    url: targetUrl,
    filename: filename,
    referer: data.pageUrl || "",
    cookies: cookies,
    user_agent: navigator.userAgent,
    format: data.format || "mp4",
    quality: data.quality || "",
    is_video: true,
  };

  const res = await sendToHDM(payload);
  if (res && res.ok) {
    showHDMWindow();
    return { ok: true };
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "HDM Download Manager",
      message: "Không thể kết nối với ứng dụng HDM. Vui lòng mở HDM trên máy tính của bạn.",
    });
    return { ok: false, error: "Cannot connect to HDM" };
  }
}

// Listen to popup and content script messages
chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === "ping") {
    pingHDM().then(sendResponse);
    return true;
  } else if (req.action === "update_port") {
    currentPort = parseInt(req.port, 10) || 9618;
    pingHDM().then(sendResponse);
    return true;
  } else if (req.action === "show_hdm") {
    showHDMWindow().then(() => sendResponse({ ok: true }));
    return true;
  } else if (req.action === "download_media") {
    handleMediaDownload(req.data).then(sendResponse);
    return true;
  } else if (req.action === "get_captured_media") {
    const tabId = req.tabId || (sender && sender.tab && sender.tab.id);
    const list = tabId ? (capturedMediaByTab.get(tabId) || []) : [];
    sendResponse({ ok: true, media: list });
    return true;
  } else if (req.action === "clear_captured_media") {
    const tabId = req.tabId || (sender && sender.tab && sender.tab.id);
    if (tabId) {
      capturedMediaByTab.delete(tabId);
      chrome.action.setBadgeText({ tabId, text: "" }).catch(() => {});
    }
    sendResponse({ ok: true });
    return true;
  }
});
