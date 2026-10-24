/**
 * HDM Browser Extension - Video Download Sniffer
 * Ultra-compact 28px icon button with top-right 'x' dismiss badge,
 * positioned strictly outside the video viewing box.
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

  const SVG_ALERT_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="8" x2="12" y2="12"></line>
      <line x1="12" y1="16" x2="12.01" y2="16"></line>
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
      const ytPlayer =
        document.querySelector("#player") ||
        document.querySelector("ytd-watch-flexy #player") ||
        document.querySelector(".ytd-watch-flexy #player");
      if (ytPlayer) return ytPlayer;
    }

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

  function triggerDownload(formatType, qualityType, sourceBtn, video) {
    const originalHtml = sourceBtn ? sourceBtn.innerHTML : "";
    if (sourceBtn) {
      sourceBtn.classList.add("loading");
      sourceBtn.setAttribute("title", "Đang kết nối HDM...");
    }

    const pageUrl = window.location.href;
    let targetUrl = pageUrl;

    if (!isYouTube() && video) {
      const rawSrc = video.currentSrc || video.src;
      if (rawSrc && !rawSrc.startsWith("blob:")) {
        targetUrl = rawSrc;
      }
    }

    chrome.runtime.sendMessage(
      {
        action: "download_media",
        data: {
          url: targetUrl,
          pageUrl: pageUrl,
          title: getVideoTitle(),
          format: formatType || "mp4",
          quality: qualityType || "",
          isStreaming: isYouTube(),
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
          const qText = qualityType ? (formatType === "mp3" ? `${qualityType} kbps` : `${qualityType}p`) : "";
          const desc = formatType === "mp3" ? `MP3 ${qText}`.trim() : (qText ? `MP4 ${qText}` : "MP4");
          showToast(`✓ Đã gửi lệnh tải (${desc}) tới HDM! Vui lòng xác nhận trên HDM.`, false);
        }
      }
    );
  }

  function createOutsideButton(video, container) {
    if (container.__hdm_dismissed__ || container.querySelector(".hdm-btn-wrap")) return;

    // Ensure container has relative/absolute positioning
    const compStyle = window.getComputedStyle(container);
    if (compStyle.position === "static") {
      container.style.position = "relative";
    }

    // Outer wrapper
    const wrap = document.createElement("div");
    wrap.className = "hdm-btn-wrap hdm-pos-top";

    // Main 28px circular button
    const btn = document.createElement("div");
    btn.className = "hdm-outside-btn";
    btn.setAttribute("title", "Tải video với HDM (Bấm để chọn định dạng & chất lượng)");
    btn.innerHTML = SVG_DOWNLOAD_ICON;

    // Mini 'x' dismiss badge at top-right
    const closeBtn = document.createElement("div");
    closeBtn.className = "hdm-close-x";
    closeBtn.setAttribute("title", "Ẩn nút tải này");
    closeBtn.innerHTML = "&times;";

    // Dynamic quality & format selection dropdown menu
    const qualityMenu = document.createElement("div");
    qualityMenu.className = "hdm-quality-menu";
    qualityMenu.innerHTML = `
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
    document.body.appendChild(qualityMenu);

    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      container.__hdm_dismissed__ = true;
      qualityMenu.remove();
      wrap.style.opacity = "0";
      wrap.style.transform = "scale(0.8)";
      setTimeout(() => wrap.remove(), 200);
    });

    wrap.appendChild(btn);
    wrap.appendChild(closeBtn);

    // Dynamic placement check (above vs below depending on available space)
    function updatePlacement() {
      const rect = container.getBoundingClientRect();
      if (rect.top < 40) {
        wrap.classList.remove("hdm-pos-top");
        wrap.classList.add("hdm-pos-bottom");
      } else {
        wrap.classList.remove("hdm-pos-bottom");
        wrap.classList.add("hdm-pos-top");
      }
    }

    updatePlacement();
    window.addEventListener("scroll", updatePlacement, { passive: true });
    window.addEventListener("resize", updatePlacement, { passive: true });

    function toggleMenu(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      if (qualityMenu.classList.contains("show")) {
        qualityMenu.classList.remove("show");
        return;
      }

      // Close any other open menus
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

    // Left click and right click open the format/quality selector
    btn.addEventListener("click", toggleMenu);
    btn.addEventListener("contextmenu", toggleMenu);

    qualityMenu.addEventListener("click", (e) => {
      e.stopPropagation();
      const item = e.target.closest(".hdm-menu-item");
      if (item) {
        const fmt = item.getAttribute("data-format");
        const q = item.getAttribute("data-quality") || "";
        qualityMenu.classList.remove("show");
        triggerDownload(fmt, q, btn, video);
      }
    });

    document.addEventListener("click", (e) => {
      if (!qualityMenu.contains(e.target) && !btn.contains(e.target)) {
        qualityMenu.classList.remove("show");
      }
    });

    window.addEventListener(
      "scroll",
      () => {
        if (qualityMenu.classList.contains("show")) {
          qualityMenu.classList.remove("show");
        }
      },
      { passive: true }
    );

    container.appendChild(wrap);
  }

  function scanVideos() {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      const videos = document.querySelectorAll("video");
      videos.forEach((vid) => {
        if (vid.offsetWidth < 120 && vid.offsetHeight < 80 && !isYouTube()) return;
        const container = findAnchorContainer(vid);
        if (container && !container.__hdm_dismissed__) {
          createOutsideButton(vid, container);
        }
      });
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
