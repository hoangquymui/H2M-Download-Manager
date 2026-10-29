/**
 * HDM Browser Extension - Video Download Sniffer
 * Ultra-compact 28px icon button with top-right 'x' dismiss badge,
 * ALWAYS mounted on window.top.document.body and positioned strictly
 * OUTSIDE the video/stream player box so it never overlaps video controls
 * and is never clipped by overflow:hidden or iframe boundaries.
 */

(function () {
  "use strict";

  if (window.__HDM_CONTENT_SCRIPT_LOADED__) return;
  window.__HDM_CONTENT_SCRIPT_LOADED__ = true;

  const IS_TOP_WINDOW = window === window.top;

  // =========================================================================
  // 1. Sub-frame (iframe) Handler: Never draw UI inside an iframe!
  //    Sniff Resource Timing & DOM inside the iframe and forward stream URLs
  //    to window.top via postMessage.
  // =========================================================================
  if (!IS_TOP_WINDOW) {
    let notifiedStream = "";
    let lastManifestKey = "";
    let mainManifest = "";
    let mainStreamUrl = "";
    let mainQualities = [];

    // Content scripts live in an isolated world and cannot read page JS globals
    // (jwplayer, hls.js). main_world.js forwards captured playlists via postMessage.
    window.addEventListener("message", (e) => {
      const d = e.data;
      if (!d || d.__hdm_main !== true) return;

      if (d.type === "HDM_MAIN_MANIFEST" && typeof d.manifest === "string") {
        const text = d.manifest;
        if (text.indexOf("#EXTM3U") === -1) return;
        const qualities = Array.isArray(d.qualities) ? d.qualities : [];
        const qualityKey = qualities.map((q) => q.label || q.height || q.manifest.length).join(",");
        const key = `${text.length}:${text.slice(0, 48)}:${text.slice(-32)}:${qualityKey}`;
        if (key === lastManifestKey) return;
        // Prefer a media playlist (#EXTINF) over a master playlist: relative
        // variant URIs in a master cannot resolve when downloaded from a file.
        if (mainManifest.indexOf("#EXTINF") !== -1 && text.indexOf("#EXTINF") === -1) return;
        lastManifestKey = key;
        mainManifest = text;
        mainQualities = qualities;
        notifyParent();
      } else if (d.type === "HDM_MAIN_STREAM_URL" && typeof d.url === "string") {
        if (!/^https?:/i.test(d.url) || d.url === mainStreamUrl) return;
        mainStreamUrl = d.url;
        notifyParent();
      }
    });

    function findStreamInSubframe() {
      // 1. Check Resource Timing API (m3u8, mpd, mp4 loaded by hls.js / playerjs)
      try {
        const entries = performance.getEntriesByType("resource");
        for (let i = entries.length - 1; i >= 0; i--) {
          const name = entries[i].name;
          if (typeof name === "string") {
            const clean = name.toLowerCase().split("?")[0].split("#")[0];
            if (
              (clean.endsWith(".m3u8") || name.toLowerCase().includes("m3u8") || name.toLowerCase().includes("/hls/")) &&
              !clean.endsWith(".ts") &&
              !clean.endsWith(".key") &&
              !clean.endsWith(".js")
            ) {
              return entries[i].name;
            }
            if (clean.endsWith(".mpd") && !clean.endsWith(".m4s")) {
              return entries[i].name;
            }
            if (clean.endsWith(".mp4") || clean.endsWith(".webm") || clean.endsWith(".mkv")) {
              return entries[i].name;
            }
          }
        }
      } catch (e) {}

      // 2. Check HTML5 <video> elements
      const vid = document.querySelector("video");
      if (vid) {
        const src = vid.currentSrc || vid.src || "";
        if (src && !src.startsWith("blob:")) {
          return src;
        }
        const sources = vid.querySelectorAll("source");
        for (const s of sources) {
          if (s.src && !s.src.startsWith("blob:")) {
            return s.src;
          }
        }
      }
      return "";
    }

    function notifyParent() {
      const streamUrl = mainStreamUrl || findStreamInSubframe();
      const vid = document.querySelector("video");

      if (mainStreamUrl || mainManifest) {
        const url = mainStreamUrl || document.referrer || window.location.href;
        const qualityKey = mainQualities.map((q) => q.label || q.height || "").join(",");
        const key = mainStreamUrl
          ? `u:${mainStreamUrl}`
          : `m:${mainManifest.length}:${mainManifest.slice(0, 48)}:${mainManifest.slice(-32)}:${qualityKey}`;
        if (key !== notifiedStream) {
          notifiedStream = key;
          try {
            window.parent.postMessage(
              {
                type: "HDM_CHILD_STREAM",
                url: url,
                manifest: mainManifest || "",
                qualities: mainQualities,
                title: document.title || "",
              },
              "*"
            );
          } catch (e) {}
        }
        return;
      }

      if (!vid && !streamUrl) return;

      if (streamUrl && streamUrl !== notifiedStream) {
        notifiedStream = streamUrl;
        try {
          window.parent.postMessage(
            {
              type: "HDM_CHILD_STREAM",
              url: streamUrl,
              title: document.title || "",
            },
            "*"
          );
        } catch (e) {}
      } else {
        try {
          window.parent.postMessage(
            {
              type: "HDM_CHILD_VIDEO",
              title: document.title || "",
            },
            "*"
          );
        } catch (e) {}
      }
    }

    // Forward nested iframe messages up to window.top
    window.addEventListener("message", (e) => {
      if (e.data && (e.data.type === "HDM_CHILD_VIDEO" || e.data.type === "HDM_CHILD_STREAM")) {
        try {
          window.parent.postMessage(e.data, "*");
        } catch (err) {}
      }
    });

    const subObserver = new MutationObserver(() => {
      notifyParent();
    });
    subObserver.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src"],
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", notifyParent);
    } else {
      notifyParent();
    }
    setTimeout(notifyParent, 800);
    setTimeout(notifyParent, 2000);
    setTimeout(notifyParent, 4000);
    return;
  }

  // =========================================================================
  // 2. Top-Level Window Handler: Render Button & Menu on document.body
  //    strictly OUTSIDE any video / stream player box.
  // =========================================================================

  const SVG_DOWNLOAD_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 4v11m-5-5 5 5 5-5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
    </svg>
  `;

  const SVG_CHECK_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
  `;

  const SVG_ALERT_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="8" x2="12" y2="12"></line>
      <line x1="12" y1="16" x2="12.01" y2="16"></line>
    </svg>
  `;

  const PLAYER_BOX_SELECTORS = [
    "#halim-player-wrapper",
    "#ajax-player-hh3d",
    ".playerjs-mount-slot",
    ".halim-player-aspect",
    ".halim-playerjs-host",
    "#movie_player",
    ".html5-video-player",
    "#player-container-outer",
    "ytd-player",
    "#player",
    ".watch-player",
    ".film-player",
    "#video-player",
    ".video-player",
    ".artplayer-app",
    ".dplayer",
    ".jwplayer",
    ".video-js",
    ".plyr",
  ];

  let lastSniffedMedia = null;
  let lastCapturedManifest = "";
  let lastCapturedQualities = [];
  let lastCapturedQualitiesKey = "";
  const activeButtons = []; // Array of { targetEl, wrap, btn, qualityMenu, updatePos, mediaOverride }

  // Query background for already sniffed media streams on page load
  function syncCapturedMediaFromBackground() {
    try {
      chrome.runtime.sendMessage({ action: "get_captured_media" }, (res) => {
        if (chrome.runtime.lastError) return;
        if (res && res.media && res.media.length > 0) {
          lastSniffedMedia = res.media[0];
          activeButtons.forEach((entry) => {
            if (!entry.mediaOverride) entry.mediaOverride = lastSniffedMedia;
          });
        }
      });
    } catch (e) {}
  }
  syncCapturedMediaFromBackground();

  function isYouTube() {
    const host = (window.location.hostname || "").toLowerCase();
    return ["youtube.com", "youtube-nocookie.com", "youtu.be"].some(
      (domain) => host === domain || host.endsWith("." + domain)
    );
  }

  function getVideoTitle() {
    if (isYouTube()) {
      const ytTitle =
        document.querySelector("h1.ytd-watch-metadata yt-formatted-string") ||
        document.querySelector("#title h1 yt-formatted-string") ||
        document.querySelector("h1.title");
      if (ytTitle && ytTitle.textContent.trim()) {
        return ytTitle.textContent.trim();
      }
      return document.title.replace(/ - YouTube$/, "").trim() || "YouTube Video";
    }

    if (lastSniffedMedia && lastSniffedMedia.title) {
      return lastSniffedMedia.title;
    }

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && ogTitle.content) {
      return ogTitle.content.trim();
    }

    return document.title.trim() || "Video";
  }

  /**
   * Scan top window's Resource Timing for any m3u8/mpd/video stream.
   */
  function findStreamUrlInTopWindow() {
    try {
      const entries = performance.getEntriesByType("resource");
      for (let i = entries.length - 1; i >= 0; i--) {
        const name = entries[i].name;
        if (typeof name === "string") {
          const clean = name.toLowerCase().split("?")[0].split("#")[0];
          if (
            (clean.endsWith(".m3u8") || name.toLowerCase().includes("m3u8") || name.toLowerCase().includes("/hls/")) &&
            !clean.endsWith(".ts") &&
            !clean.endsWith(".key") &&
            !clean.endsWith(".js")
          ) {
            return entries[i].name;
          }
          if (clean.endsWith(".mpd") && !clean.endsWith(".m4s")) {
            return entries[i].name;
          }
          if (clean.endsWith(".mp4") || clean.endsWith(".webm") || clean.endsWith(".mkv")) {
            return entries[i].name;
          }
        }
      }
    } catch (e) {}
    return null;
  }

  /**
   * Given a <video>, <iframe>, or inner player element, resolve the outermost
   * player container whose bounding rect represents the video/stream box.
   */
  function resolvePlayerBox(el) {
    if (!el || el === document.body || el === document.documentElement) return null;

    if (isYouTube()) {
      const ytBox =
        el.closest("#movie_player, #player-container-outer, ytd-player, #player") ||
        document.querySelector("#movie_player") ||
        document.querySelector("#player");
      if (ytBox && ytBox.offsetWidth >= 160 && ytBox.offsetHeight >= 100) {
        return ytBox;
      }
    }

    const outerSelector = PLAYER_BOX_SELECTORS.join(", ");
    const matchedWrapper = el.closest(outerSelector);
    if (matchedWrapper && matchedWrapper.offsetWidth >= 160 && matchedWrapper.offsetHeight >= 100) {
      return matchedWrapper;
    }

    return el;
  }

  let toastTimer = null;

  function showToast(msg, isError) {
    let toast = document.querySelector(".hdm-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "hdm-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = `hdm-toast show ${isError ? "error" : "success"}`;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastTimer = null;
      toast.className = "hdm-toast";
    }, 4000);
  }

  function getVideoSource(videoOrBox) {
    if (isYouTube()) {
      return window.location.href;
    }

    if (lastSniffedMedia && lastSniffedMedia.url) {
      return lastSniffedMedia.url;
    }

    const perfStream = findStreamUrlInTopWindow();
    if (perfStream) {
      return perfStream;
    }

    if (videoOrBox) {
      if (videoOrBox.__hdm_stream_url__) {
        return videoOrBox.__hdm_stream_url__;
      }

      const vid =
        videoOrBox.tagName === "VIDEO"
          ? videoOrBox
          : videoOrBox.querySelector
          ? videoOrBox.querySelector("video")
          : null;
      if (vid) {
        const rawSrc = vid.currentSrc || vid.src;
        if (rawSrc && !rawSrc.startsWith("blob:")) {
          return rawSrc;
        }
        const sources = vid.querySelectorAll("source");
        for (const s of sources) {
          if (s.src && !s.src.startsWith("blob:")) {
            return s.src;
          }
        }
      }
    }
    return window.location.href;
  }

  async function triggerDownload(formatType, qualityType, sourceBtn, targetEl, mediaOverride) {
    const originalHtml = sourceBtn ? sourceBtn.innerHTML : "";
    if (sourceBtn) {
      sourceBtn.classList.add("loading");
      sourceBtn.setAttribute("title", "Đang kết nối HDM...");
    }

    function showConnectError() {
      if (sourceBtn) {
        sourceBtn.classList.remove("loading");
        sourceBtn.classList.add("error");
        sourceBtn.innerHTML = SVG_ALERT_ICON;
        sourceBtn.setAttribute(
          "title",
          "Không thể kết nối với HDM. Vui lòng mở ứng dụng HDM trên máy tính!"
        );
        setTimeout(() => {
          sourceBtn.classList.remove("error");
          sourceBtn.innerHTML = originalHtml;
          sourceBtn.setAttribute("title", "Tải video này với HDM");
        }, 3000);
      }
      showToast("⚠️ Vui lòng mở ứng dụng HDM (HDM.exe) trên máy tính trước khi bấm tải!", true);
    }

    const pageUrl = window.location.href;
    const manifest =
      (mediaOverride && mediaOverride.manifest) ||
      (lastSniffedMedia && lastSniffedMedia.manifest) ||
      lastCapturedManifest ||
      "";
    const qualities =
      (mediaOverride && mediaOverride.qualities && mediaOverride.qualities.length && mediaOverride.qualities) ||
      (lastSniffedMedia && lastSniffedMedia.qualities && lastSniffedMedia.qualities.length && lastSniffedMedia.qualities) ||
      lastCapturedQualities ||
      [];

    // Refresh captured media from background before triggering
    let finalTargetUrl =
      (mediaOverride && mediaOverride.url) ||
      (lastSniffedMedia && lastSniffedMedia.url) ||
      getVideoSource(targetEl);

    // If still resolved to page HTML, try background synchronously
    if (
      !manifest &&
      !isYouTube() &&
      (!finalTargetUrl ||
        finalTargetUrl === pageUrl ||
        finalTargetUrl.endsWith(".html") ||
        finalTargetUrl.endsWith(".htm"))
    ) {
      try {
        const res = await new Promise((resolve) => {
          chrome.runtime.sendMessage({ action: "get_captured_media" }, resolve);
        });
        if (res && res.media && res.media.length > 0) {
          finalTargetUrl = res.media[0].url;
          lastSniffedMedia = res.media[0];
        }
      } catch (e) {}
    }

    const title =
      (mediaOverride && mediaOverride.title) ||
      (lastSniffedMedia && lastSniffedMedia.title) ||
      getVideoTitle();

    const isStreamManifest =
      finalTargetUrl.includes(".m3u8") ||
      finalTargetUrl.includes(".mpd") ||
      !!manifest;

    const message = {
      action: "download_media",
      data: {
        url: finalTargetUrl,
        pageUrl: pageUrl,
        title: title,
        format: formatType || "mp4",
        quality: qualityType || "",
        ext: mediaOverride && mediaOverride.ext ? mediaOverride.ext : (formatType === "mp3" ? "mp3" : "mp4"),
        manifest: manifest,
        qualities: qualities,
        isStreaming: isYouTube() || isStreamManifest || finalTargetUrl === pageUrl,
      },
    };

    try {
      chrome.runtime.sendMessage(message, (res) => {
        const lastErr = chrome.runtime.lastError;
        if (sourceBtn) sourceBtn.classList.remove("loading");

        if (lastErr || !res || !res.ok) {
          showConnectError();
        } else if (res.cancelled) {
          showToast("Đã huỷ tải trong HDM.", false);
        } else {
          if (sourceBtn) {
            sourceBtn.classList.add("success");
            sourceBtn.innerHTML = SVG_CHECK_ICON;
            sourceBtn.setAttribute("title", "✓ Đã gửi lệnh tải tới HDM!");
            setTimeout(() => {
              sourceBtn.classList.remove("success");
              sourceBtn.innerHTML = originalHtml;
              sourceBtn.setAttribute("title", "Tải video này với HDM");
            }, 2500);
          }
        }
      });
    } catch (e) {
      // The extension was reloaded/updated: this page's context is dead.
      showConnectError();
    }
  }

  function isAlreadyTracked(candidateEl) {
    for (let i = activeButtons.length - 1; i >= 0; i--) {
      const entry = activeButtons[i];
      if (!entry.targetEl || !entry.targetEl.isConnected) {
        entry.wrap.remove();
        entry.qualityMenu.remove();
        activeButtons.splice(i, 1);
        continue;
      }
      if (
        entry.targetEl === candidateEl ||
        entry.targetEl.contains(candidateEl) ||
        candidateEl.contains(entry.targetEl)
      ) {
        return entry;
      }
      const r1 = entry.targetEl.getBoundingClientRect();
      const r2 = candidateEl.getBoundingClientRect();
      if (
        r1.width > 0 &&
        r2.width > 0 &&
        Math.abs(r1.top - r2.top) < 30 &&
        Math.abs(r1.left - r2.left) < 30
      ) {
        return entry;
      }
    }
    return null;
  }

  function isCoveredByFixedHeader(x, y, playerEl) {
    if (y < 4) return true;
    try {
      const elAtPoint = document.elementFromPoint(x, y);
      if (!elAtPoint || playerEl.contains(elAtPoint)) return false;
      let cur = elAtPoint;
      while (cur && cur !== document.body && cur !== document.documentElement) {
        if (cur.classList && (cur.classList.contains("hdm-btn-wrap") || cur.classList.contains("hdm-quality-menu"))) {
          return false;
        }
        const style = window.getComputedStyle(cur);
        if ((style.position === "fixed" || style.position === "sticky") && cur.getBoundingClientRect().bottom >= y) {
          return true;
        }
        cur = cur.parentElement;
      }
    } catch (e) {}
    return false;
  }

  function buildQualityMenuHtml() {
    return `
      <div class="hdm-menu-sec">🎬 Tải Video (MP4)</div>
      <div class="hdm-menu-item" data-format="mp4" data-quality="1080">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎬</span>
          <span class="hdm-menu-text">MP4 1080p (Full HD / 1K)</span>
        </div>
        <span class="hdm-badge-q">1080p</span>
      </div>
      <div class="hdm-menu-item" data-format="mp4" data-quality="720">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎬</span>
          <span class="hdm-menu-text">MP4 720p (HD)</span>
        </div>
        <span class="hdm-badge-q">720p</span>
      </div>
      <div class="hdm-menu-item" data-format="mp4" data-quality="480">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎬</span>
          <span class="hdm-menu-text">MP4 480p (Tiêu chuẩn)</span>
        </div>
        <span class="hdm-badge-q">480p</span>
      </div>
      <div class="hdm-menu-item" data-format="mp4" data-quality="360">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎬</span>
          <span class="hdm-menu-text">MP4 360p (Tiết kiệm)</span>
        </div>
        <span class="hdm-badge-q">360p</span>
      </div>
      <div class="hdm-menu-item" data-format="mp4" data-quality="">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">⚡</span>
          <span class="hdm-menu-text">Tự động (Chất lượng cao nhất)</span>
        </div>
        <span class="hdm-badge-q auto">AUTO</span>
      </div>

      <div class="hdm-divider"></div>

      <div class="hdm-menu-sec">🎵 Tải Âm Thanh (MP3)</div>
      <div class="hdm-menu-item" data-format="mp3" data-quality="320">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎵</span>
          <span class="hdm-menu-text">MP3 320 kbps (Cao nhất)</span>
        </div>
        <span class="hdm-badge-q audio">320k</span>
      </div>
      <div class="hdm-menu-item" data-format="mp3" data-quality="192">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎵</span>
          <span class="hdm-menu-text">MP3 192 kbps (Chuẩn)</span>
        </div>
        <span class="hdm-badge-q audio">192k</span>
      </div>
      <div class="hdm-menu-item" data-format="mp3" data-quality="128">
        <div class="hdm-menu-item-left">
          <span class="hdm-menu-icon">🎵</span>
          <span class="hdm-menu-text">MP3 128 kbps (Cơ bản)</span>
        </div>
        <span class="hdm-badge-q audio">128k</span>
      </div>
    `;
  }

  /**
   * Mount the download button on document.body and dock it strictly OUTSIDE playerBox.
   */
  function createOutsideButton(playerBox, mediaOverride) {
    const targetEl = resolvePlayerBox(playerBox);
    if (!targetEl || targetEl.__hdm_dismissed__) return;

    const existing = isAlreadyTracked(targetEl);
    if (existing) {
      if (mediaOverride) existing.mediaOverride = mediaOverride;
      existing.updatePos();
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "hdm-btn-wrap";

    const btn = document.createElement("div");
    btn.className = "hdm-outside-btn";
    btn.setAttribute("title", "Tải video với HDM (Nhấn để chọn chất lượng)");
    btn.innerHTML = SVG_DOWNLOAD_ICON;

    const closeBtn = document.createElement("div");
    closeBtn.className = "hdm-close-x";
    closeBtn.setAttribute("title", "Ẩn nút tải");
    closeBtn.innerHTML = "&times;";

    const qualityMenu = document.createElement("div");
    qualityMenu.className = "hdm-quality-menu";
    qualityMenu.innerHTML = buildQualityMenuHtml();

    document.body.appendChild(wrap);
    document.body.appendChild(qualityMenu);

    wrap.appendChild(btn);
    wrap.appendChild(closeBtn);

    const entry = {
      targetEl: targetEl,
      wrap: wrap,
      btn: btn,
      qualityMenu: qualityMenu,
      mediaOverride: mediaOverride || null,
      updatePos: updatePlacement,
      lastTop: 0,
      lastLeft: 0,
    };
    activeButtons.push(entry);

    function repositionMenu() {
      if (!qualityMenu.classList.contains("show")) return;
      const rect = btn.getBoundingClientRect();
      const menuH = qualityMenu.offsetHeight || 310;
      let top = rect.bottom + 6;
      if (top + menuH > window.innerHeight && rect.top > menuH + 10) {
        top = rect.top - menuH - 6;
      }
      qualityMenu.style.top = `${Math.max(6, top)}px`;
      qualityMenu.style.left = `${Math.max(8, Math.min(window.innerWidth - 275, rect.left))}px`;
    }

    function updatePlacement() {
      if (!targetEl.isConnected) {
        wrap.style.setProperty("display", "none", "important");
        qualityMenu.classList.remove("show");
        return;
      }
      if (document.fullscreenElement) {
        wrap.style.setProperty("display", "none", "important");
        qualityMenu.classList.remove("show");
        return;
      }

      const rect = targetEl.getBoundingClientRect();
      if (rect.width < 120 || rect.height < 80) {
        wrap.style.setProperty("display", "none", "important");
        return;
      }

      wrap.style.setProperty("display", "inline-flex", "important");

      const leftPage = Math.round(window.scrollX + Math.max(6, rect.left + 4));
      const candidateTopViewportY = rect.top - 20;

      // Place strictly ABOVE top-left of video box if space above is clear;
      // otherwise place strictly BELOW bottom-left of video box.
      let topPage;
      if (rect.top >= 38 && !isCoveredByFixedHeader(rect.left + 18, candidateTopViewportY, targetEl)) {
        topPage = Math.round(window.scrollY + rect.top - 34);
      } else {
        topPage = Math.round(window.scrollY + rect.bottom + 6);
      }

      if (Math.abs(entry.lastTop - topPage) > 1 || Math.abs(entry.lastLeft - leftPage) > 1) {
        entry.lastTop = topPage;
        entry.lastLeft = leftPage;
        wrap.style.setProperty("top", `${topPage}px`, "important");
        wrap.style.setProperty("left", `${leftPage}px`, "important");
        repositionMenu();
      }
    }

    updatePlacement();

    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      targetEl.__hdm_dismissed__ = true;
      qualityMenu.remove();
      wrap.style.opacity = "0";
      wrap.style.transform = "scale(0.8)";
      setTimeout(() => {
        wrap.remove();
        const idx = activeButtons.indexOf(entry);
        if (idx !== -1) activeButtons.splice(idx, 1);
      }, 200);
    });

    function toggleMenu(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }

      if (qualityMenu.classList.contains("show")) {
        qualityMenu.classList.remove("show");
        return;
      }

      // Close other open quality menus
      document.querySelectorAll(".hdm-quality-menu.show").forEach((m) => {
        if (m !== qualityMenu) m.classList.remove("show");
      });

      qualityMenu.classList.add("show");
      repositionMenu();
    }

    btn.addEventListener("click", toggleMenu);
    btn.addEventListener("contextmenu", toggleMenu);

    let isRequesting = false;
    qualityMenu.addEventListener("click", (e) => {
      e.stopPropagation();
      const item = e.target.closest(".hdm-menu-item");
      if (item) {
        if (isRequesting) return;
        isRequesting = true;
        setTimeout(() => {
          isRequesting = false;
        }, 1200);

        const fmt = item.getAttribute("data-format");
        const q = item.getAttribute("data-quality") || "";
        qualityMenu.classList.remove("show");
        triggerDownload(fmt, q, btn, targetEl, entry.mediaOverride);
      }
    });
  }

  // A single document-level listener closes any open menu. Clicks on a button
  // or inside a menu stop propagation, so they never reach this handler.
  // Registering one listener here (instead of one per button) keeps the page
  // from accumulating handlers when players are re-mounted by the site.
  document.addEventListener("click", () => {
    document.querySelectorAll(".hdm-quality-menu.show").forEach((menu) => {
      menu.classList.remove("show");
    });
  });

  function updateAllPlacements() {
    for (const entry of activeButtons) {
      entry.updatePos();
    }
  }

  window.addEventListener("scroll", updateAllPlacements, { passive: true });
  window.addEventListener("resize", updateAllPlacements, { passive: true });
  document.addEventListener("fullscreenchange", updateAllPlacements);

  /**
   * Scan page for any video element or player wrapper with debouncing.
   */
  let scanDebounceTimer = null;
  function scanVideos() {
    if (scanDebounceTimer) return;
    scanDebounceTimer = setTimeout(() => {
      scanDebounceTimer = null;
      doScanVideos();
    }, 300);
  }

  function doScanVideos() {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      // 1. Known video/stream player containers
      for (const sel of PLAYER_BOX_SELECTORS) {
        const boxes = document.querySelectorAll(sel);
        boxes.forEach((box) => {
          if (box.offsetWidth >= 160 && box.offsetHeight >= 100) {
            createOutsideButton(box);
          }
        });
      }

      // 2. Direct <video> elements
      const videos = document.querySelectorAll("video");
      videos.forEach((vid) => {
        if (vid.offsetWidth < 120 && vid.offsetHeight < 80 && !isYouTube()) return;
        createOutsideButton(vid);
      });

      // 3. Embedded video/stream iframes
      const iframes = document.querySelectorAll(
        "iframe[src*='player'], iframe[src*='embed'], iframe[src*='video'], iframe[src*='stream'], iframe[src*='hls'], iframe[src*='m3u8'], iframe[allowfullscreen]"
      );
      iframes.forEach((ifr) => {
        if (ifr.offsetWidth >= 200 && ifr.offsetHeight >= 120) {
          createOutsideButton(ifr);
        }
      });

      updateAllPlacements();
    });
  }

  // Listen for child iframe video or stream detection via postMessage
  window.addEventListener("message", (e) => {
    if (!e.data) return;

    if (e.data.type === "HDM_CHILD_STREAM" && e.data.url) {
      const childManifest = typeof e.data.manifest === "string" ? e.data.manifest : "";
      const childQualities = Array.isArray(e.data.qualities) ? e.data.qualities : [];
      if (childManifest) lastCapturedManifest = childManifest;
      if (childQualities.length) lastCapturedQualities = childQualities;
      lastSniffedMedia = {
        url: e.data.url,
        title: e.data.title || getVideoTitle(),
        ext: e.data.url.includes(".mp3") ? "mp3" : "mp4",
        manifest: childManifest,
        qualities: childQualities,
      };
      const iframes = document.querySelectorAll("iframe");
      for (const ifr of iframes) {
        try {
          if (ifr.contentWindow === e.source) {
            ifr.__hdm_stream_url__ = e.data.url;
            createOutsideButton(ifr, lastSniffedMedia);
            break;
          }
        } catch (err) {}
      }
      activeButtons.forEach((entry) => {
        entry.mediaOverride = lastSniffedMedia;
      });
      scanVideos();
    } else if (e.data.type === "HDM_CHILD_VIDEO") {
      const iframes = document.querySelectorAll("iframe");
      for (const ifr of iframes) {
        try {
          if (ifr.contentWindow === e.source) {
            createOutsideButton(ifr);
            break;
          }
        } catch (err) {}
      }
      scanVideos();
    }
  });

  // Receive playlists / stream URLs captured by main_world.js in this document
  window.addEventListener("message", (e) => {
    const d = e.data;
    if (!d || d.__hdm_main !== true) return;

    if (d.type === "HDM_MAIN_MANIFEST" && typeof d.manifest === "string" && d.manifest.indexOf("#EXTM3U") !== -1) {
      const qualities = Array.isArray(d.qualities) ? d.qualities : [];
      const qualitiesKey = qualities
        .map((q) => `${q.label || ""}:${(q.manifest || "").length}`)
        .join("|");
      if (
        lastSniffedMedia &&
        lastSniffedMedia.manifest === d.manifest &&
        lastCapturedQualitiesKey === qualitiesKey
      ) {
        return;
      }
      lastCapturedQualitiesKey = qualitiesKey;
      lastCapturedManifest = d.manifest;
      lastCapturedQualities = qualities;
      lastSniffedMedia = {
        url: window.location.href,
        title: getVideoTitle(),
        ext: "mp4",
        manifest: d.manifest,
        qualities: qualities,
      };
      activeButtons.forEach((entry) => {
        entry.mediaOverride = lastSniffedMedia;
      });
      scanVideos();
    } else if (d.type === "HDM_MAIN_STREAM_URL" && typeof d.url === "string" && /^https?:/i.test(d.url)) {
      if (lastSniffedMedia && lastSniffedMedia.manifest) return;
      if (lastSniffedMedia && lastSniffedMedia.url === d.url) return;
      lastSniffedMedia = {
        url: d.url,
        title: getVideoTitle(),
        ext: "mp4",
      };
      activeButtons.forEach((entry) => {
        entry.mediaOverride = lastSniffedMedia;
      });
      scanVideos();
    }
  });

  // Listen for sniffed media messages from background service worker
  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.action === "hdm_media_detected" && req.media) {
      lastSniffedMedia = req.media;
      activeButtons.forEach((entry) => {
        entry.mediaOverride = req.media;
      });
      scanVideos();
      sendResponse({ ok: true });
    } else if (req.action === "get_page_stream") {
      const media = lastSniffedMedia ? { ...lastSniffedMedia } : null;
      if (media) {
        media.manifest = lastCapturedManifest || media.manifest || "";
        media.qualities = lastCapturedQualities.length ? lastCapturedQualities : media.qualities || [];
      }
      sendResponse({ ok: true, media });
    }
  });

  const observer = new MutationObserver(() => {
    scanVideos();
  });

  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.addEventListener("yt-navigate-finish", () => {
    setTimeout(scanVideos, 400);
  });
  window.addEventListener("popstate", () => {
    setTimeout(scanVideos, 400);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanVideos);
  } else {
    scanVideos();
  }

  // Periodic layout sync for dynamic players
  setInterval(updateAllPlacements, 1500);
})();
