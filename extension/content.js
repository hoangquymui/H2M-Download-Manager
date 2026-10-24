/**
 * HDM Browser Extension - Video Download Sniffer
 * Icon-only button positioned strictly outside the video viewing box.
 */

(function () {
  "use strict";

  if (window.__HDM_CONTENT_SCRIPT_LOADED__) return;
  window.__HDM_CONTENT_SCRIPT_LOADED__ = true;

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

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && ogTitle.content) {
      return ogTitle.content.trim();
    }

    return document.title.trim() || "Video";
  }

  function findAnchorContainer(video) {
    if (isYouTube()) {
      // On YouTube, #player is outside #movie_player and does not clip
      const ytPlayer =
        document.querySelector("#player") ||
        document.querySelector("ytd-watch-flexy #player") ||
        document.querySelector(".ytd-watch-flexy #player");
      if (ytPlayer) return ytPlayer;
    }

    // Generic sites: find parent container that does not clip overflow
    let container = video.parentElement;
    while (container && container !== document.body) {
      const style = window.getComputedStyle(container);
      if (
        style.overflow !== "hidden" &&
        style.overflowY !== "hidden" &&
        container.offsetWidth >= 200
      ) {
        return container;
      }
      if (container.parentElement === document.body) break;
      container = container.parentElement;
    }

    return container || video.parentElement || video;
  }

  function triggerDownload(formatType, sourceBtn, video) {
    if (sourceBtn) {
      sourceBtn.classList.add("success");
      const originalHtml = sourceBtn.innerHTML;
      sourceBtn.innerHTML = SVG_CHECK_ICON;
      sourceBtn.setAttribute("title", "Đang mở HDM...");

      setTimeout(() => {
        sourceBtn.classList.remove("success");
        sourceBtn.innerHTML = originalHtml;
        sourceBtn.setAttribute("title", "Tải video này với HDM");
      }, 2200);
    }

    const pageUrl = window.location.href;
    let targetUrl = pageUrl;

    if (!isYouTube() && video) {
      const rawSrc = video.currentSrc || video.src;
      if (rawSrc && !rawSrc.startsWith("blob:")) {
        targetUrl = rawSrc;
      }
    }

    chrome.runtime.sendMessage({
      action: "download_media",
      data: {
        url: targetUrl,
        pageUrl: pageUrl,
        title: getVideoTitle(),
        format: formatType || "mp4",
        isStreaming: isYouTube(),
      },
    });
  }

  function createOutsideButton(video, container) {
    if (container.querySelector(".hdm-outside-btn")) return;

    // Ensure container has relative/absolute positioning
    const compStyle = window.getComputedStyle(container);
    if (compStyle.position === "static") {
      container.style.position = "relative";
    }

    const btn = document.createElement("div");
    btn.className = "hdm-outside-btn hdm-pos-top";
    btn.setAttribute("title", "Tải video này với HDM (Click để tải)");
    btn.innerHTML = SVG_DOWNLOAD_ICON;

    // Dynamic placement check (above vs below depending on available space)
    function updatePlacement() {
      const rect = container.getBoundingClientRect();
      if (rect.top < 46) {
        btn.classList.remove("hdm-pos-top");
        btn.classList.add("hdm-pos-bottom");
      } else {
        btn.classList.remove("hdm-pos-bottom");
        btn.classList.add("hdm-pos-top");
      }
    }

    updatePlacement();
    window.addEventListener("scroll", updatePlacement, { passive: true });
    window.addEventListener("resize", updatePlacement, { passive: true });

    // Mini context menu for format selection
    const miniMenu = document.createElement("div");
    miniMenu.className = "hdm-mini-menu";
    miniMenu.innerHTML = `
      <div class="hdm-menu-item" data-format="mp4">🎬 Tải video MP4 (Chất lượng cao)</div>
      <div class="hdm-menu-item" data-format="mp3">🎵 Tải MP3 (Chỉ âm thanh)</div>
    `;
    document.body.appendChild(miniMenu);

    btn.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const rect = btn.getBoundingClientRect();
      miniMenu.style.top = `${rect.bottom + 6}px`;
      miniMenu.style.left = `${Math.max(10, rect.right - 220)}px`;
      miniMenu.classList.add("show");
    });

    miniMenu.addEventListener("click", (e) => {
      const item = e.target.closest(".hdm-menu-item");
      if (item) {
        const fmt = item.getAttribute("data-format");
        miniMenu.classList.remove("show");
        triggerDownload(fmt, btn, video);
      }
    });

    document.addEventListener("click", (e) => {
      if (!miniMenu.contains(e.target) && e.target !== btn) {
        miniMenu.classList.remove("show");
      }
    });

    // Primary click triggers download
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      miniMenu.classList.remove("show");
      triggerDownload("mp4", btn, video);
    });

    container.appendChild(btn);
  }

  function injectYouTubeActionBarButton() {
    if (!isYouTube()) return;

    const actionContainer =
      document.querySelector("#actions #actions-inner") ||
      document.querySelector("ytd-watch-metadata #actions") ||
      document.querySelector("ytd-menu-renderer.ytd-watch-metadata") ||
      document.querySelector("#top-row #actions");

    if (!actionContainer) return;
    if (actionContainer.querySelector(".hdm-yt-action-btn")) return;

    const ytBtn = document.createElement("button");
    ytBtn.className = "hdm-yt-action-btn";
    ytBtn.setAttribute("title", "Tải video này với HDM");
    ytBtn.innerHTML = `
      <span class="hdm-yt-icon">${SVG_DOWNLOAD_ICON}</span>
      <span class="hdm-yt-text">Tải HDM</span>
    `;

    ytBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      triggerDownload("mp4", ytBtn, null);
    });

    actionContainer.appendChild(ytBtn);
  }

  function scanVideos() {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      const videos = document.querySelectorAll("video");
      videos.forEach((vid) => {
        if (vid.offsetWidth < 120 && vid.offsetHeight < 80 && !isYouTube()) return;
        const container = findAnchorContainer(vid);
        if (container) {
          createOutsideButton(vid, container);
        }
      });

      if (isYouTube()) {
        injectYouTubeActionBarButton();
      }
    });
  }

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
})();
