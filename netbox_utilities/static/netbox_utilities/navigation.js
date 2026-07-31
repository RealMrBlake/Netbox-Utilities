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
    const requested = Number(value);
    const width = Number.isFinite(requested) ? Math.round(requested) : 288;
    return Math.min(maximum, Math.max(minimum, width));
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
        button.title =
          button.getAttribute('aria-label') || button.querySelector('.nav-link-title')?.textContent.trim() || '';
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

  function closeDropdown(item) {
    if (!item) return false;
    const button = item.querySelector(':scope > button.nav-link');
    const menu = item.querySelector(':scope > .dropdown-menu');
    if (!button || !menu?.classList.contains('show')) return false;

    // Let NetBox/Bootstrap tear down its Popper instance when available.
    button.click();
    if (!menu.classList.contains('show')) {
      menu.style.removeProperty('--netbox-utilities-dropdown-top');
      return true;
    }

    // Fallback for pages on which Bootstrap's data API is unavailable.
    button.classList.remove('show');
    button.setAttribute('aria-expanded', 'false');
    menu.classList.remove('show');
    menu.style.removeProperty('--netbox-utilities-dropdown-top');
    return true;
  }

  function closeDropdowns(sidebar, exceptItem = null) {
    sidebar.querySelectorAll(':scope > li.nav-item.dropdown').forEach((item) => {
      if (item !== exceptItem) closeDropdown(item);
    });
  }

  function configureCollapsedDropdowns(sidebar) {
    sidebar.addEventListener('show.bs.dropdown', (event) => {
      if (!preferences.collapsed) return;
      const item = event.target.closest('.nav-item.dropdown');
      if (!item) return;

      closeDropdowns(sidebar, item);

      const button = item.querySelector(':scope > button.nav-link');
      const menu = item.querySelector(':scope > .dropdown-menu');
      if (!button || !menu) return;
      const top = Math.max(8, button.getBoundingClientRect().top);
      menu.style.setProperty('--netbox-utilities-dropdown-top', `${top}px`);
    });

    sidebar.addEventListener('click', (event) => {
      if (!preferences.collapsed || !(event.target instanceof Element)) return;
      const selectedOption = event.target.closest('.dropdown-menu a[href], .dropdown-menu button');
      if (selectedOption) closeDropdown(selectedOption.closest('.nav-item.dropdown'));
    });

    document.addEventListener(
      'click',
      (event) => {
        if (!preferences.collapsed || !(event.target instanceof Element)) return;
        sidebar.querySelectorAll(':scope > li.nav-item.dropdown').forEach((item) => {
          if (!item.contains(event.target)) closeDropdown(item);
        });
      },
      true
    );

    document.addEventListener('keydown', (event) => {
      if (!preferences.collapsed || event.key !== 'Escape') return;
      const openItem = sidebar.querySelector(':scope > li.nav-item.dropdown > .dropdown-menu.show')?.closest('.nav-item');
      if (openItem && closeDropdown(openItem)) {
        openItem.querySelector(':scope > button.nav-link')?.focus();
        event.preventDefault();
      }
    });
  }

  async function saveLayout(action, width) {
    const body = new URLSearchParams({action});
    if (width !== undefined) body.set('width', String(width));
    const response = await fetch(preferences.layout_update_url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'X-CSRFToken': preferences.csrf_token,
      },
      body,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function addResizeHandle(sidebarElement, sidebar) {
    if (!preferences.layout_update_url || !preferences.csrf_token) return;

    const handle = document.createElement('div');
    handle.className = 'netbox-utilities-sidebar-resizer';
    handle.tabIndex = 0;
    handle.setAttribute('role', 'separator');
    handle.setAttribute('aria-orientation', 'vertical');
    handle.setAttribute('aria-label', 'Breite der Navigation ändern');

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'netbox-utilities-sidebar-toggle';
    const toggleIcon = document.createElement('i');
    toggleIcon.className = 'mdi';
    toggleIcon.setAttribute('aria-hidden', 'true');
    toggle.appendChild(toggleIcon);
    handle.appendChild(toggle);
    sidebarElement.appendChild(handle);

    let resizing = false;
    let previousLayout = null;

    function updateHandle() {
      const minimum = Number(preferences.width_min) || 216;
      const maximum = Number(preferences.width_max) || 408;
      handle.setAttribute('aria-valuemin', String(minimum));
      handle.setAttribute('aria-valuemax', String(maximum));
      handle.setAttribute('aria-valuenow', String(preferences.collapsed ? minimum : preferences.width));
      const label = preferences.collapsed ? 'Navigation ausklappen' : 'Navigation auf Icons einklappen';
      toggle.title = label;
      toggle.setAttribute('aria-label', label);
      toggleIcon.className = preferences.collapsed ? 'mdi mdi-chevron-right' : 'mdi mdi-chevron-left';
      updateMenuTitles(sidebar);
    }

    function applyWidth(clientX) {
      preferences.collapsed = false;
      preferences.width = normalizeWidth(clientX);
      applyRootLayout();
      updateHandle();
    }

    async function persist(action, width, fallback) {
      try {
        const saved = await saveLayout(action, width);
        preferences.collapsed = Boolean(saved.collapsed);
        preferences.width = normalizeWidth(saved.width);
        handle.classList.remove('netbox-utilities-sidebar-save-error');
        handle.removeAttribute('data-save-error');
      } catch (error) {
        preferences.collapsed = fallback.collapsed;
        preferences.width = fallback.width;
        handle.classList.add('netbox-utilities-sidebar-save-error');
        handle.dataset.saveError = 'Die Navigationseinstellung konnte nicht gespeichert werden.';
        console.error('Could not save NetBox navigation layout', error);
      }
      applyRootLayout();
      updateHandle();
    }

    toggle.addEventListener('click', async () => {
      if (toggle.disabled) return;
      const previous = {collapsed: preferences.collapsed, width: preferences.width};
      preferences.collapsed = !preferences.collapsed;
      applyRootLayout();
      updateHandle();
      toggle.disabled = true;
      await persist('toggle', undefined, previous);
      toggle.disabled = false;
    });

    handle.addEventListener('pointerdown', (event) => {
      if (event.target.closest('button')) return;
      event.preventDefault();
      resizing = true;
      previousLayout = {collapsed: preferences.collapsed, width: preferences.width};
      handle.setPointerCapture(event.pointerId);
      root.classList.add('netbox-utilities-navigation-resizing');
      applyWidth(event.clientX);
    });

    handle.addEventListener('pointermove', (event) => {
      if (resizing) applyWidth(event.clientX);
    });

    async function finishResize(event) {
      if (!resizing) return;
      resizing = false;
      if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
      root.classList.remove('netbox-utilities-navigation-resizing');
      const fallback = previousLayout;
      previousLayout = null;
      await persist('resize', preferences.width, fallback);
    }

    handle.addEventListener('pointerup', finishResize);
    handle.addEventListener('pointercancel', finishResize);

    handle.addEventListener('keydown', async (event) => {
      const minimum = Number(preferences.width_min) || 216;
      const maximum = Number(preferences.width_max) || 408;
      const directions = {ArrowLeft: -16, ArrowRight: 16};
      let width;
      if (event.key in directions) width = preferences.width + directions[event.key];
      if (event.key === 'Home') width = minimum;
      if (event.key === 'End') width = maximum;
      if (width === undefined) return;
      event.preventDefault();
      const previous = {collapsed: preferences.collapsed, width: preferences.width};
      applyWidth(width);
      await persist('resize', preferences.width, previous);
    });

    updateHandle();
  }

  function initializeNavigation() {
    const sidebarMenu = document.getElementById('sidebar-menu');
    const sidebar = document.querySelector('#sidebar-menu > ul.navbar-nav');
    const sidebarElement = document.querySelector('.page > aside.navbar-vertical.navbar-expand-lg');
    if (!sidebarMenu || !sidebar || !sidebarElement) return;

    applyMenuPreferences(sidebar);
    updateMenuTitles(sidebar);
    configureCollapsedDropdowns(sidebar);
    addResizeHandle(sidebarElement, sidebar);
  }

  applyRootLayout();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeNavigation, {once: true});
  } else {
    initializeNavigation();
  }
})();
