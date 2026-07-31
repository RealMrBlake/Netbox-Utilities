(() => {
  'use strict';

  const dataElement = document.getElementById('netbox-utilities-navigation-data');
  if (!dataElement) return;

  let preferences;
  try {
    preferences = JSON.parse(dataElement.textContent);
  } catch (_error) {
    return;
  }

  const root = document.documentElement;

  function normalizeWidth(value) {
    const minimum = Number(preferences.width_min) || 216;
    const maximum = Number(preferences.width_max) || 408;
    const step = Number(preferences.width_step) || 24;
    const requested = Number(value) || 288;
    const snapped = minimum + Math.round((requested - minimum) / step) * step;
    return Math.min(maximum, Math.max(minimum, snapped));
  }

  function applyRootLayout() {
    preferences.width = normalizeWidth(preferences.width);
    preferences.collapsed = Boolean(preferences.collapsed);
    root.classList.add('netbox-utilities-navigation-layout');
    root.classList.toggle('netbox-utilities-navigation-collapsed', preferences.collapsed);
    root.style.setProperty('--netbox-utilities-sidebar-width', `${preferences.width}px`);
  }

  function applyMenuPreferences(sidebar) {
    const descriptorByPath = new Map(
      preferences.menus.map((menu) => [new URL(menu.first_url, document.baseURI).pathname, menu])
    );
    const nodeByKey = new Map();

    sidebar.querySelectorAll(':scope > li.nav-item.dropdown').forEach((node) => {
      const firstLink = node.querySelector('.dropdown-menu a[href]');
      if (!firstLink) return;
      const descriptor = descriptorByPath.get(new URL(firstLink.href, document.baseURI).pathname);
      if (descriptor) nodeByKey.set(descriptor.key, node);
    });

    preferences.order.forEach((key) => {
      const node = nodeByKey.get(key);
      if (node) sidebar.appendChild(node);
    });

    const hidden = new Set(preferences.hidden);
    nodeByKey.forEach((node, key) => {
      node.classList.toggle('d-none', hidden.has(key));
    });
  }

  function updateMenuTitles(sidebar) {
    sidebar.querySelectorAll(':scope > li.nav-item.dropdown > button.nav-link').forEach((button) => {
      if (preferences.collapsed) {
        button.dataset.netboxUtilitiesTitle = 'true';
        button.title = button.getAttribute('aria-label') || '';
        const menu = button.closest('.nav-item.dropdown')?.querySelector(':scope > .dropdown-menu.show');
        if (menu) {
          const top = Math.max(8, button.getBoundingClientRect().top);
          menu.style.setProperty('--netbox-utilities-dropdown-top', `${top}px`);
        }
      } else if (button.dataset.netboxUtilitiesTitle) {
        button.removeAttribute('title');
        delete button.dataset.netboxUtilitiesTitle;
      }
    });
  }

  function configureCollapsedDropdowns(sidebar) {
    sidebar.addEventListener('show.bs.dropdown', (event) => {
      if (!preferences.collapsed) return;
      const item = event.target.closest('.nav-item.dropdown');
      if (!item) return;

      sidebar.querySelectorAll(':scope > li.nav-item.dropdown').forEach((otherItem) => {
        if (otherItem === item) return;
        const otherButton = otherItem.querySelector(':scope > button.nav-link');
        const otherMenu = otherItem.querySelector(':scope > .dropdown-menu');
        otherButton?.classList.remove('show');
        otherButton?.setAttribute('aria-expanded', 'false');
        otherMenu?.classList.remove('show');
      });

      const button = item.querySelector(':scope > button.nav-link');
      const menu = item.querySelector(':scope > .dropdown-menu');
      if (!button || !menu) return;
      const top = Math.max(8, button.getBoundingClientRect().top);
      menu.style.setProperty('--netbox-utilities-dropdown-top', `${top}px`);
    });
  }

  function createControl(action, icon, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-sm btn-ghost-secondary netbox-utilities-sidebar-control';
    button.dataset.action = action;
    button.title = label;
    button.setAttribute('aria-label', label);
    const iconElement = document.createElement('i');
    iconElement.className = `mdi ${icon}`;
    iconElement.setAttribute('aria-hidden', 'true');
    button.appendChild(iconElement);
    return button;
  }

  function updateControls(controls, sidebar, pending = false) {
    const minimum = Number(preferences.width_min) || 216;
    const maximum = Number(preferences.width_max) || 408;
    const smaller = controls.querySelector('[data-action="smaller"]');
    const larger = controls.querySelector('[data-action="larger"]');
    const toggle = controls.querySelector('[data-action="toggle"]');
    const toggleIcon = toggle.querySelector('i');

    smaller.disabled = pending || preferences.collapsed || preferences.width <= minimum;
    larger.disabled = pending || preferences.collapsed || preferences.width >= maximum;
    toggle.disabled = pending;
    toggleIcon.className = preferences.collapsed
      ? 'mdi mdi-arrow-expand-right'
      : 'mdi mdi-arrow-collapse-left';
    const toggleLabel = preferences.collapsed ? 'Navigation ausklappen' : 'Navigation auf Icons einklappen';
    toggle.title = toggleLabel;
    toggle.setAttribute('aria-label', toggleLabel);
    updateMenuTitles(sidebar);
  }

  function applyAction(action) {
    const step = Number(preferences.width_step) || 24;
    if (action === 'toggle') preferences.collapsed = !preferences.collapsed;
    if (action === 'smaller') preferences.width = normalizeWidth(preferences.width - step);
    if (action === 'larger') preferences.width = normalizeWidth(preferences.width + step);
    applyRootLayout();
  }

  function addLayoutControls(sidebarMenu, sidebar) {
    if (!preferences.layout_update_url || !preferences.csrf_token) return;

    const controls = document.createElement('div');
    controls.className = 'netbox-utilities-sidebar-controls';
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', 'Navigationsgröße');
    controls.append(
      createControl('smaller', 'mdi-minus', 'Navigation schmaler'),
      createControl('toggle', 'mdi-arrow-collapse-left', 'Navigation auf Icons einklappen'),
      createControl('larger', 'mdi-plus', 'Navigation breiter')
    );

    const releaseInfo = sidebarMenu.querySelector(':scope > .text-muted');
    sidebarMenu.insertBefore(controls, releaseInfo || null);
    updateControls(controls, sidebar);

    controls.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button || button.disabled) return;

      const previous = {collapsed: preferences.collapsed, width: preferences.width};
      applyAction(button.dataset.action);
      updateControls(controls, sidebar, true);

      try {
        const response = await fetch(preferences.layout_update_url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'X-CSRFToken': preferences.csrf_token,
          },
          body: new URLSearchParams({action: button.dataset.action}),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const saved = await response.json();
        preferences.collapsed = Boolean(saved.collapsed);
        preferences.width = normalizeWidth(saved.width);
        controls.classList.remove('text-danger');
        controls.removeAttribute('title');
      } catch (error) {
        preferences.collapsed = previous.collapsed;
        preferences.width = previous.width;
        controls.classList.add('text-danger');
        controls.title = 'Die Navigationseinstellung konnte nicht gespeichert werden.';
        console.error('Could not save NetBox navigation layout', error);
      }

      applyRootLayout();
      updateControls(controls, sidebar);
    });
  }

  function initializeNavigation() {
    const sidebarMenu = document.getElementById('sidebar-menu');
    const sidebar = document.querySelector('#sidebar-menu > ul.navbar-nav');
    if (!sidebarMenu || !sidebar) return;

    applyMenuPreferences(sidebar);
    updateMenuTitles(sidebar);
    configureCollapsedDropdowns(sidebar);
    addLayoutControls(sidebarMenu, sidebar);
  }

  applyRootLayout();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeNavigation, {once: true});
  } else {
    initializeNavigation();
  }
})();
