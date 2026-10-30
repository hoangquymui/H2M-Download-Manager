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

// React immediately if port or panel settings change in settings/popup
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.serverPort) {
    currentPort = parseInt(changes.serverPort.newValue, 10) || 9618;
  }
  if (changes.enableVideoPanel) {
    videoPanelEnabled = !!changes.enableVideoPanel.newValue;
    if (!videoPanelEnabled) {
      capturedMediaByTab.forEach((_list, tabId) => {
        chrome.action.setBadgeText({ tabId, text: "" })?.catch?.(() => {});
      });
      capturedMediaByTab.clear();
    }
  }
});

function getHdmUrls() {
  return [`http://127.0.0.1:${currentPort}`, `http://localhost:${currentPort}`];
}

// Cache processed downloads to avoid re-interception loops
const processedDownloads = new Set();

// In-memory media stream cache per tab: Map<tabId, Array<MediaItem>>
const capturedMediaByTab = new Map();

// Media handed to HDM before, so a page that replays the same stream (CDN URLs
// are re-signed on every visit) is not captured and listed all over again.
const downloadedUrlKeys = new Set();
const MAX_DOWNLOADED_KEYS = 500;
let videoPanelEnabled = true;

function mediaUrlKey(rawUrl) {
  try {
    const u = new URL(rawUrl);
    // Query strings carry per-session tokens, so compare origin + path.
    if (u.pathname && u.pathname !== "/") return `${u.origin}${u.pathname}`;
    return u.href;
  } catch (e) {
    return rawUrl || "";
  }
}

async function loadRememberedState() {
  try {
    const data = await chrome.storage.local.get({
      downloadedUrls: {},
      enableVideoPanel: true,
    });
    videoPanelEnabled = !!data.enableVideoPanel;
    Object.keys(data.downloadedUrls || {}).forEach((key) => downloadedUrlKeys.add(key));
  } catch (e) {}
}

loadRememberedState();

async function rememberDownloaded(rawUrl) {
  const key = mediaUrlKey(rawUrl);
  if (!key) return;
  downloadedUrlKeys.add(key);
  try {
    const data = await chrome.storage.local.get({ downloadedUrls: {} });
    const map = data.downloadedUrls || {};
    map[key] = Date.now();
    const entries = Object.entries(map);
    if (entries.length > MAX_DOWNLOADED_KEYS) {
      entries.sort((a, b) => a[1] - b[1]);
      entries.slice(0, entries.length - MAX_DOWNLOADED_KEYS).forEach(([old]) => delete map[old]);
    }
    await chrome.storage.local.set({ downloadedUrls: map });
    if (downloadedUrlKeys.size > MAX_DOWNLOADED_KEYS) {
      downloadedUrlKeys.clear();
      Object.keys(map).forEach((k) => downloadedUrlKeys.add(k));
    }
  } catch (e) {}
}

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
async function sendToHDM(data, timeoutMs = 15000) {
  for (const baseUrl of getHdmUrls()) {
    try {
      const options = {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-HDM-Client": "extension",
        },
        body: JSON.stringify(data),
      };
      // timeoutMs = 0 waits until HDM answers, however long its dialog stays open.
      if (timeoutMs > 0) options.signal = AbortSignal.timeout(timeoutMs);
      const res = await fetch(`${baseUrl}/api/v1/download`, options);
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
 * True when a name ends with a plausible file extension ("7z", "mp4", "tar.gz").
 * Version tails such as ".2407" are rejected because they contain no letter.
 */
function hasFileExtension(name) {
  if (!name || !name.includes(".")) return false;
  const ext = name.split(".").pop();
  return ext.length > 1 && ext.length <= 12 && /^[a-z0-9]+$/i.test(ext) && /[a-z]/i.test(ext);
}

/**
 * Recover the real filename from a download URL. Signed CDN links often carry
 * an opaque UUID as the suggested name while the real name sits in the path or
 * in the response-content-disposition query parameter.
 */
function guessFilenameFromUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    const decode = (value) => {
      try {
        return decodeURIComponent(value);
      } catch (e) {
        return value;
      }
    };

    const segments = parsed.pathname.split("/").filter(Boolean);
    const base = decode(segments[segments.length - 1] || "");
    if (hasFileExtension(base)) return base;

    for (const key of ["response-content-disposition", "content-disposition"]) {
      const value = parsed.searchParams.get(key);
      if (!value) continue;
      const match = value.match(/filename\*?\s*=\s*(?:UTF-8'')?["']?([^"';]+)/i);
      if (match) {
        const candidate = decode(match[1].trim().replace(/^"|"$/g, ""));
        if (hasFileExtension(candidate)) return candidate;
      }
    }

    for (const key of ["filename", "file", "name"]) {
      const value = parsed.searchParams.get(key);
      if (!value) continue;
      const candidate = decode(value.trim());
      if (hasFileExtension(candidate)) return candidate;
    }
  } catch (e) {
    // Not a parseable URL
  }
  return "";
}

/**
 * Keep only well-formed captured quality entries, mirroring the server limits.
 */
function sanitizeQualities(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  let total = 0;
  for (const item of list.slice(0, 8)) {
    if (!item || typeof item !== "object") continue;
    const manifest =
      typeof item.manifest === "string" && item.manifest.indexOf("#EXTM3U") !== -1
        ? item.manifest
        : "";
    if (!manifest) continue;
    if (total + manifest.length > 5 * 1024 * 1024) break;
    total += manifest.length;
    out.push({
      label: String(item.label || "").slice(0, 24),
      height: String(item.height || "").slice(0, 8),
      manifest: manifest,
    });
  }
  return out;
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
 * Pause an in-progress download, retrying because Chrome often rejects
 * pause() while the download is still starting right after onCreated.
 * Returns the latest DownloadItem, or null when it is gone.
 */
async function ensurePaused(id, attempts = 12) {
  let last = null;
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const [current] = await chrome.downloads.search({ id });
      last = current || null;
      if (!current || current.state !== "in_progress") return last;
      if (!current.paused) {
        await chrome.downloads.pause(id);
      }
      const [after] = await chrome.downloads.search({ id });
      last = after || null;
      if (!after || after.state !== "in_progress" || after.paused) return last;
    } catch (e) {
      // Retry: pause() throws while the download is still initializing.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return last;
}

/**
 * Cancel a browser download and remove its entry from the downloads list.
 */
async function cancelAndEraseDownload(id) {
  try {
    await chrome.downloads.cancel(id);
  } catch (e) {
    // Already finished or interrupted
  }
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      const [current] = await chrome.downloads.search({ id });
      if (!current) return;
      if (current.state !== "in_progress") {
        await chrome.downloads.erase({ id });
        return;
      }
      await chrome.downloads.cancel(id);
    } catch (e) {
      // Retry until the download actually stops
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  try {
    await chrome.downloads.erase({ id });
  } catch (e) {}
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

  // 1. Pause the browser copy before anything is transferred.
  await ensurePaused(item.id);

  const [latest] = (await chrome.downloads.search({ id: item.id }).catch(() => [])) || [];
  if (latest && latest.state === "complete") {
    // A tiny/fast download already finished: keep the browser copy instead
    // of asking HDM to download a duplicate.
    return;
  }

  // Chrome may auto-resume a paused download, so hold it paused for as long
  // as the desktop confirmation dialog stays open. The interval also keeps the
  // MV3 service worker alive during that wait.
  const keepPaused = setInterval(() => {
    ensurePaused(item.id, 1);
  }, 800);

  let response = null;
  try {
    // 2. Prepare payload for HDM
    const cookies = await getCookiesForUrl(url);
    let suggestedName = item.filename ? item.filename.split(/[\/\\]/).pop() : "";
    if (!hasFileExtension(suggestedName)) {
      suggestedName = guessFilenameFromUrl(url) || suggestedName;
    }
    const payload = {
      url: url,
      filename: suggestedName,
      referer: item.referrer || "",
      cookies: cookies,
      user_agent: navigator.userAgent,
    };

    // 3. Send to HDM Desktop. The desktop answers only when the user resolves
    //    its confirmation dialog, so wait without a timeout.
    response = await sendToHDM(payload, 0);
  } finally {
    clearInterval(keepPaused);
  }

  const mode = response && response.mode;

  if (response && response.ok && mode !== "cancelled") {
    // HDM accepted the job and now owns the download.
    await rememberDownloaded(url);
    await cancelAndEraseDownload(item.id);
  } else if (response && mode === "cancelled") {
    // The user said no in the HDM dialog: drop the browser copy as well
    // instead of resuming a download they explicitly declined.
    await cancelAndEraseDownload(item.id);
  } else {
    // HDM is unreachable or the dialog timed out without a decision, so keep
    // the browser download: an offline/disabled HDM must not block browsing.
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
  const clean = url.split("?")[0].split("#")[0];

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

  // 1. HLS m3u8 playlist (PRIORITY: Catch all HLS manifests)
  if (
    clean.endsWith(".m3u8") ||
    url.includes(".m3u8") ||
    url.includes("/hls/") ||
    url.includes("m3u8") ||
    mimeType.includes("mpegurl") ||
    mimeType.includes("application/x-mpegurl") ||
    mimeType.includes("application/vnd.apple.mpegurl") ||
    mimeType.includes("audio/x-mpegurl")
  ) {
    // Avoid false positive on .ts / .key with m3u8 query
    if (!clean.endsWith(".ts") && !clean.endsWith(".key") && !clean.endsWith(".js")) {
      return { type: "m3u8", label: "HLS Stream (m3u8)", ext: "mp4", format: "mp4" };
    }
  }

  // 2. DASH mpd manifest
  if (
    clean.endsWith(".mpd") ||
    url.includes(".mpd") ||
    mimeType.includes("application/dash+xml")
  ) {
    if (!clean.endsWith(".m4s")) {
      return { type: "mpd", label: "DASH Stream (mpd)", ext: "mp4", format: "mp4" };
    }
  }

  // Exclude non-media static files & tiny segments
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

// Record captured media item into tab cache
async function recordCapturedMedia(tabId, url, mimeType = "") {
  if (tabId < 0) return;
  if (!videoPanelEnabled) return;
  if (downloadedUrlKeys.has(mediaUrlKey(url))) return;
  const mediaInfo = detectMediaType(url, mimeType);
  if (!mediaInfo) return;

  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab) return;

    if (tab.url && (tab.url.includes("youtube.com") || tab.url.includes("youtu.be"))) {
      return;
    }

    let list = capturedMediaByTab.get(tabId);
    if (!list) {
      list = [];
      capturedMediaByTab.set(tabId, list);
    }

    const isDup = list.some((item) => item.url === url);
    if (isDup) return;

    let rawTitle = tab.title || "";
    rawTitle = rawTitle
      .replace(/\s*[-–|]\s*(Xem phim|Phim HD|Trang chủ|Official Website|Thuyết minh|Vietsub).*$/i, "")
      .replace(/\s*[-–|]\s*YouTube$/i, "")
      .trim();

    if (!rawTitle) {
      const uParts = url.split("/").pop().split("?")[0];
      rawTitle = uParts.replace(/\.[a-zA-Z0-9]+$/, "") || "video";
    }

    const mediaItem = {
      id: `${tabId}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      url: url,
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

    chrome.action.setBadgeText({ tabId, text: String(list.length) })?.catch?.(() => {});
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" })?.catch?.(() => {});

    chrome.tabs.sendMessage(tabId, {
      action: "hdm_media_detected",
      media: mediaItem,
      totalCount: list.length,
    }).catch(() => {});
  } catch (err) {}
}

// 1. Sniff URL as soon as network request begins (instant m3u8 detection)
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    recordCapturedMedia(details.tabId, details.url);
  },
  { urls: ["<all_urls>"] }
);

// 2. Sniff response headers to detect MIME types for extensionless URLs
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    let mimeType = "";
    if (details.responseHeaders) {
      const ct = details.responseHeaders.find(
        (h) => h.name.toLowerCase() === "content-type"
      );
      if (ct && ct.value) {
        mimeType = ct.value.toLowerCase();
      }
    }
    recordCapturedMedia(details.tabId, details.url, mimeType);
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Clean up captured media when a tab navigates or closes
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    capturedMediaByTab.delete(tabId);
    chrome.action.setBadgeText({ tabId, text: "" })?.catch?.(() => {});
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

  // Wait out the desktop confirmation dialog instead of failing early.
  const res = await sendToHDM(payload, 0);
  if (res && res.ok) {
    await rememberDownloaded(targetUrl);
    // Download request sent to HDM; modal will display on desktop without forcing main window
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "HDM Download Manager",
      message: "Không thể kết nối với ứng dụng HDM. Vui lòng kiểm tra cổng kết nối hoặc mở HDM.",
    });
  }
});

/**
 * True when the URL belongs to a site yt-dlp handles as a streaming platform.
 * Matched by hostname so "notyoutube.com" is not treated as YouTube.
 */
function isStreamingHost(rawUrl) {
  try {
    const host = new URL(rawUrl).hostname.toLowerCase();
    return ["youtube.com", "youtube-nocookie.com", "youtu.be"].some(
      (domain) => host === domain || host.endsWith("." + domain)
    );
  } catch (e) {
    return false;
  }
}

function sanitizeFilename(name) {
  return (name || "video")
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/\s+/g, " ")
    .trim();
}

async function handleMediaDownload(data, sender) {
  // Captured in-page HLS manifest (blob-based players like jwplayer/ibytedance).
  // When present it is the source of truth and no URL substitution may happen.
  const manifest =
    typeof data.manifest === "string" && data.manifest.indexOf("#EXTM3U") !== -1
      ? data.manifest
      : "";
  const hasManifest = manifest.length > 0;

  let targetUrl = data.url || data.pageUrl;
  const tabId = (sender && sender.tab && sender.tab.id) || null;

  if (hasManifest && !/^https?:/i.test(targetUrl || "")) {
    targetUrl = data.pageUrl || targetUrl;
  }

  // CRITICAL FIX: If targetUrl is an HTML web page (ends in .html, .htm or matches pageUrl)
  // or does not look like a media stream (no m3u8/mpd/mp4), substitute with the real
  // video/stream URL sniffed for this tab!
  const isHtmlOrPageUrl =
    !targetUrl ||
    targetUrl.endsWith(".html") ||
    targetUrl.endsWith(".htm") ||
    targetUrl === data.pageUrl ||
    (!targetUrl.includes(".m3u8") &&
      !targetUrl.includes("m3u8") &&
      !targetUrl.includes(".mpd") &&
      !targetUrl.match(/\.(mp4|webm|mkv|m4v|mov|flv)($|\?)/i));

  const isYouTube = isStreamingHost(targetUrl) || isStreamingHost(data.pageUrl || "");

  if (!hasManifest && !isYouTube && isHtmlOrPageUrl && tabId) {
    const list = capturedMediaByTab.get(tabId) || [];
    if (list.length > 0) {
      // Pick the most recent media stream captured for this tab
      const best = list[0];
      targetUrl = best.url;
      if (!data.title && best.title) {
        data.title = best.title;
      }
      if (best.ext) {
        data.ext = best.ext;
      }
    }
  }

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

  if (hasManifest) {
    payload.manifest = manifest;
  }

  const qualities = sanitizeQualities(data.qualities);
  if (qualities.length) {
    payload.qualities = qualities;
  }

  // Wait out the desktop confirmation dialog instead of failing early.
  const res = await sendToHDM(payload, 0);
  if (res && res.ok) {
    await rememberDownloaded(targetUrl);
    // Download request sent to HDM; modal will display on desktop without forcing main window
    return { ok: true };
  }
  if (res && res.mode === "cancelled") {
    // The user declined in HDM: a valid outcome, not a connection failure.
    return { ok: true, cancelled: true };
  }
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "HDM Download Manager",
    message: "Không thể kết nối với ứng dụng HDM. Vui lòng kiểm tra cổng kết nối hoặc mở HDM.",
  });
  return { ok: false, error: "Cannot connect to HDM" };
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
    handleMediaDownload(req.data, sender).then(sendResponse);
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
      chrome.action.setBadgeText({ tabId, text: "" })?.catch?.(() => {});
    }
    sendResponse({ ok: true });
    return true;
  }
});
