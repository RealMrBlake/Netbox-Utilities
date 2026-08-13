(() => {
  'use strict';

  const placementSource = document.getElementById('netbox-utilities-topology-rack-width-data');
  if (!placementSource) return;

  let payload;
  try {
    payload = JSON.parse(placementSource.textContent);
  } catch (error) {
    console.error('NetBox Utilities could not read the Topology Views rack widths.', error);
    return;
  }
  if (!Array.isArray(payload) && payload?.status && payload.status !== 'ready') {
    console.warn('NetBox Utilities is leaving Topology Views in its native layout.', payload.status);
    return;
  }
  const placementData = Array.isArray(payload) ? payload : payload?.devices;
  if (!Array.isArray(placementData)) {
    console.error('NetBox Utilities received invalid Topology Views rack width data.');
    return;
  }

  const normalizePath = value => {
    try {
      return new URL(value, document.baseURI).pathname.replace(/\/+$/, '/');
    } catch (_) {
      return '';
    }
  };

  const normalizePlacement = value => {
    const width = Number.parseInt(value?.width, 10);
    const horizontalPosition = Number.parseInt(value?.horizontal_position, 10);
    if (![2, 3, 4].includes(width) || horizontalPosition < 1 || horizontalPosition > width) return null;
    return {
      width,
      horizontalPosition,
      leftPercent: Number.isFinite(Number(value.left_percent))
        ? Number(value.left_percent)
        : (horizontalPosition - 1) / width * 100,
      widthPercent: Number.isFinite(Number(value.width_percent))
        ? Number(value.width_percent)
        : 100 / width,
    };
  };

  const placementsByPath = new Map();
  const placementsByDeviceId = new Map();
  placementData.forEach(item => {
    const placement = normalizePlacement(item);
    if (!placement) return;
    const path = normalizePath(item.url);
    if (path) placementsByPath.set(path, placement);
    placementsByDeviceId.set(String(item.device_id), placement);
  });

  const rackCards = Array.from(document.querySelectorAll('.rack-card[data-rack-id][data-rack-units]'));
  const liveViewCompatible = rackCards.length > 0 && rackCards.every(card => {
    if (!/^\d+$/.test(String(card.dataset.rackId)) || !Number.isFinite(Number(card.dataset.rackUnits))) {
      return false;
    }
    return Array.from(card.querySelectorAll('.rack-device')).every(device => (
      device.hasAttribute('href')
      && ['front', 'rear'].includes(device.dataset.face)
      && Number.isFinite(Number(device.dataset.position))
      && Number.isFinite(Number(device.dataset.deviceHeight))
      && typeof device.dataset.deviceColor === 'string'
    ));
  });
  if (!rackCards.length && !placementData.length) return;
  if (!liveViewCompatible) {
    console.warn('NetBox Utilities left Topology Views unchanged because its rack DOM is not compatible.');
    return;
  }

  const placementForElement = element => {
    const path = normalizePath(element.getAttribute('href'));
    if (placementsByPath.has(path)) return placementsByPath.get(path);
    const deviceId = path.match(/\/devices\/(\d+)\/?$/)?.[1];
    return deviceId ? placementsByDeviceId.get(deviceId) : null;
  };

  document.querySelectorAll('.rack-device').forEach(device => {
    const placement = placementForElement(device);
    if (!placement) return;
    device.classList.add('netbox-utilities-partial-width');
    device.dataset.rackWidth = String(placement.width);
    device.dataset.horizontalPosition = String(placement.horizontalPosition);
    device.style.setProperty('--netbox-utilities-rack-device-left', `${placement.leftPercent}%`);
    device.style.setProperty('--netbox-utilities-rack-device-width', `${placement.widthPercent}%`);
  });

  const rackDataSource = document.getElementById('rack-export-data');
  if (!rackDataSource) return;

  let rackData;
  try {
    rackData = JSON.parse(rackDataSource.textContent);
  } catch (error) {
    console.error('NetBox Utilities could not read the Topology Views rack export data.', error);
    return;
  }

  const rackExportCompatible = Array.isArray(rackData) && rackData.length > 0 && rackData.every(rack => {
    if (!rack || !/^\d+$/.test(String(rack.id)) || !Array.isArray(rack.devices)) return false;
    if (!Number.isFinite(Number(rack.u_height)) || !Number.isFinite(Number(rack.starting_unit))) return false;
    const card = document.querySelector(`.rack-card[data-rack-id="${rack.id}"]`);
    if (!card || !Number.isFinite(Number(card.dataset.rackUnits))) return false;
    return true;
  });
  if (!rackExportCompatible) {
    console.warn('NetBox Utilities left Topology Views exports unchanged because their schema is not compatible.');
    return;
  }

  const xmlEscape = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&apos;',
  })[character]);
  const safeName = value => String(value || 'export')
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-|-$/g, '');
  const numberOr = (value, fallback) => {
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : fallback;
  };

  const activeNetBoxTheme = () => {
    for (const element of [document.body, document.documentElement]) {
      const match = getComputedStyle(element).backgroundColor.match(/[\d.]+/g);
      if (match && match.length >= 3 && (match.length < 4 || Number(match[3]) > 0)) {
        const [red, green, blue] = match.map(Number);
        return (.2126 * red + .7152 * green + .0722 * blue) < 140 ? 'dark' : 'light';
      }
    }
    return document.body.dataset.bsTheme || document.documentElement.dataset.bsTheme || 'light';
  };

  const exportPalette = () => activeNetBoxTheme() === 'dark' ? {
    frame: '#52606d',
    grid: '#667382',
    heading: '#8fc8ff',
    muted: '#a9b7c6',
    deviceFill: '#162e45',
    deviceText: '#ffffff',
    deviceSubtext: '#cad5df',
  } : {
    frame: '#718096',
    grid: '#8b99a8',
    heading: '#0b69b7',
    muted: '#52606d',
    deviceFill: '#eef6ff',
    deviceText: '#132238',
    deviceSubtext: '#52606d',
  };

  const exportPlacement = device => {
    const width = Number.parseInt(device.dataset.rackWidth || '1', 10);
    const horizontalPosition = Number.parseInt(device.dataset.horizontalPosition || '1', 10);
    if (![1, 2, 3, 4].includes(width) || horizontalPosition < 1 || horizontalPosition > width) {
      return {width: 1, horizontalPosition: 1};
    }
    return {width, horizontalPosition};
  };

  const renderedRackData = racks => racks.map(rack => {
    const card = document.querySelector(`.rack-card[data-rack-id="${rack.id}"]`);
    if (!card) return rack;
    const rackUnits = numberOr(card.dataset.rackUnits, numberOr(rack.u_height, 1));
    const devices = Array.from(card.querySelectorAll('.rack-device')).map(device => {
      const placement = exportPlacement(device);
      return {
        name: device.dataset.deviceName || device.querySelector('span')?.textContent || 'Gerät',
        type: device.dataset.deviceType || '',
        position: numberOr(device.dataset.position, numberOr(rack.starting_unit, 1)),
        height: Math.max(numberOr(device.dataset.deviceHeight, 100 / rackUnits), 1),
        face: device.dataset.face === 'rear' ? 'rear' : 'front',
        color: device.dataset.deviceColor || '#1685fc',
        width: placement.width,
        horizontalPosition: placement.horizontalPosition,
      };
    });
    return {...rack, devices};
  });

  const horizontalGeometry = (faceX, faceWidth, device) => {
    const width = [1, 2, 3, 4].includes(device.width) ? device.width : 1;
    const horizontalPosition = device.horizontalPosition >= 1 && device.horizontalPosition <= width
      ? device.horizontalPosition
      : 1;
    const slotWidth = faceWidth / width;
    return {
      x: faceX + (horizontalPosition - 1) * slotWidth + 3,
      width: Math.max(slotWidth - 6, 1),
    };
  };

  const svgDocument = (width, height, content) =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${content}</svg>`;
  const drawioDocument = cells =>
    `<mxfile host="app.diagrams.net" type="device"><diagram name="Rack export"><mxGraphModel page="0" background="none" grid="1" guides="1" connect="1"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells}</root></mxGraphModel></diagram></mxfile>`;

  const buildRackDrawio = racks => {
    const palette = exportPalette();
    const unit = 22;
    const faceWidth = 250;
    const labelWidth = 28;
    const faceGap = 28;
    const rackGap = 44;
    const header = 55;
    const rackWidth = labelWidth + faceWidth * 2 + faceGap;
    let cells = '';
    let cellId = 2;
    const vertex = (value, style, x, y, width, height) => {
      cells += `<mxCell id="${cellId++}" value="${xmlEscape(value)}" style="${style}" vertex="1" parent="1"><mxGeometry x="${x}" y="${y}" width="${width}" height="${height}" as="geometry"/></mxCell>`;
    };

    racks.forEach((rack, rackIndex) => {
      const rackUnits = numberOr(rack.u_height, 1);
      const baseX = 10 + rackIndex * (rackWidth + rackGap);
      const rackHeight = rackUnits * unit;
      const startingUnit = numberOr(rack.starting_unit, 1);
      vertex(rack.name, `text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontSize=16;fontStyle=1;fontColor=${palette.heading};`, baseX, 0, rackWidth, 25);
      vertex(`${rack.site}${rack.location ? ` · ${rack.location}` : ''} · ${rackUnits}U`, `text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=10;fontColor=${palette.muted};`, baseX, 24, rackWidth, 20);
      ['front', 'rear'].forEach((face, faceIndex) => {
        const faceX = baseX + labelWidth + faceIndex * (faceWidth + faceGap);
        vertex(face === 'front' ? 'VORDERSEITE' : 'RÜCKSEITE', `text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=10;fontColor=${palette.muted};`, faceX, 38, faceWidth, 17);
        vertex('', `rounded=0;html=1;fillColor=none;strokeColor=${palette.frame};strokeWidth=4;`, faceX, header, faceWidth, rackHeight);
        for (let row = 0; row < rackUnits; row += 1) {
          const y = header + row * unit;
          const unitLabel = rack.desc_units ? startingUnit + row : startingUnit + rackUnits - 1 - row;
          if (faceIndex === 0) {
            vertex(String(unitLabel), `text;html=1;strokeColor=none;fillColor=none;align=right;fontSize=8;fontColor=${palette.muted};`, faceX - labelWidth, y, labelWidth - 4, unit);
          }
        }
        rack.devices.filter(device => device.face === face).forEach(device => {
          const positionOffset = device.position - startingUnit;
          const y = rack.desc_units
            ? header + positionOffset * unit
            : header + rackHeight - (positionOffset + device.height) * unit;
          const height = Math.max(device.height * unit, 4);
          const geometry = horizontalGeometry(faceX, faceWidth, device);
          const value = height >= 31
            ? `${device.name}<br><font style="font-size:9px">U${device.position} · ${device.type}</font>`
            : device.name;
          vertex(value, `rounded=1;html=1;whiteSpace=wrap;overflow=hidden;align=left;verticalAlign=top;spacingLeft=5;spacingTop=2;fillColor=${palette.deviceFill};strokeColor=${device.color};strokeWidth=2;fontColor=${palette.deviceText};fontSize=11;`, geometry.x, y + 1, geometry.width, height - 2);
        });
      });
    });
    return drawioDocument(cells);
  };

  const buildRackSvg = racks => {
    const palette = exportPalette();
    const unit = 22;
    const faceWidth = 250;
    const labelWidth = 28;
    const faceGap = 28;
    const rackGap = 44;
    const header = 55;
    const rackWidth = labelWidth + faceWidth * 2 + faceGap;
    const maxUnits = Math.max(...racks.map(rack => numberOr(rack.u_height, 1)), 1);
    const width = racks.length * rackWidth + Math.max(0, racks.length - 1) * rackGap + 20;
    const height = header + maxUnits * unit + 25;
    let definitions = '';
    let content = '';

    racks.forEach((rack, rackIndex) => {
      const rackUnits = numberOr(rack.u_height, 1);
      const baseX = 10 + rackIndex * (rackWidth + rackGap);
      const rackHeight = rackUnits * unit;
      const startingUnit = numberOr(rack.starting_unit, 1);
      content += `<text x="${baseX}" y="20" fill="${palette.heading}" font-family="sans-serif" font-size="16" font-weight="700">${xmlEscape(rack.name)}</text>`;
      content += `<text x="${baseX}" y="39" fill="${palette.muted}" font-family="sans-serif" font-size="11">${xmlEscape(rack.site)}${rack.location ? ` · ${xmlEscape(rack.location)}` : ''} · ${rackUnits}U</text>`;
      ['front', 'rear'].forEach((face, faceIndex) => {
        const faceX = baseX + labelWidth + faceIndex * (faceWidth + faceGap);
        content += `<text x="${faceX + faceWidth / 2}" y="51" text-anchor="middle" fill="${palette.muted}" font-family="sans-serif" font-size="10">${face === 'front' ? 'VORDERSEITE' : 'RÜCKSEITE'}</text>`;
        content += `<rect x="${faceX}" y="${header}" width="${faceWidth}" height="${rackHeight}" fill="none" stroke="${palette.frame}" stroke-width="4"/>`;
        for (let row = 0; row < rackUnits; row += 1) {
          const y = header + row * unit;
          const unitLabel = rack.desc_units ? startingUnit + row : startingUnit + rackUnits - 1 - row;
          content += `<line x1="${faceX}" y1="${y}" x2="${faceX + faceWidth}" y2="${y}" stroke="${palette.grid}" stroke-opacity=".35"/>`;
          if (faceIndex === 0) {
            content += `<text x="${faceX - 6}" y="${y + 15}" text-anchor="end" fill="${palette.muted}" font-family="sans-serif" font-size="9">${unitLabel}</text>`;
          }
        }
        rack.devices.filter(device => device.face === face).forEach((device, deviceIndex) => {
          const positionOffset = device.position - startingUnit;
          const y = rack.desc_units
            ? header + positionOffset * unit
            : header + rackHeight - (positionOffset + device.height) * unit;
          const deviceHeight = Math.max(device.height * unit, 4);
          const geometry = horizontalGeometry(faceX, faceWidth, device);
          const clipId = `netbox-utilities-rack-${rackIndex}-${faceIndex}-${deviceIndex}`;
          definitions += `<clipPath id="${clipId}"><rect x="${geometry.x}" y="${y + 1}" width="${geometry.width}" height="${deviceHeight - 2}"/></clipPath>`;
          content += `<g clip-path="url(#${clipId})">`;
          content += `<rect x="${geometry.x}" y="${y + 1}" width="${geometry.width}" height="${deviceHeight - 2}" rx="3" fill="${palette.deviceFill}" stroke="${xmlEscape(device.color)}" stroke-width="2"/>`;
          if (deviceHeight >= 13) {
            content += `<text x="${geometry.x + 6}" y="${y + Math.min(15, deviceHeight - 4)}" fill="${palette.deviceText}" font-family="sans-serif" font-size="11" font-weight="600">${xmlEscape(device.name)}</text>`;
          }
          if (deviceHeight >= 31) {
            content += `<text x="${geometry.x + 6}" y="${y + 28}" fill="${palette.deviceSubtext}" font-family="sans-serif" font-size="9">U${device.position} · ${xmlEscape(device.type)}</text>`;
          }
          content += '</g>';
        });
      });
    });

    const svg = svgDocument(width, height, `<defs>${definitions}</defs>${content}`);
    return {svg, drawio: buildRackDrawio(racks), width, height};
  };

  const downloadBlob = (blob, filename) => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  };

  const exportGraphic = (graphic, format, filename) => {
    if (format === 'svg') {
      downloadBlob(new Blob([graphic.svg], {type: 'image/svg+xml'}), `${filename}.svg`);
      return;
    }
    if (format === 'drawio') {
      downloadBlob(new Blob([graphic.drawio], {type: 'application/xml'}), `${filename}.drawio`);
      return;
    }

    const image = new Image();
    const url = URL.createObjectURL(new Blob([graphic.svg], {type: 'image/svg+xml'}));
    image.onload = () => {
      const scale = 2;
      const canvas = document.createElement('canvas');
      canvas.width = graphic.width * scale;
      canvas.height = graphic.height * scale;
      const context = canvas.getContext('2d');
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.scale(scale, scale);
      context.drawImage(image, 0, 0);
      canvas.toBlob(blob => downloadBlob(blob, `${filename}.png`), 'image/png');
      URL.revokeObjectURL(url);
    };
    image.onerror = () => URL.revokeObjectURL(url);
    image.src = url;
  };

  const selectedRacks = button => button.dataset.scope === 'all'
    ? rackData
    : rackData.filter(rack => String(rack.id) === button.dataset.scope);
  const containsPartialWidthDevice = racks => racks.some(rack =>
    document.querySelector(`.rack-card[data-rack-id="${rack.id}"] .netbox-utilities-partial-width`));

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    const button = target?.closest('.rack-export');
    if (!button) return;

    const selection = selectedRacks(button);
    if (!selection.length || !containsPartialWidthDevice(selection)) return;

    try {
      const racks = renderedRackData(selection);
      const graphic = buildRackSvg(racks);
      const filename = button.dataset.scope === 'all'
        ? 'racks-gesamt'
        : `rack-${safeName(racks[0]?.name)}`;
      exportGraphic(graphic, button.dataset.format, filename);
      event.preventDefault();
      event.stopImmediatePropagation();
    } catch (error) {
      // Let Topology Views' original click handler provide its normal export fallback.
      console.error('NetBox Utilities could not create the width-aware rack export.', error);
    }
  }, true);
})();
