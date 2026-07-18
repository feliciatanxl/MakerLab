(function () {
  "use strict";

  const data = window.MAKER_LAB_DATA;

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
    const action = project.detailUrl
      ? `<a class="button button-secondary project-card-action" href="${project.detailUrl}">View details <span aria-hidden="true">→</span></a>`
      : `<button class="button project-card-action" type="button" disabled aria-label="Details for ${project.name} are planned">Details coming later</button>`;

    return `
      <article class="project-card">
        <div class="project-card-top">
          <span class="project-number">PROJECT / ${String(project.order).padStart(3, "0")}</span>
          <span class="status-badge status-${project.status.toLowerCase()}">${project.status}</span>
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
    const tags = project.tags.concat(["HTTP APIs"]).map((tag) => `<span>${tag}</span>`).join("");

    root.innerHTML = `
      <div class="featured-visual" aria-hidden="true">
        <div class="signal-ring ring-one"></div><div class="signal-ring ring-two"></div>
        <div class="echo-core"><span>ES</span><small>SENSOR NODE</small></div>
        <span class="sensor-label label-sound">SOUND</span><span class="sensor-label label-motion">PIR</span>
        <span class="sensor-label label-distance">DISTANCE</span><span class="sensor-label label-load">LOAD</span>
      </div>
      <div class="featured-content">
        <div class="project-topline"><span class="status-badge status-built">${project.status}</span><span class="project-code">FEATURED / ${String(project.order).padStart(3, "0")}</span></div>
        <h3 id="featured-project-title">${project.name}</h3>
        <p class="featured-lead">${project.description}</p>
        <p>${project.featuredDescription}</p>
        <div class="tag-list" aria-label="${project.name} technologies">${tags}</div>
        <div class="project-actions">
          <a class="button button-primary" href="${project.detailUrl}">View Project Details <span aria-hidden="true">→</span></a>
          <a class="text-link" href="${project.sourceUrl}" target="_blank" rel="noreferrer">Browse Source <span aria-hidden="true">↗</span></a>
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

  function listMarkup(items) {
    return items.map((item) => `<li>${item}</li>`).join("");
  }

  function initProjectDetail() {
    const root = document.querySelector("[data-project-detail]");
    if (!data || !root) return;

    const project = data.projects.find((item) => item.id === root.dataset.projectDetail);
    if (!project || !project.detail) return;
    const detail = project.detail;

    document.title = `${project.name} | Maker-Lab`;
    document.querySelectorAll("[data-project-name]").forEach((element) => { element.textContent = project.name; });
    document.querySelector("[data-project-summary]").textContent = detail.summary;
    document.querySelector("[data-hardware-list]").innerHTML = listMarkup(detail.hardware);
    document.querySelector("[data-software-list]").innerHTML = listMarkup(detail.software);
    document.querySelector("[data-communication]").textContent = detail.communication;
    document.querySelector("[data-system-flow]").innerHTML = detail.flow.map((node, index) => `
      ${index ? '<span class="flow-arrow" aria-hidden="true">→</span>' : ""}
      <div class="flow-node"><strong>${node.title}</strong><span>${node.label}</span></div>`).join("");
    document.querySelector("[data-capabilities-list]").innerHTML = listMarkup(detail.capabilities);
    document.querySelector("[data-source-files]").innerHTML = detail.files.map((file) => `
      <li>
        <a href="${file.url}" target="_blank" rel="noreferrer">
          <span><strong>${file.name}</strong><small>${file.role}</small></span>
          <span aria-hidden="true">↗</span>
        </a>
      </li>`).join("");
  }

  setCurrentYear();
  initNavigation();
  initActiveNavigation();
  initFeaturedProject();
  initProjectBrowser();
  initBuildLog();
  initProjectDetail();
}());
