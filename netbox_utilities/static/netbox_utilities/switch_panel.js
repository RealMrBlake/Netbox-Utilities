// Switch front panel on the device page: moves it above the "Device" and "Management" cards and
// switches between the status and VLAN colours.
(function () {
  "use strict";

  const STORAGE_KEY = "netbox_utilities.switch_panel_mode";

  function relocate(panel) {
    // The plugin can only render into a column; place the panel above the row with both columns.
    const row = panel.closest(".row");
    if (!row || row.dataset.nbuSwitchPanelMoved) return;
    row.dataset.nbuSwitchPanelMoved = "true";
    const wrapper = document.createElement("div");
    wrapper.className = "row mb-3";
    const column = document.createElement("div");
    column.className = "col col-12";
    column.appendChild(panel);
    wrapper.appendChild(column);
    row.parentNode.insertBefore(wrapper, row);
  }

  function init() {
    const panel = document.querySelector("[data-nbu-switch-panel]");
    if (!panel) return;
    relocate(panel);

    if (window.bootstrap && window.bootstrap.Tooltip) {
      panel.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((element) => {
        window.bootstrap.Tooltip.getOrCreateInstance(element, { container: "body" });
      });
    }

    function setMode(mode) {
      panel.classList.toggle("nbu-switch-vlan", mode === "vlan");
      panel.querySelectorAll("[data-nbu-switch-mode]").forEach((button) => {
        button.classList.toggle("active", button.dataset.nbuSwitchMode === mode);
      });
      panel.querySelectorAll("[data-nbu-switch-legend]").forEach((legend) => {
        legend.classList.toggle("d-none", legend.dataset.nbuSwitchLegend !== mode);
      });
      try {
        localStorage.setItem(STORAGE_KEY, mode);
      } catch (error) {
        /* private mode: the choice is just not remembered */
      }
    }

    panel.querySelectorAll("[data-nbu-switch-mode]").forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.nbuSwitchMode));
    });

    let saved = "status";
    try {
      saved = localStorage.getItem(STORAGE_KEY) || "status";
    } catch (error) {
      /* ignore */
    }
    setMode(saved === "vlan" ? "vlan" : "status");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
