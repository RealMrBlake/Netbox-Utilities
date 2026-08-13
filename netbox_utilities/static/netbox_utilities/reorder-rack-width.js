(() => {
  'use strict';

  const source = document.getElementById('netbox-utilities-reorder-rack-width-data');
  if (!source) return;

  let data;
  try {
    data = JSON.parse(source.textContent);
  } catch (error) {
    console.error('NetBox Utilities could not read the Reorder Rack width data.', error);
    return;
  }
  if (data.status && data.status !== 'ready') {
    console.warn('NetBox Utilities is leaving Reorder Rack in its native layout.', data.status);
    return;
  }

  const columns = Number.parseInt(data.columns, 10) || 12;
  const gridElements = {
    front: document.getElementById('grid-front'),
    rear: document.getElementById('grid-rear'),
    other: document.getElementById('grid-other'),
  };
  if (!gridElements.front || !gridElements.rear || !gridElements.other) return;

  const setAttribute = (element, name, value) => element.setAttribute(name, String(value));
  const partialDeviceIds = new Set(data.devices.map(device => String(device.id)));

  const originalFetch = window.fetch.bind(window);
  window.fetch = (resource, options = {}) => {
    const resourceUrl = typeof resource === 'string' || resource instanceof URL
      ? resource
      : resource?.url;
    let url;
    try {
      url = new URL(resourceUrl, document.baseURI);
    } catch (_) {
      return originalFetch(resource, options);
    }
    const method = String(options.method || resource?.method || 'GET').toUpperCase();
    if (method !== 'PUT' || !/\/api\/plugins\/reorder\/save\/\d+\/?$/.test(url.pathname)) {
      return originalFetch(resource, options);
    }

    const headers = new Headers(options.headers || resource?.headers);
    headers.set('X-NetBox-Utilities-Rack-Grid-Columns', String(columns));
    return originalFetch(resource, {...options, headers});
  };

  Object.values(gridElements).forEach(grid => {
    setAttribute(grid, 'gs-column', columns);
    grid.querySelectorAll('.grid-stack-item').forEach(item => {
      if (partialDeviceIds.has(item.getAttribute('gs-id'))) {
        item.remove();
        return;
      }
      setAttribute(item, 'gs-w', columns);
      setAttribute(item, 'gs-x', 0);
      item.dataset.rackWidth = '1';
      item.dataset.horizontalPosition = '1';
    });
  });

  const addWidget = (device, gridFace, itemFace, rearSide = false) => {
    const item = document.createElement('div');
    item.className = 'grid-stack-item netbox-utilities-reorder-rack-device';
    setAttribute(item, 'gs-w', device.grid_width);
    setAttribute(item, 'gs-h', device.grid_height);
    setAttribute(item, 'gs-x', device.grid_x);
    setAttribute(item, 'gs-y', device.grid_y);
    setAttribute(item, 'gs-id', device.id);
    setAttribute(item, 'gs-locked', device.locked ? 'true' : 'false');
    setAttribute(item, 'gs-no-move', device.locked ? 'true' : 'false');
    item.dataset.itemColor = device.color;
    item.dataset.itemTextColor = device.text_color;
    item.dataset.fullDepth = device.full_depth ? 'True' : 'False';
    item.dataset.itemFace = itemFace;
    item.dataset.rackWidth = String(device.width);
    item.dataset.horizontalPosition = String(device.horizontal_position);

    const content = document.createElement('div');
    content.className = 'grid-stack-item-content';
    if (rearSide) content.classList.add('device_rear');
    const image = rearSide ? device.rear_image : device.front_image;
    if (image && data.images) {
      content.style.backgroundImage = `url("${String(image).replaceAll('"', '\\"')}")`;
      content.style.backgroundSize = `${data.unit_width}px`;
      content.style.color = `#${device.text_color}`;
      if (data.labels) content.textContent = device.label;
    } else {
      if (!rearSide) content.style.backgroundColor = `#${device.color}`;
      content.style.color = rearSide ? '#000000' : `#${device.text_color}`;
      content.textContent = device.label;
    }
    item.appendChild(content);
    gridElements[gridFace].appendChild(item);
  };

  data.devices.forEach(device => {
    const face = device.face === 'rear' ? 'rear' : 'front';
    addWidget(device, face, face);
    if (device.full_depth) {
      addWidget(device, face === 'front' ? 'rear' : 'front', 'back', true);
    }
  });

  const snapElement = element => {
    if (!element?.gridstackNode) return;
    const width = Number.parseInt(element.dataset.rackWidth || '1', 10);
    if (![1, 2, 3, 4].includes(width)) return;
    const gridWidth = columns / width;
    const node = element.gridstackNode;
    const gridX = Math.max(0, Math.min(columns - gridWidth, Math.round(node.x / gridWidth) * gridWidth));
    element.dataset.horizontalPosition = String(gridX / gridWidth + 1);
    if (node.x !== gridX || node.w !== gridWidth) {
      node.grid.update(element, {x: gridX, w: gridWidth});
    }
  };

  const snapGrid = grid => grid.getGridItems().forEach(snapElement);
  const attachSnapping = () => {
    Object.values(gridElements).forEach(element => {
      const grid = element.gridstack;
      if (!grid) return;
      grid.on('dragstop', (_event, item) => snapElement(item));
      grid.on('dropped', (_event, _previous, current) => snapElement(current?.el));
    });
  };

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    if (!target?.closest('#saveButton')) return;
    Object.values(gridElements).forEach(element => {
      if (element.gridstack) snapGrid(element.gridstack);
    });
  }, true);

  document.addEventListener('DOMContentLoaded', attachSnapping, {once: true});
})();
