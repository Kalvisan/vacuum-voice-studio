const state = {
  packs: [],
  activePackId: null,
  files: [],
  filter: "",
  customOnly: false,
  languages: [],
  basePack: { ready: false, language: null },
  highlightNewPack: false,
  busyKeys: new Set(),
};

const GUIDE_DISMISS_KEY = "x20-pack-guide-dismissed";

const els = {
  app: document.querySelector(".app"),
  packSelect: document.getElementById("packSelect"),
  newPackBtn: document.getElementById("newPackBtn"),
  fileGrid: document.getElementById("fileGrid"),
  emptyState: document.getElementById("emptyState"),
  emptyText: document.getElementById("emptyText"),
  searchInput: document.getElementById("searchInput"),
  customOnly: document.getElementById("customOnly"),
  toast: document.getElementById("toast"),
  newPackDialog: document.getElementById("newPackDialog"),
  newPackForm: document.getElementById("newPackForm"),
  packNameInput: document.getElementById("packNameInput"),
  packLangSelect: document.getElementById("packLangSelect"),
  cancelPackBtn: document.getElementById("cancelPackBtn"),
  createPackBtn: document.getElementById("createPackBtn"),
  deletePackBtn: document.getElementById("deletePackBtn"),
  deletePackDialog: document.getElementById("deletePackDialog"),
  deletePackName: document.getElementById("deletePackName"),
  deletePackEffects: document.getElementById("deletePackEffects"),
  cancelDeletePackBtn: document.getElementById("cancelDeletePackBtn"),
  confirmDeletePackBtn: document.getElementById("confirmDeletePackBtn"),
  setupFlow: document.getElementById("setupFlow"),
  setupStepBase: document.getElementById("setupStepBase"),
  setupStepPack: document.getElementById("setupStepPack"),
  setupStepPackText: document.getElementById("setupStepPackText"),
  dashboard: document.getElementById("dashboard"),
  baseLangSelect: document.getElementById("baseLangSelect"),
  baseLangSelectChange: document.getElementById("baseLangSelectChange"),
  downloadBaseBtn: document.getElementById("downloadBaseBtn"),
  downloadBaseChangeBtn: document.getElementById("downloadBaseChangeBtn"),
  toggleBaseChange: document.getElementById("toggleBaseChange"),
  toggleBaseChangeText: document.getElementById("toggleBaseChangeText"),
  baseChangePanel: document.getElementById("baseChangePanel"),
  baseLangLabel: document.getElementById("baseLangLabel"),
  progressRing: document.getElementById("progressRing"),
  replacedCount: document.getElementById("replacedCount"),
  totalCount: document.getElementById("totalCount"),
  legendCustom: document.getElementById("legendCustom"),
  legendOriginal: document.getElementById("legendOriginal"),
  packMeta: document.getElementById("packMeta"),
  packGuide: document.getElementById("packGuide"),
  packGuideBadge: document.getElementById("packGuideBadge"),
  packGuideTitle: document.getElementById("packGuideTitle"),
  packGuideLead: document.getElementById("packGuideLead"),
  packGuideSteps: document.getElementById("packGuideSteps"),
  packGuideActions: document.getElementById("packGuideActions"),
  packGuideNewBtn: document.getElementById("packGuideNewBtn"),
  dismissPackGuide: document.getElementById("dismissPackGuide"),
  toolbar: document.getElementById("toolbar"),
};

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  els.toast.classList.toggle("error", isError);
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    els.toast.hidden = true;
  }, 2800);
}

function isBusy(key) {
  if (key) return state.busyKeys.has(key);
  return state.busyKeys.size > 0;
}

function syncBusyUi() {
  const globalBusy = state.busyKeys.size > 0;
  els.app.classList.toggle("is-busy", globalBusy);

  document.querySelectorAll("[data-busy-disable]").forEach((el) => {
    el.disabled = globalBusy || el.dataset.staticDisabled === "true";
  });

  document.querySelectorAll("[data-busy-key]").forEach((el) => {
    const key = el.dataset.busyKey;
    const loading = state.busyKeys.has(key);
    el.disabled = loading || (globalBusy && !loading);
    el.classList.toggle("is-loading", loading);
  });
}

async function withBusy(key, fn) {
  if (state.busyKeys.has(key)) return null;
  state.busyKeys.add(key);
  syncBusyUi();
  try {
    return await fn();
  } finally {
    state.busyKeys.delete(key);
    syncBusyUi();
  }
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function saveUiPrefs() {
  localStorage.setItem(
    "x20-studio-ui",
    JSON.stringify({
      filter: state.filter,
      customOnly: state.customOnly,
    })
  );
}

function loadUiPrefs() {
  try {
    const raw = localStorage.getItem("x20-studio-ui");
    if (!raw) return;
    const prefs = JSON.parse(raw);
    state.filter = prefs.filter || "";
    state.customOnly = Boolean(prefs.customOnly);
    els.searchInput.value = state.filter;
    els.customOnly.checked = state.customOnly;
  } catch (_) {
    /* ignore */
  }
}

function languageLabel(code) {
  const entry = state.languages.find((item) => item.code === code);
  return entry?.label || code;
}

function formatLanguageOption(entry) {
  return `${entry.label} (${entry.code})`;
}

function fillLanguageSelect(select, preferred) {
  if (!select) return;
  select.innerHTML = "";
  for (const entry of state.languages) {
    const opt = document.createElement("option");
    opt.value = entry.code;
    opt.textContent = entry.label ? formatLanguageOption(entry) : entry.code;
    select.appendChild(opt);
  }
  const code = preferred || state.basePack.language || "en";
  if (state.languages.some((item) => item.code === code)) {
    select.value = code;
  } else if (state.languages.length > 0) {
    select.value = state.languages[0].code;
  }
}

function renderLanguageSelects() {
  const preferred = state.basePack.language || "en";
  fillLanguageSelect(els.baseLangSelect, preferred);
  fillLanguageSelect(els.baseLangSelectChange, preferred);
  fillLanguageSelect(els.packLangSelect, preferred);
}

function closeBaseChangePanel() {
  els.baseChangePanel.hidden = true;
  els.toggleBaseChange.setAttribute("aria-expanded", "false");
  els.toggleBaseChangeText.textContent = "Change";
}

function openBaseChangePanel() {
  els.baseChangePanel.hidden = false;
  els.toggleBaseChange.setAttribute("aria-expanded", "true");
  els.toggleBaseChangeText.textContent = "Hide";
  renderLanguageSelects();
}

function loadGuideDismissed() {
  try {
    const raw = localStorage.getItem(GUIDE_DISMISS_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch (_) {
    return new Set();
  }
}

function saveGuideDismissed(set) {
  localStorage.setItem(GUIDE_DISMISS_KEY, JSON.stringify([...set]));
}

function guideDismissKey(pack) {
  if (!pack) return "__no_pack__";
  return pack.id;
}

function isGuideDismissed(pack) {
  return loadGuideDismissed().has(guideDismissKey(pack));
}

function dismissActivePackGuide() {
  if (isBusy()) return;
  const pack = state.packs.find((p) => p.id === state.activePackId) || null;
  const key = guideDismissKey(pack);
  const dismissed = loadGuideDismissed();
  dismissed.add(key);
  saveGuideDismissed(dismissed);
  state.highlightNewPack = false;
  updatePackGuide();
}

function shouldShowPackGuide(pack) {
  if (!state.basePack.ready) return false;
  if (state.highlightNewPack) return true;
  if (!pack) return !isGuideDismissed(null);
  if ((pack.replaced_count || 0) > 0) return false;
  return !isGuideDismissed(pack);
}

function updatePackGuide() {
  const pack = state.packs.find((p) => p.id === state.activePackId) || null;
  const show = shouldShowPackGuide(pack);

  els.packGuide.hidden = !show;
  if (!show) return;

  const noPack = !pack;
  els.packGuideBadge.textContent = noPack ? "Get started" : "New pack";

  if (noPack) {
    els.packGuideTitle.textContent = "Create your first voice pack";
    els.packGuideLead.textContent =
      "A voice pack is your personal copy of all 101 robot sounds. Replace only the phrases you want. The rest stay official.";
    els.packGuideSteps.innerHTML = `
      <li><strong>Create a pack:</strong> copies every sound from your base language</li>
      <li><strong>Find a phrase:</strong> search or scroll the list below</li>
      <li><strong>Drop an MP3:</strong> on any card to replace that one sound on your robot</li>
    `;
    els.packGuideActions.hidden = false;
    els.packGuideNewBtn.hidden = false;
  } else {
    els.packGuideTitle.textContent = `Customize "${pack.name}"`;
    els.packGuideLead.textContent =
      "This pack is a full copy of your base sounds. Nothing changes on the robot until you replace individual files.";
    els.packGuideSteps.innerHTML = `
      <li><strong>Listen:</strong> compare Base (original) and Pack (what installs)</li>
      <li><strong>Replace:</strong> drag an MP3 onto a card or click to pick a file</li>
      <li><strong>Install:</strong> when ready, build and upload from the CLI or TUI menu</li>
    `;
    els.packGuideActions.hidden = true;
  }
}

function updateSetupFlow() {
  const ready = state.basePack.ready;
  els.setupFlow.hidden = ready;
  els.setupStepBase.classList.toggle("is-active", !ready);
  els.setupStepBase.classList.toggle("is-done", ready);
  els.setupStepPack.classList.toggle("is-locked", !ready);
  els.setupStepPack.classList.toggle("is-active", ready && state.packs.length === 0);
  if (ready) {
    els.setupStepPackText.textContent = "Use New pack in the dashboard to start customizing sounds.";
  }
}

function updateBaseUi() {
  const ready = state.basePack.ready;
  const lang = state.basePack.language || "en";

  updateSetupFlow();
  els.dashboard.hidden = !ready;
  els.baseLangLabel.textContent = `${languageLabel(lang)} (${lang})`;
  els.emptyState.hidden = true;

  if (!ready) {
    closeBaseChangePanel();
    els.packGuide.hidden = true;
    els.toolbar.hidden = true;
    els.fileGrid.hidden = true;
  }

  els.newPackBtn.disabled = !ready;
  els.packSelect.dataset.staticDisabled = state.packs.length === 0 ? "true" : "false";
  syncBusyUi();
}

async function loadLanguages() {
  return withBusy("init", async () => {
    const data = await api("/api/languages");
    state.languages = data.languages || [];
    state.basePack = data.base_pack || { ready: false, language: null };
    renderLanguageSelects();
    updateBaseUi();
  });
}

async function downloadBasePack(fromChange = false) {
  if (isBusy("download-base")) return;

  const select = fromChange ? els.baseLangSelectChange : els.baseLangSelect;
  const language = select?.value || "en";
  const replacing = state.basePack.ready;

  if (replacing && !window.confirm(`Replace base pack with ${language}? Your custom packs keep their files.`)) {
    return;
  }

  await withBusy("download-base", async () => {
    showToast(`Downloading ${language}...`);
    const data = await api("/api/download-base", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language, reset_working: true }),
    });
    state.basePack = data.base_pack || state.basePack;
    renderLanguageSelects();
    updateBaseUi();
    closeBaseChangePanel();
    await refreshPacks();
    showToast(`Base pack ${language} ready`);
  }).catch((err) => {
    showToast(err.message, true);
  });
}

function updateProgressRing(replaced, total) {
  const safeTotal = total || 101;
  const pct = safeTotal ? Math.min(100, (replaced / safeTotal) * 100) : 0;
  els.progressRing.style.strokeDasharray = `${pct} ${100 - pct}`;
  els.replacedCount.textContent = String(replaced);
  els.totalCount.textContent = String(safeTotal);
  els.legendCustom.textContent = String(replaced);
  els.legendOriginal.textContent = String(Math.max(0, safeTotal - replaced));
}

function updateStats(pack) {
  if (!pack) {
    updateProgressRing(0, 101);
    els.packMeta.hidden = true;
    els.packMeta.textContent = "";
    updatePackGuide();
    return;
  }

  const total = pack.total_count || 101;
  const replaced = pack.replaced_count || 0;
  updateProgressRing(replaced, total);

  const lang = pack.language || "en";
  els.packMeta.textContent = `Install language: ${languageLabel(lang)} (${lang})`;
  els.packMeta.hidden = false;

  if (replaced > 0) {
    state.highlightNewPack = false;
  }

  updatePackGuide();
}

function renderPackSelect() {
  els.packSelect.innerHTML = "";
  for (const pack of state.packs) {
    const opt = document.createElement("option");
    opt.value = pack.id;
    opt.textContent = pack.name;
    if (pack.active || pack.id === state.activePackId) {
      opt.selected = true;
      state.activePackId = pack.id;
    }
    els.packSelect.appendChild(opt);
  }
  els.packSelect.dataset.staticDisabled = state.packs.length === 0 ? "true" : "false";
  els.deletePackBtn.hidden = state.packs.length === 0;
}

function filteredFiles() {
  const q = state.filter.trim().toLowerCase();
  return state.files.filter((file) => {
    if (state.customOnly && !file.custom) return false;
    if (!q) return true;
    return (
      file.file.toLowerCase().includes(q) ||
      file.text.toLowerCase().includes(q) ||
      file.event_id.toLowerCase().includes(q)
    );
  });
}

function renderFiles() {
  const list = filteredFiles();
  els.fileGrid.innerHTML = "";

  for (const file of list) {
    const card = document.createElement("article");
    card.className = `card${file.custom ? " custom" : ""}`;
    card.dataset.file = file.file;

    card.innerHTML = `
      <div class="card-head">
        <span class="file-name">${file.file}</span>
        <span class="badge${file.custom ? " custom" : ""}">${file.custom ? "Custom" : "Base"}</span>
      </div>
      <p class="phrase">${escapeHtml(file.text)}</p>
      <div class="audio-stack">
        <div class="audio-row">
          <label>Base</label>
          <audio controls preload="none" src="/api/original/${encodeURIComponent(file.file)}"></audio>
        </div>
        <div class="audio-row">
          <label>Pack</label>
          <audio controls preload="none" src="/api/packs/${encodeURIComponent(state.activePackId)}/audio/${encodeURIComponent(file.file)}?t=${Date.now()}"></audio>
        </div>
      </div>
      <div class="dropzone" tabindex="0" role="button" aria-label="Replace ${file.file}">
        Drop MP3 or click
        <input type="file" accept="audio/mpeg,audio/mp3,.mp3" hidden>
      </div>
      ${file.custom ? `<div class="card-actions"><button type="button" class="btn btn-small revert-btn" data-busy-disable>Revert</button></div>` : ""}
    `;

    wireDropzone(card, file.file);
    els.fileGrid.appendChild(card);
  }
  syncBusyUi();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function wireDropzone(card, fileName) {
  const zone = card.querySelector(".dropzone");
  const input = zone.querySelector("input");

  zone.addEventListener("click", () => {
    if (isBusy()) return;
    input.click();
  });
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (isBusy()) return;
      input.click();
    }
  });

  input.addEventListener("change", () => {
    if (input.files && input.files[0]) {
      uploadFile(fileName, input.files[0], card);
      input.value = "";
    }
  });

  ["dragenter", "dragover"].forEach((ev) => {
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      if (!isBusy()) card.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      card.classList.remove("dragover");
    });
  });
  zone.addEventListener("drop", (e) => {
    if (isBusy()) return;
    const f = e.dataTransfer?.files?.[0];
    if (f) uploadFile(fileName, f, card);
  });

  const revert = card.querySelector(".revert-btn");
  if (revert) {
    revert.addEventListener("click", () => revertFile(fileName, card));
  }
}

async function uploadFile(fileName, file, card) {
  if (!state.activePackId) return;
  if (!file.name.toLowerCase().endsWith(".mp3")) {
    showToast("MP3 files only.", true);
    return;
  }

  const key = `upload:${fileName}`;
  if (isBusy(key)) return;

  await withBusy(key, async () => {
    if (card) card.classList.add("is-uploading");
    const body = await file.arrayBuffer();
    const data = await api(
      `/api/packs/${encodeURIComponent(state.activePackId)}/files/${encodeURIComponent(fileName)}`,
      { method: "PUT", body }
    );
    updateStats(data.pack);
    await refreshFiles();
    showToast(`Saved ${fileName}`);
  }).catch((err) => {
    showToast(err.message, true);
  }).finally(() => {
    if (card) card.classList.remove("is-uploading");
  });
}

async function revertFile(fileName, card) {
  if (!state.activePackId) return;
  const key = `revert:${fileName}`;
  if (isBusy(key)) return;

  await withBusy(key, async () => {
    if (card) card.classList.add("is-uploading");
    const data = await api(
      `/api/packs/${encodeURIComponent(state.activePackId)}/files/${encodeURIComponent(fileName)}`,
      { method: "DELETE" }
    );
    updateStats(data.pack);
    await refreshFiles();
    showToast(`Reverted ${fileName}`);
  }).catch((err) => {
    showToast(err.message, true);
  }).finally(() => {
    if (card) card.classList.remove("is-uploading");
  });
}

async function refreshPacks() {
  if (isBusy("refresh-packs")) return;

  return withBusy("refresh-packs", async () => {
    const data = await api("/api/packs");
    state.packs = data.packs || [];
    const active = state.packs.find((p) => p.active);
    state.activePackId = active?.id || state.packs[0]?.id || null;

    const hasPacks = state.packs.length > 0;
    els.fileGrid.hidden = !hasPacks;
    els.toolbar.hidden = !hasPacks || !state.basePack.ready;

    renderPackSelect();
    updateSetupFlow();

    if (state.activePackId) {
      const pack = state.packs.find((p) => p.id === state.activePackId);
      updateStats(pack);
      await refreshFiles();
    } else {
      updateStats(null);
    }
    updatePackGuide();
    syncBusyUi();
  });
}

async function refreshFiles() {
  if (!state.activePackId) return;
  const data = await api(`/api/packs/${encodeURIComponent(state.activePackId)}/files`);
  state.files = data.files || [];
  updateStats(data.pack);
  renderFiles();
}

async function createPack(name, language) {
  return withBusy("create-pack", async () => {
    const data = await api("/api/packs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, language }),
    });
    state.activePackId = data.pack.id;
    state.highlightNewPack = true;
    const dismissed = loadGuideDismissed();
    dismissed.delete(data.pack.id);
    saveGuideDismissed(dismissed);
    await refreshPacks();
    showToast(`Created "${name}"`);
  });
}

function getActivePack() {
  return state.packs.find((p) => p.id === state.activePackId) || null;
}

function buildDeleteEffects(pack) {
  const replaced = pack.replaced_count || 0;
  const items = [
    `Removes the pack folder from your computer. This cannot be undone.`,
    `Your base pack (${state.basePack.language || "base"}) and other voice packs stay untouched.`,
    `Your robot keeps its current sounds until you install a different pack.`,
  ];
  if (replaced > 0) {
    items.unshift(
      `Deletes <strong>${replaced}</strong> custom sound${replaced === 1 ? "" : "s"} you added to this pack.`
    );
  } else {
    items.unshift(`This pack has no custom sounds yet. Only the empty project copy will be removed.`);
  }
  return items;
}

function openDeletePackDialog() {
  if (isBusy()) return;
  const pack = getActivePack();
  if (!pack) {
    showToast("No pack selected.", true);
    return;
  }

  els.deletePackName.textContent = `"${pack.name}"`;
  els.deletePackEffects.innerHTML = buildDeleteEffects(pack)
    .map((text) => `<li>${text}</li>`)
    .join("");
  els.deletePackDialog.showModal();
}

async function deleteActivePack() {
  const pack = getActivePack();
  if (!pack || isBusy("delete-pack")) return;

  await withBusy("delete-pack", async () => {
    await api(`/api/packs/${encodeURIComponent(pack.id)}`, { method: "DELETE" });
    els.deletePackDialog.close();

    const dismissed = loadGuideDismissed();
    dismissed.delete(pack.id);
    saveGuideDismissed(dismissed);

    if (state.activePackId === pack.id) {
      state.activePackId = null;
      state.files = [];
    }

    await refreshPacks();

    if (state.packs.length > 0 && !state.packs.some((p) => p.active)) {
      await activatePack(state.packs[0].id);
    }

    showToast(`Deleted "${pack.name}"`);
  }).catch((err) => {
    showToast(err.message, true);
  });
}

async function activatePack(packId) {
  if (isBusy("activate-pack")) return;
  return withBusy("activate-pack", async () => {
    const data = await api(`/api/packs/${encodeURIComponent(packId)}/activate`, { method: "POST" });
    state.activePackId = packId;
    state.highlightNewPack = false;
    updateStats(data.pack);
    await refreshFiles();
    updatePackGuide();
  });
}

function openNewPackDialog() {
  if (isBusy()) return;
  if (!state.basePack.ready) {
    showToast("Download the base pack first.", true);
    return;
  }
  els.packNameInput.value = "";
  const defaultLang = state.basePack.language || "en";
  renderLanguageSelects();
  if (state.languages.some((item) => item.code === defaultLang)) {
    els.packLangSelect.value = defaultLang;
  }
  els.newPackDialog.showModal();
  els.packNameInput.focus();
}

els.newPackBtn.addEventListener("click", openNewPackDialog);
els.packGuideNewBtn.addEventListener("click", openNewPackDialog);
els.deletePackBtn.addEventListener("click", openDeletePackDialog);
els.dismissPackGuide.addEventListener("click", dismissActivePackGuide);
els.downloadBaseBtn.addEventListener("click", () => downloadBasePack(false));
els.downloadBaseChangeBtn.addEventListener("click", () => downloadBasePack(true));
els.cancelPackBtn.addEventListener("click", () => {
  if (!isBusy("create-pack")) els.newPackDialog.close();
});
els.cancelDeletePackBtn.addEventListener("click", () => {
  if (!isBusy("delete-pack")) els.deletePackDialog.close();
});
els.confirmDeletePackBtn.addEventListener("click", () => deleteActivePack());

els.toggleBaseChange.addEventListener("click", () => {
  if (isBusy()) return;
  if (els.baseChangePanel.hidden) {
    openBaseChangePanel();
  } else {
    closeBaseChangePanel();
  }
});

els.newPackForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isBusy("create-pack")) return;
  const name = els.packNameInput.value.trim();
  const language = els.packLangSelect.value;
  if (!name || !language) return;
  try {
    await createPack(name, language);
    els.newPackDialog.close();
  } catch (err) {
    showToast(err.message, true);
  }
});

els.packSelect.addEventListener("change", async () => {
  if (isBusy()) {
    renderPackSelect();
    return;
  }
  try {
    await activatePack(els.packSelect.value);
  } catch (err) {
    showToast(err.message, true);
    renderPackSelect();
  }
});

els.searchInput.addEventListener("input", () => {
  state.filter = els.searchInput.value;
  saveUiPrefs();
  renderFiles();
});

els.customOnly.addEventListener("change", () => {
  state.customOnly = els.customOnly.checked;
  saveUiPrefs();
  renderFiles();
});

loadUiPrefs();
syncBusyUi();

(async function init() {
  try {
    await loadLanguages();
    await refreshPacks();
  } catch (err) {
    els.emptyState.hidden = false;
    els.fileGrid.hidden = true;
    els.toolbar.hidden = true;
    els.setupFlow.hidden = true;
    els.dashboard.hidden = true;
    els.packGuide.hidden = true;
    els.emptyText.textContent = err.message;
  }
})();
