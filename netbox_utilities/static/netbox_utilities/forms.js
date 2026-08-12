(() => {
  'use strict';

  const dataElement = document.getElementById('netbox-utilities-frontend-data');
  if (!dataElement) return;

  let config;
  try {
    config = JSON.parse(dataElement.textContent);
  } catch (_error) {
    return;
  }

  function rewriteImageUploadLinks(root = document) {
    if (!config.image_attachment_add_url || !config.bulk_image_upload_url) return;
    const singleUploadPath = new URL(config.image_attachment_add_url, document.baseURI).pathname;

    root.querySelectorAll('a[href]').forEach((link) => {
      const current = new URL(link.href, document.baseURI);
      if (current.pathname !== singleUploadPath) return;
      if (!current.searchParams.has('object_type') || !current.searchParams.has('object_id')) return;

      const bulkUpload = new URL(config.bulk_image_upload_url, document.baseURI);
      bulkUpload.search = current.search;
      link.href = bulkUpload.href;
      link.title = 'Mehrere Bilder gleichzeitig hochladen';
      link.replaceChildren();
      const icon = document.createElement('i');
      icon.className = 'mdi mdi-image-multiple me-1';
      icon.setAttribute('aria-hidden', 'true');
      link.append(icon, document.createTextNode('Mehrere Bilder hochladen'));
    });
  }

  function configureTenantConfirmation(root = document) {
    root.querySelectorAll('[data-netbox-utilities-autofilled-tenant]').forEach((field) => {
      const form = field.form;
      if (!form || form.dataset.netboxUtilitiesTenantConfirmation === 'true') return;
      form.dataset.netboxUtilitiesTenantConfirmation = 'true';

      form.addEventListener('submit', (event) => {
        const candidateFields = form.querySelectorAll('[data-netbox-utilities-autofilled-tenant]');
        for (const candidateField of candidateFields) {
          const candidate = candidateField.dataset.netboxUtilitiesAutofilledTenant;
          if (!candidate || String(candidateField.value) !== candidate) continue;
          if (candidateField.dataset.netboxUtilitiesTenantConfirmed === candidate) continue;

          const selectedOption = candidateField.selectedOptions?.[0];
          const tenantLabel = selectedOption?.textContent.trim() || `ID ${candidate}`;
          const confirmed = window.confirm(
            `Der Mandant „${tenantLabel}“ wurde automatisch erkannt. Bitte bestätigen Sie diese Zuordnung.`
          );
          if (!confirmed) {
            event.preventDefault();
            candidateField.focus();
            return;
          }
          candidateField.dataset.netboxUtilitiesTenantConfirmed = candidate;
        }
      });
    });
  }

  function configureImagePreview(root = document) {
    const input = root.querySelector('.netbox-utilities-multi-image-input');
    const preview = document.getElementById('netbox-utilities-image-preview');
    if (!input || !preview || input.dataset.netboxUtilitiesPreview === 'true') return;
    input.dataset.netboxUtilitiesPreview = 'true';
    let objectUrls = [];

    input.addEventListener('change', () => {
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
      objectUrls = [];
      preview.replaceChildren();

      Array.from(input.files).forEach((file) => {
        const objectUrl = URL.createObjectURL(file);
        objectUrls.push(objectUrl);
        const item = document.createElement('div');
        item.className = 'netbox-utilities-image-preview-item';
        const image = document.createElement('img');
        image.src = objectUrl;
        image.alt = '';
        const name = document.createElement('div');
        name.className = 'netbox-utilities-image-preview-name text-secondary mt-1';
        name.title = file.name;
        name.textContent = file.name;
        item.append(image, name);
        preview.appendChild(item);
      });
    });
  }

  function configureRackWidth(root = document) {
    const widthField = root.querySelector('[name="utilities_rack_width"]');
    const positionField = root.querySelector('[name="utilities_horizontal_position"]');
    if (!widthField || !positionField || widthField.dataset.netboxUtilitiesWidth === 'true') return;
    widthField.dataset.netboxUtilitiesWidth = 'true';

    const updatePositions = () => {
      const width = Number.parseInt(widthField.value || '1', 10);
      Array.from(positionField.options).forEach((option) => {
        const position = Number.parseInt(option.value || '1', 10);
        option.disabled = position > width;
      });
      if (width === 1 || Number.parseInt(positionField.value || '1', 10) > width) {
        positionField.value = '1';
        positionField.dispatchEvent(new Event('change', {bubbles: true}));
      }
      positionField.disabled = width === 1;
    };

    widthField.addEventListener('change', updatePositions);
    updatePositions();
  }

  function initialize(root = document) {
    rewriteImageUploadLinks(root);
    configureTenantConfirmation(root);
    configureImagePreview(root);
    configureRackWidth(root);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initialize(), {once: true});
  } else {
    initialize();
  }
  document.addEventListener('htmx:afterSettle', (event) => initialize(event.target));
})();
