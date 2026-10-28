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
  //    Forward video detection to the top-level page so the button is
  //    placed strictly OUTSIDE the iframe / player container.
  // =========================================================================
  if (!IS_TOP_WINDOW) {
    let notifiedSrc = "";

    function notifyParentOfVideo() {
      const vid = document.querySelector("video");
      if (!vid) return;
      const src = vid.currentSrc || vid.src || "";
      if (src === notifiedSrc && notifiedSrc !== "") return;
      notifiedSrc = src || "iframe_video";
      try {
        window.parent.postMessage(
          {
            type: "HDM_CHILD_VIDEO",
            src: src && !src.startsWith("blob:") ? src : "",
            title: document.title || "",
          },
          "*"
        );
      } catch (e) {}
    }

    // Forward nested iframe messages up to window.top
    window.addEventListener("message", (e) => {
      if (e.data && e.data.type === "HDM_CHILD_VIDEO") {
        try {
          window.parent.postMessage(e.data, "*");
        } catch (err) {}
      }
    });

    const subObserver = new MutationObserver(notifyParentOfVideo);
    subObserver.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src"],
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", notifyParentOfVideo);
    } else {
      notifyParentOfVideo();
    }
    setTimeout(notifyParentOfVideo, 1000);
    setTimeout(notifyParentOfVideo, 3000);
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
  const activeButtons = []; // Array of { targetEl, wrap, qualityMenu, updatePos, mediaOverride }

  function isYouTube() {
    return (
      window.location.hostname.includes("youtube.com") ||
      window.location.hostname.includes("youtu.be")
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
   * Given a <video>, <iframe>, or inner player element, resolve the clean
   * outer video/stream player box whose bounding rect represents the player frame.
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

  function showToast(msg, isError) {
    let toast = document.querySelector(".hdm-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "hdm-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = `hdm-toast show ${isError ? "error" : "success"}`;
    setTimeout(() => {
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
    if (videoOrBox) {
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
      if (videoOrBox.__hdm_iframe_src__) {
        return videoOrBox.__hdm_iframe_src__;
      }
    }
    return window.location.href;
  }

  function triggerDownload(formatType, qualityType, sourceBtn, targetEl, mediaOverride) {
    const originalHtml = sourceBtn ? sourceBtn.innerHTML : "";
    if (sourceBtn) {
      sourceBtn.classList.add("loading");
      sourceBtn.setAttribute("title", "Đang kết nối HDM...");
    }

    const pageUrl = window.location.href;
    const targetUrl =
      (mediaOverride && mediaOverride.url) ||
      (lastSniffedMedia && lastSniffedMedia.url) ||
      getVideoSource(targetEl);

    const title =
      (mediaOverride && mediaOverride.title) ||
      getVideoTitle();

    const isStreamManifest = targetUrl.includes(".m3u8") || targetUrl.includes(".mpd");

    chrome.runtime.sendMessage(
      {
        action: "download_media",
        data: {
          url: targetUrl,
          pageUrl: pageUrl,
          title: title,
          format: formatType || "mp4",
          quality: qualityType || "",
          ext: mediaOverride && mediaOverride.ext ? mediaOverride.ext : (formatType === "mp3" ? "mp3" : "mp4"),
          isStreaming: isYouTube() || isStreamManifest || targetUrl === pageUrl,
        },
      },
      (res) => {
        const lastErr = chrome.runtime.lastError;
        if (sourceBtn) sourceBtn.classList.remove("loading");

        if (lastErr || !res || !res.ok) {
          if (sourceBtn) {
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
        } else {
          if (sourceBtn) {
            sourceBtn.classList.add("success");
            sourceBtn.innerHTML = SVG_CHECK_ICON;
            sourceBtn.setAttribute("title", "✓ Đã mở HDM thành công!");
            setTimeout(() => {
              sourceBtn.classList.remove("success");
              sourceBtn.innerHTML = originalHtml;
              sourceBtn.setAttribute("title", "Tải video này với HDM");
            }, 2500);
          }
        }
      }
    );
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
        Math.abs(r1.top - r2.top) < 40 &&
        Math.abs(r1.left - r2.left) < 40
      ) {
        return entry;
      }
    }
    return null;
  }

  /**
   * Check if a viewport coordinate (x, y) is covered by a fixed/sticky top header
   * (such as YouTube's masthead bar).
   */
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

    // Remove fallback fixed button if a real player box is now available
    const fixedBtn = document.querySelector(".hdm-btn-wrap.hdm-pos-fixed");
    if (fixedBtn) fixedBtn.remove();

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
    btn.setAttribute("title", "Tải video với HDM (Bấm để chọn định dạng & chất lượng)");
    btn.innerHTML = SVG_DOWNLOAD_ICON;

    const closeBtn = document.createElement("div");
    closeBtn.className = "hdm-close-x";
    closeBtn.setAttribute("title", "Ẩn nút tải này");
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
      qualityMenu: qualityMenu,
      mediaOverride: mediaOverride || null,
      updatePos: updatePlacement,
    };
    activeButtons.push(entry);

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

      // Place strictly ABOVE the top-left of the video box if space above is clear;
      // otherwise place strictly BELOW the bottom-left of the video box.
      let topPage;
      if (rect.top >= 38 && !isCoveredByFixedHeader(rect.left + 18, candidateTopViewportY, targetEl)) {
        topPage = Math.round(window.scrollY + rect.top - 34);
      } else {
        topPage = Math.round(window.scrollY + rect.bottom + 6);
      }

      wrap.style.setProperty("top", `${topPage}px`, "important");
      wrap.style.setProperty("left", `${leftPage}px`, "important");
    }

    updatePlacement();

    let resizeObs = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObs = new ResizeObserver(updatePlacement);
      resizeObs.observe(targetEl);
    }

    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      targetEl.__hdm_dismissed__ = true;
      if (resizeObs) resizeObs.disconnect();
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

      document.querySelectorAll(".hdm-quality-menu.show").forEach((m) => {
        if (m !== qualityMenu) m.classList.remove("show");
      });

      qualityMenu.style.visibility = "hidden";
      qualityMenu.classList.add("show");
      const menuH = qualityMenu.offsetHeight || 310;
      qualityMenu.style.visibility = "";

      const rect = btn.getBoundingClientRect();
      let top = rect.bottom + 6;
      if (top + menuH > window.innerHeight && rect.top > menuH + 10) {
        top = rect.top - menuH - 6;
      }
      qualityMenu.style.top = `${Math.max(6, top)}px`;
      qualityMenu.style.left = `${Math.max(8, Math.min(window.innerWidth - 270, rect.left))}px`;
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

    document.addEventListener("click", (e) => {
      if (!qualityMenu.contains(e.target) && !btn.contains(e.target)) {
        qualityMenu.classList.remove("show");
      }
    });
  }

  function updateAllPlacements() {
    for (const entry of activeButtons) {
      entry.updatePos();
      if (entry.qualityMenu.classList.contains("show")) {
        entry.qualityMenu.classList.remove("show");
      }
    }
  }

  window.addEventListener("scroll", updateAllPlacements, { passive: true });
  window.addEventListener("resize", updateAllPlacements, { passive: true });
  document.addEventListener("fullscreenchange", updateAllPlacements);

  /**
   * Scan the page for any video element, known player wrapper, or video iframe.
   */
  function scanVideos() {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      // 1. Direct <video> elements
      const videos = document.querySelectorAll("video");
      videos.forEach((vid) => {
        if (vid.offsetWidth < 120 && vid.offsetHeight < 80 && !isYouTube()) return;
        createOutsideButton(vid);
      });

      // 2. Known video/stream player containers (Halim, Playerjs, ArtPlayer, JWPlayer, etc.)
      for (const sel of PLAYER_BOX_SELECTORS) {
        const boxes = document.querySelectorAll(sel);
        boxes.forEach((box) => {
          if (box.offsetWidth >= 160 && box.offsetHeight >= 100) {
            createOutsideButton(box);
          }
        });
      }

      // 3. Embedded video/stream iframes
      const iframes = document.querySelectorAll(
        "iframe[src*='player'], iframe[src*='embed'], iframe[src*='video'], iframe[src*='stream'], iframe[src*='hls'], iframe[src*='m3u8'], iframe[allowfullscreen]"
      );
      iframes.forEach((ifr) => {
        if (ifr.offsetWidth >= 220 && ifr.offsetHeight >= 130) {
          createOutsideButton(ifr);
        }
      });

      updateAllPlacements();
    });
  }

  function attachSniffedMediaButton(media) {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      lastSniffedMedia = media;

      // Update any existing tracked button with the sniffed stream metadata
      if (activeButtons.length > 0) {
        activeButtons.forEach((entry) => {
          entry.mediaOverride = media;
          entry.updatePos();
        });
        return;
      }

      // Look for any player container or large iframe on the page
      for (const sel of [...PLAYER_BOX_SELECTORS, "video"]) {
        const el = document.querySelector(sel);
        if (el && el.offsetWidth >= 140 && el.offsetHeight >= 90) {
          createOutsideButton(el, media);
          return;
        }
      }

      const iframes = document.querySelectorAll("iframe");
      for (const ifr of iframes) {
        if (ifr.offsetWidth >= 180 && ifr.offsetHeight >= 110) {
          createOutsideButton(ifr, media);
          return;
        }
      }
    });
  }

  // Listen for child iframe video detection via postMessage
  window.addEventListener("message", (e) => {
    if (!e.data || e.data.type !== "HDM_CHILD_VIDEO") return;
    const iframes = document.querySelectorAll("iframe");
    for (const ifr of iframes) {
      try {
        if (ifr.contentWindow === e.source) {
          if (e.data.src) {
            ifr.__hdm_iframe_src__ = e.data.src;
          }
          createOutsideButton(ifr);
          break;
        }
      } catch (err) {}
    }
  });

  // Listen for sniffed media messages from background service worker
  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.action === "hdm_media_detected" && req.media) {
      lastSniffedMedia = req.media;
      attachSniffedMediaButton(req.media);
      sendResponse({ ok: true });
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
    setTimeout(scanVideos, 600);
  });
  window.addEventListener("popstate", () => {
    setTimeout(scanVideos, 600);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanVideos);
  } else {
    scanVideos();
  }

  // Periodic layout sync for dynamic AJAX players
  setInterval(updateAllPlacements, 1200);
})();
