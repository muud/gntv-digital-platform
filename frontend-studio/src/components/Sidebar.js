import { store } from "../../../shared/src/state.js";

export function initSidebar(container) {
  // Set navigation role for accessibility
  container.setAttribute('role', 'navigation');
  container.setAttribute('aria-label', 'GNTV DIGITAL, ALL EVERYWHERE Studio Sidebar');
  container.innerHTML = `
    <div class="sidebar-brand">
      <span class="brand-glow"></span>
      <h1 class="brand-text">GN<span class="highlight">TV</span></h1>
      <span class="brand-tag">BROADCAST HUB</span>
    </div>

    <div class="sidebar-section-header">Frontend Portal</div>
    <nav class="sidebar-nav" style="margin: 0 0 16px 0;">
      <button class="nav-item" data-tab="home" id="btn-tab-home">
        <span class="nav-icon">🏠</span>
        <span class="nav-label">Home / Player</span>
      </button>
      <button class="nav-item" data-tab="epg" id="btn-tab-epg">
        <span class="nav-icon">📅</span>
        <span class="nav-label">EPG Guide</span>
      </button>
      <button class="nav-item" data-tab="vod" id="btn-tab-vod">
        <span class="nav-icon">📼</span>
        <span class="nav-label">VOD Library</span>
      </button>
    </nav>

    <div class="sidebar-section-header">Backend Panel</div>
    <nav class="sidebar-nav" style="margin: 0;">
      <button class="nav-item" data-tab="control" id="btn-tab-control">
        <span class="nav-icon">🎙️</span>
        <span class="nav-label">Broadcaster Panel</span>
      </button>
      <button class="nav-item" data-tab="dashboard" id="btn-tab-dashboard">
        <span class="nav-icon">📊</span>
        <span class="nav-label">Live Console</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <div class="system-status">
        <span class="status-pulse-green"></span>
        <span class="status-text">GNTV DIGITAL, ALL EVERYWHERE Server Node Online</span>
      </div>
      <div class="system-time" id="system-clock">00:00:00 UTC</div>
    </div>
  `;

  // Bind click handlers to buttons
  const navItems = container.querySelectorAll(".nav-item");
  navItems.forEach(item => {
    // Click handling
    item.addEventListener("click", () => {
      const tab = item.getAttribute("data-tab");
      store.setState("activeTab", tab);
    });
    // Keyboard accessibility (Enter/Space)
    item.addEventListener("keydown", (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const tab = item.getAttribute("data-tab");
        store.setState("activeTab", tab);
      }
    });
    // Initial ARIA state
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');
    item.setAttribute('aria-current', 'false');
  });

  // Clock Update
  const clockElement = container.querySelector("#system-clock");
  const updateClock = () => {
    const now = new Date();
    clockElement.textContent = now.toLocaleTimeString() + " LCT";
  };
  setInterval(updateClock, 1000);
  updateClock();

  // Subscribe to state activeTab to update active classes
  store.subscribe("activeTab", (activeTab) => {
    navItems.forEach(item => {
      const isActive = item.getAttribute("data-tab") === activeTab;
      item.classList.toggle("active", isActive);
      // Update ARIA attribute for screen readers
      item.setAttribute('aria-current', isActive ? 'page' : 'false');
    });
  });
}
