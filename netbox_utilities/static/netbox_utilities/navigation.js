(() => {
  'use strict';

  function applyNavigationPreferences() {
    const dataElement = document.getElementById('netbox-utilities-navigation-data');
    const sidebar = document.querySelector('#sidebar-menu > ul.navbar-nav');
    if (!dataElement || !sidebar) return;

    let preferences;
    try {
      preferences = JSON.parse(dataElement.textContent);
    } catch (_error) {
      return;
    }

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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyNavigationPreferences, {once: true});
  } else {
    applyNavigationPreferences();
  }
})();
