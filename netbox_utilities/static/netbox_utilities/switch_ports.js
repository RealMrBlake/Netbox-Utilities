// "Ports" tab of switches: colour mode, VLAN filter, search and tile → table row highlighting.
(function () {
  "use strict";

  const STORAGE_KEY = "netbox_utilities.port_mode";

  function init() {
    const root = document.querySelector("[data-nbu-ports]");
    if (!root) return;

    const tiles = Array.from(root.querySelectorAll("[data-nbu-port]"));
    const rows = Array.from(root.querySelectorAll("[data-nbu-port-row]"));
    const search = root.querySelector("[data-nbu-port-search]");
    let vlanFilter = null;

    if (window.bootstrap && window.bootstrap.Tooltip) {
      tiles.forEach((tile) => window.bootstrap.Tooltip.getOrCreateInstance(tile, { container: "body" }));
    }

    function setMode(mode) {
      root.classList.toggle("nbu-ports-vlan", mode === "vlan");
      root.querySelectorAll("[data-nbu-legend]").forEach((legend) => {
        legend.classList.toggle("d-none", legend.dataset.nbuLegend !== mode);
      });
      const radio = root.querySelector(`input[name="nbu-port-mode"][value="${mode}"]`);
      if (radio) radio.checked = true;
      try {
        localStorage.setItem(STORAGE_KEY, mode);
      } catch (error) {
        /* private mode: the choice is just not remembered */
      }
      if (mode !== "vlan") applyFilter(null);
    }

    function applyFilter(vlan) {
      vlanFilter = vlan;
      tiles.forEach((tile) => tile.classList.toggle("nbu-port-dimmed", vlan !== null && tile.dataset.vlan !== vlan));
      root.querySelectorAll("[data-nbu-vlan-filter]").forEach((button) => {
        button.classList.toggle("fw-bold", vlan !== null && button.dataset.nbuVlanFilter === vlan);
      });
      filterRows();
    }

    function filterRows() {
      const query = (search && search.value || "").trim().toLowerCase();
      rows.forEach((row) => {
        const matchesText = !query || row.textContent.toLowerCase().includes(query);
        const matchesVlan = vlanFilter === null || row.dataset.vlan === vlanFilter;
        row.classList.toggle("d-none", !(matchesText && matchesVlan));
      });
      if (query) {
        const visible = new Set(rows.filter((row) => !row.classList.contains("d-none")).map((row) => row.dataset.nbuPortRow));
        tiles.forEach((tile) => tile.classList.toggle("nbu-port-dimmed", !visible.has(tile.dataset.nbuPort)));
      } else if (vlanFilter === null) {
        tiles.forEach((tile) => tile.classList.remove("nbu-port-dimmed"));
      }
    }

    root.querySelectorAll('input[name="nbu-port-mode"]').forEach((radio) => {
      radio.addEventListener("change", () => setMode(radio.value));
    });
    root.querySelectorAll("[data-nbu-vlan-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        const vlan = button.dataset.nbuVlanFilter;
        applyFilter(vlanFilter === vlan ? null : vlan);
      });
    });
    if (search) search.addEventListener("input", filterRows);

    tiles.forEach((tile) => {
      tile.addEventListener("click", () => {
        const row = document.getElementById(`nbu-port-row-${tile.dataset.nbuPort}`);
        if (!row) return;
        row.classList.add("table-active");
        window.setTimeout(() => row.classList.remove("table-active"), 2000);
      });
    });

    let saved = "state";
    try {
      saved = localStorage.getItem(STORAGE_KEY) || "state";
    } catch (error) {
      /* ignore */
    }
    setMode(saved === "vlan" ? "vlan" : "state");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
