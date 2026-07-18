(function () {
  "use strict";

  const data = window.MAKER_LAB_DATA;
  const isProjectPage = Boolean(document.querySelector("[data-project-detail]"));

  function localPath(path) {
    return isProjectPage ? `../${path}` : path;
  }

  function setText(selector, value) {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
  }

  function setCurrentYear() {
    document.querySelectorAll("[data-current-year]").forEach((element) => {
      element.textContent = new Date().getFullYear();
    });
  }

  function initNavigation() {
    const toggle = document.querySelector(".nav-toggle");
    const menu = document.querySelector(".nav-menu");
    if (!toggle || !menu) return;

    const setMenuState = (open, returnFocus) => {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
      menu.classList.toggle("is-open", open);
      document.body.classList.toggle("menu-open", open);
      if (!open && returnFocus) toggle.focus();
    };

    toggle.addEventListener("click", () => {
      setMenuState(toggle.getAttribute("aria-expanded") !== "true", false);
    });

    menu.addEventListener("click", (event) => {
      if (event.target.closest("a")) setMenuState(false, false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setMenuState(false, true);
      }
    });

    document.addEventListener("click", (event) => {
      if (toggle.getAttribute("aria-expanded") === "true" && !menu.contains(event.target) && !toggle.contains(event.target)) {
        setMenuState(false, false);
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 860) setMenuState(false, false);
    });
  }

  function initActiveNavigation() {
    const links = Array.from(document.querySelectorAll(".nav-link[href^='#']"));
    const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
    if (!links.length || !sections.length || !("IntersectionObserver" in window)) return;

    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;

      links.forEach((link) => {
        const active = link.getAttribute("href") === `#${visible.target.id}`;
        link.classList.toggle("is-active", active);
        if (active) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    }, { rootMargin: "-25% 0px -62%", threshold: [0, 0.2, 0.5] });

    sections.forEach((section) => observer.observe(section));
  }

  function projectCard(project) {
    const tags = project.tags.map((tag) => `<span>${tag}</span>`).join("");
    const statusClass = project.status.startsWith("Built") ? "built" : "planned";
    const action = project.detailUrl
      ? `<a class="button button-secondary project-card-action" href="${project.detailUrl}">View details <span aria-hidden="true">→</span></a>`
      : `<button class="button project-card-action" type="button" disabled aria-label="Details for ${project.name} are planned">Details coming later</button>`;

    return `
      <article class="project-card">
        <div class="project-card-top">
          <span class="project-number">PROJECT / ${String(project.order).padStart(3, "0")}</span>
          <span class="status-badge status-${statusClass}">${project.status}</span>
        </div>
        <h3>${project.name}</h3>
        <p>${project.description}</p>
        <div class="project-platform">Platform: <strong>${project.platform}</strong></div>
        <div class="tag-list" aria-label="${project.name} technologies">${tags}</div>
        ${action}
      </article>`;
  }

  function initFeaturedProject() {
    const root = document.querySelector("[data-featured-project]");
    if (!data || !root) return;

    const project = data.projects.find((item) => item.id === root.dataset.featuredProject);
    if (!project) return;
    const tags = project.tags.map((tag) => `<span>${tag}</span>`).join("");

    root.innerHTML = `
      <figure class="featured-visual featured-photo">
        <img src="${localPath(project.image)}" alt="${project.imageAlt}" width="720" height="1280" loading="lazy" decoding="async">
        <figcaption><span>DEVELOPMENT PROTOTYPE</span><strong>${project.platform}</strong></figcaption>
      </figure>
      <div class="featured-content">
        <div class="project-topline"><span class="status-badge status-built">${project.status}</span><span class="project-code">FEATURED / ${String(project.order).padStart(3, "0")}</span></div>
        <h3 id="featured-project-title">${project.name}</h3>
        <p class="featured-lead">${project.description}</p>
        <p>${project.featuredDescription}</p>
        <div class="tag-list" aria-label="${project.name} technologies">${tags}</div>
        <div class="project-actions">
          <a class="button button-primary" href="${project.detailUrl}">View Project Details <span aria-hidden="true">→</span></a>
          <div class="project-secondary-links">
            <a class="text-link external-project-link" href="${project.repositoryUrl}" target="_blank" rel="noopener noreferrer">Full repository <span aria-hidden="true">↗</span></a>
            <a class="text-link external-project-link portfolio-project-link" href="${project.portfolioUrl}" target="_blank" rel="noopener noreferrer">Portfolio Case Study <span aria-hidden="true">↗</span></a>
          </div>
        </div>
      </div>`;
  }

  function initProjectBrowser() {
    const filters = document.querySelector("[data-project-filters]");
    const grid = document.querySelector("[data-project-grid]");
    const status = document.querySelector("[data-filter-status]");
    if (!data || !filters || !grid || !status) return;

    const render = (filter) => {
      const matches = filter === "All" ? data.projects : data.projects.filter((project) => project.filters.includes(filter));
      grid.innerHTML = matches.map(projectCard).join("");
      status.textContent = `Showing ${matches.length} ${matches.length === 1 ? "project" : "projects"} · ${filter}`;
      filters.querySelectorAll("button").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.filter === filter));
      });
    };

    filters.innerHTML = data.filters.map((filter) => (
      `<button class="filter-button" type="button" data-filter="${filter}" aria-pressed="${filter === "All"}">${filter}</button>`
    )).join("");

    filters.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-filter]");
      if (button) render(button.dataset.filter);
    });

    render("All");
  }

  function initBuildLog() {
    const timeline = document.querySelector("[data-build-log]");
    if (!data || !timeline) return;

    timeline.innerHTML = data.buildLog.map((entry) => {
      const statusClass = entry.status.toLowerCase();
      return `
        <li class="timeline-item is-${statusClass}">
          <span class="timeline-marker" aria-hidden="true"></span>
          <div class="timeline-content">
            <div class="timeline-meta"><span>${entry.phase}</span><span class="${statusClass}">${entry.status}</span></div>
            <h3>${entry.title}</h3>
            <p>${entry.description}</p>
          </div>
        </li>`;
    }).join("");
  }

  function renderHardware(items) {
    const root = document.querySelector("[data-hardware-grid]");
    if (!root) return;
    root.innerHTML = items.map((item) => `
      <article class="hardware-card">
        <div class="hardware-image"${item.crop ? ` data-image-crop="${item.crop}"` : ""}><img src="${localPath(item.image)}" alt="${item.alt}" width="${item.width || 720}" height="${item.height || 1280}" loading="lazy" decoding="async"></div>
        <div class="hardware-content">
          <span>${item.interface}</span>
          <h3>${item.name}</h3>
          <p>${item.purpose}</p>
        </div>
      </article>`).join("");
  }

  function renderPrototypeEvidence(selector, items) {
    const root = document.querySelector(selector);
    if (!root) return;
    root.innerHTML = items.map((item) => `
      <figure class="prototype-evidence-card">
        <div class="prototype-evidence-media"><img src="${localPath(item.image)}" alt="${item.alt}" width="${item.width || 720}" height="${item.height || 1280}" loading="lazy" decoding="async"></div>
        <figcaption><span>${item.category}</span><strong>${item.caption}</strong></figcaption>
      </figure>`).join("");
  }

  function renderArchitecture(items) {
    const root = document.querySelector("[data-architecture-flow]");
    if (!root) return;
    root.innerHTML = items.map((item, index) => `
      <li class="architecture-node">
        <span class="architecture-index" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>
        <strong>${item.title}</strong>
        <small>${item.label}</small>
        ${index < items.length - 1 ? '<span class="architecture-arrow" aria-hidden="true"></span>' : ''}
      </li>`).join("");
  }

  function renderDecisionWorkflow(items) {
    const root = document.querySelector("[data-decision-workflow]");
    if (!root) return;
    root.innerHTML = items.map((item, index) => `
      <li><span>${String(index + 1).padStart(2, "0")}</span><div><h3>${item.title}</h3><p>${item.text}</p></div></li>`).join("");
  }

  function renderEcosystem(items) {
    const root = document.querySelector("[data-ecosystem-flow]");
    if (!root) return;
    root.innerHTML = items.map((item) => `<li><strong>${item.title}</strong><span>${item.label}</span></li>`).join("");
  }

  function renderVideos(videos) {
    const root = document.querySelector("[data-video-grid]");
    if (!root) return;
    root.innerHTML = videos.map((video) => `
      <article class="video-card">
        <div class="video-frame">
          <video controls preload="metadata" playsinline aria-label="${video.title}">
            <source src="${localPath(video.src)}" type="video/mp4">
            Your browser cannot play this video. <a href="${localPath(video.src)}">Download the ${video.title}</a>.
          </video>
        </div>
        <div class="video-content">
          <span class="language-label">${video.language}</span>
          <h3>${video.title}</h3>
          <p>${video.description}</p>
        </div>
      </article>`).join("");
  }

  function renderGallery(items) {
    const root = document.querySelector("[data-hardware-gallery]");
    if (!root) return;
    root.innerHTML = items.map((item, index) => `
      <figure class="gallery-item">
        <button type="button" data-gallery-index="${index}" aria-label="Enlarge image: ${item.caption}">
          <img src="${localPath(item.image)}" alt="${item.alt}" width="${item.width || 720}" height="${item.height || 1280}" loading="lazy" decoding="async">
          <span aria-hidden="true">↗</span>
        </button>
        <figcaption>${item.caption}</figcaption>
      </figure>`).join("");
  }

  function renderResults(items) {
    const root = document.querySelector("[data-results-grid]");
    if (!root) return;
    root.innerHTML = items.map((item, index) => `
      <article><span>${String(index + 1).padStart(2, "0")}</span><p>${item}</p></article>`).join("");
  }

  function renderEmbeddedSources(items) {
    const root = document.querySelector("[data-embedded-source-list]");
    if (!root) return;
    root.innerHTML = items.map((item) => `
      <li><a href="${localPath(item.path)}"><span><strong>${item.name}</strong><small>${item.role}</small></span><span aria-hidden="true">→</span></a></li>`).join("");
  }

  function renderTextList(selector, items) {
    const root = document.querySelector(selector);
    if (root) root.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
  }

  function initJsonCopy() {
    const button = document.querySelector("[data-copy-json]");
    const code = document.querySelector("[data-serial-json]");
    const feedback = document.querySelector("[data-copy-feedback]");
    if (!button || !code || !feedback) return;
    let feedbackTimer;

    const fallbackCopy = (text) => {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.className = "copy-helper";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("Copy command was unavailable");
    };

    button.addEventListener("click", async () => {
      clearTimeout(feedbackTimer);
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(code.textContent);
        else fallbackCopy(code.textContent);
        feedback.textContent = "JSON copied to clipboard.";
        button.textContent = "Copied";
      } catch (error) {
        feedback.textContent = "Copy failed. Select the JSON text and copy it manually.";
        button.textContent = "Copy JSON";
      }
      feedbackTimer = window.setTimeout(() => {
        feedback.textContent = "";
        button.textContent = "Copy JSON";
      }, 2600);
    });
  }

  function initGalleryDialog(gallery) {
    const grid = document.querySelector("[data-hardware-gallery]");
    const dialog = document.querySelector("[data-gallery-dialog]");
    const image = document.querySelector("[data-dialog-image]");
    const caption = document.querySelector("[data-dialog-caption]");
    const closeButton = document.querySelector("[data-dialog-close]");
    if (!grid || !dialog || !image || !caption || !closeButton) return;
    let openingButton = null;

    const openFromButton = (button) => {
      const item = gallery[Number(button.dataset.galleryIndex)];
      if (!item) return;
      openingButton = button;
      image.src = localPath(item.image);
      image.alt = item.alt;
      caption.textContent = item.caption;
      dialog.showModal();
    };

    grid.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-gallery-index]");
      if (button) openFromButton(button);
    });

    grid.addEventListener("keydown", (event) => {
      const button = event.target.closest("button[data-gallery-index]");
      if (!button || !["Enter", " ", "Space", "Spacebar"].includes(event.key)) return;
      event.preventDefault();
      openFromButton(button);
    });

    closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && dialog.open) dialog.close();
    });
    dialog.addEventListener("close", () => {
      if (openingButton) openingButton.focus();
    });
  }

  function initProjectDetail() {
    const root = document.querySelector("[data-project-detail]");
    if (!data || !root) return;

    const project = data.projects.find((item) => item.id === root.dataset.projectDetail);
    if (!project || !project.detail) return;
    const detail = project.detail;

    document.title = `${project.name} Case Study | Maker-Lab`;
    document.querySelectorAll("[data-project-name]").forEach((element) => { element.textContent = project.name; });
    setText("[data-platform-label]", project.platformLabel);
    setText("[data-project-summary]", detail.summary);
    setText("[data-prototype-notice]", detail.prototypeNotice);
    setText("[data-project-overview]", detail.overview);
    setText("[data-serial-json]", JSON.stringify(detail.serialExample, null, 2));
    setText("[data-recognition]", detail.recognition);
    document.querySelectorAll("[data-portfolio-link]").forEach((link) => {
      link.href = project.portfolioUrl;
    });

    renderHardware(detail.hardware);
    renderPrototypeEvidence("[data-prototype-evidence]", detail.prototypeImages.slice(0, 3));
    renderPrototypeEvidence("[data-workflow-evidence]", detail.prototypeImages.slice(3));
    renderArchitecture(detail.architecture);
    renderDecisionWorkflow(detail.detectionWorkflow);
    renderEcosystem(detail.ecosystem);
    renderVideos(project.videos);
    renderGallery(detail.gallery);
    renderResults(detail.results);
    renderEmbeddedSources(project.firmwareLinks);
    renderTextList("[data-lessons-list]", detail.lessons);
    renderTextList("[data-future-list]", detail.future);
    initJsonCopy();
    initGalleryDialog(detail.gallery);
  }

  setCurrentYear();
  initNavigation();
  initActiveNavigation();
  initFeaturedProject();
  initProjectBrowser();
  initBuildLog();
  initProjectDetail();
}());
