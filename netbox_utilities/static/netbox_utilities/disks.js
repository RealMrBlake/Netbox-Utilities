(() => {
  "use strict";

  function initSlotGrid(form) {
    const checks = () => [...form.querySelectorAll(".nbu-disk-slot-check")];
    const counter = form.querySelector("[data-nbu-selected-count]");
    const submit = form.querySelector("[data-nbu-fill-selected]");
    const selectFree = form.querySelector("[data-nbu-select-free]");

    const update = () => {
      const selected = checks().filter((check) => check.checked);
      for (const check of checks()) {
        check.closest(".nbu-disk-slot").classList.toggle("nbu-disk-selected", check.checked);
      }
      if (counter) counter.textContent = String(selected.length);
      if (submit) submit.disabled = selected.length === 0;
    };

    form.addEventListener("change", (event) => {
      if (event.target.matches(".nbu-disk-slot-check")) update();
    });
    if (selectFree) {
      selectFree.addEventListener("click", () => {
        const all = checks();
        const select = all.some((check) => !check.checked);
        for (const check of all) check.checked = select;
        update();
      });
    }
    update();
  }

  function initFillForm(form) {
    const textarea = form.querySelector("textarea[name='serials']");
    const status = form.querySelector("[data-nbu-serial-status]");
    if (!textarea || !status) return;

    const update = () => {
      const slots = form.querySelectorAll("input[name='slots']:checked").length;
      const serials = textarea.value.split(/[\r\n;,\t]+/).map((value) => value.trim()).filter(Boolean);
      const seen = new Set();
      const duplicates = serials.filter((serial) => {
        const key = serial.toLowerCase();
        if (seen.has(key)) return true;
        seen.add(key);
        return false;
      });
      let text = `${serials.length} von ${slots} Seriennummern erfasst`;
      let level = serials.length === slots ? "text-success" : "text-muted";
      if (serials.length > slots) {
        text += " – mehr Seriennummern als Steckplätze";
        level = "text-danger";
      }
      if (duplicates.length) {
        text += ` – doppelt: ${[...new Set(duplicates)].join(", ")}`;
        level = "text-danger";
      }
      status.className = `small mt-2 ${level}`;
      status.textContent = text;
    };

    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const grid = document.getElementById("nbu-disk-grid-form");
    if (grid) initSlotGrid(grid);
    const fill = document.getElementById("nbu-disk-fill-form");
    if (fill) initFillForm(fill);
  });
})();
