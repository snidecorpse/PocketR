const STEP_ORDER = ["background", "sprites", "dialogue"];
const STEP_TITLES = {
  background: "Background",
  sprites: "Sprites",
  dialogue: "Dialogue",
};

const appState = {
  meta: null,
  current: null,
  stepIndex: 0,
  dialogueDraft: {},
  activeCategory: null,
  preview: {
    room: "hub",
    group: "IdleHappy",
    frame: 0,
  },
};

const els = {
  status: document.getElementById("status-line"),
  startBtn: document.getElementById("start-btn"),

  stepPrevBtn: document.getElementById("step-prev-btn"),
  stepNextBtn: document.getElementById("step-next-btn"),
  stepSaveNextBtn: document.getElementById("step-save-next-btn"),
  stepTitle: document.getElementById("step-title"),
  stepCaption: document.getElementById("step-caption"),
  stepBackground: document.getElementById("step-background"),
  stepSprites: document.getElementById("step-sprites"),
  stepDialogue: document.getElementById("step-dialogue"),

  bgGrid: document.getElementById("background-grid"),
  animGrid: document.getElementById("anim-grid"),
  singleGrid: document.getElementById("single-grid"),

  categoryList: document.getElementById("category-list"),
  activeCategoryLabel: document.getElementById("active-category-label"),
  dialogueRows: document.getElementById("dialogue-rows"),

  addCategoryBtn: document.getElementById("add-category-btn"),
  renameCategoryBtn: document.getElementById("rename-category-btn"),
  deleteCategoryBtn: document.getElementById("delete-category-btn"),
  addRowBtn: document.getElementById("add-row-btn"),
  saveDialogueBtn: document.getElementById("save-dialogue-btn"),
  clearDialogueBtn: document.getElementById("clear-dialogue-btn"),

  validateBtn: document.getElementById("validate-btn"),
  applyBtn: document.getElementById("apply-btn"),
  discardBtn: document.getElementById("discard-btn"),
  snapshotSelect: document.getElementById("snapshot-select"),
  downloadSnapshotBtn: document.getElementById("download-snapshot-btn"),
  restoreBtn: document.getElementById("restore-btn"),

  previewRoom: document.getElementById("preview-room"),
  previewGroup: document.getElementById("preview-group"),
  previewFrame: document.getElementById("preview-frame"),
  previewCanvas: document.getElementById("preview-canvas"),
  previewMeta: document.getElementById("preview-meta"),
};

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.style.color = isError ? "#ff9f9f" : "#95d3c7";
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function apiGet(path) {
  const res = await fetch(path, { cache: "no-store" });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.ok === false) {
    throw new Error(json.error || `Request failed (${res.status})`);
  }
  return json;
}

async function apiPostJson(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.ok === false) {
    throw new Error(json.error || `Request failed (${res.status})`);
  }
  return json;
}

async function apiPostForm(path, formData) {
  const res = await fetch(path, { method: "POST", body: formData });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.ok === false) {
    throw new Error(json.error || `Request failed (${res.status})`);
  }
  return json;
}

function effectiveBackground(room) {
  return appState.current?.effective?.backgrounds?.find((x) => x.room === room) || null;
}

function effectiveAnim(group) {
  return appState.current?.effective?.anim_groups?.find((x) => x.group === group) || null;
}

function effectiveSingle(name) {
  return appState.current?.effective?.single_sprites?.find((x) => x.name === name) || null;
}

function formatAnimFiles(info) {
  const names = Array.isArray(info?.file_names) ? info.file_names : [];
  if (!names.length) return "none";
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} (+${names.length - 3} more)`;
}

function buildDialogueDraft(templateData, effectiveData) {
  const out = {};
  const tpl = templateData && typeof templateData === "object" ? templateData : {};
  const eff = effectiveData && typeof effectiveData === "object" ? effectiveData : {};

  for (const [cat, rows] of Object.entries(tpl)) {
    out[String(cat)] = deepClone(Array.isArray(rows) ? rows : []);
  }

  for (const [cat, rows] of Object.entries(eff)) {
    out[String(cat)] = deepClone(Array.isArray(rows) ? rows : []);
  }

  if (!Object.keys(out).length) {
    out.greeting = [
      {
        player: "Hey, how are you feeling?",
        pet: "I feel better when we talk.",
        social: 3,
        fun: 1,
      },
    ];
  }

  return out;
}

function ensureActiveCategory() {
  const cats = Object.keys(appState.dialogueDraft || {});
  if (!cats.length) {
    appState.activeCategory = null;
    return;
  }
  if (!appState.activeCategory || !appState.dialogueDraft[appState.activeCategory]) {
    appState.activeCategory = cats[0];
  }
}

function setStep(index) {
  const size = STEP_ORDER.length;
  const normalized = ((index % size) + size) % size;
  appState.stepIndex = normalized;

  const key = STEP_ORDER[normalized];
  els.stepTitle.textContent = STEP_TITLES[key];
  els.stepCaption.textContent = `Step ${normalized + 1} of ${size}`;

  const stepMap = {
    background: els.stepBackground,
    sprites: els.stepSprites,
    dialogue: els.stepDialogue,
  };
  for (const [k, node] of Object.entries(stepMap)) {
    const active = k === key;
    node.hidden = !active;
    node.classList.toggle("is-active", active);
  }

  if (key === "background") {
    els.stepSaveNextBtn.textContent = "Save & Next: Sprites";
  } else if (key === "sprites") {
    els.stepSaveNextBtn.textContent = "Save & Next: Dialogue";
  } else {
    els.stepSaveNextBtn.textContent = "Save Dialogue & Back To Background";
  }
}

function renderBackgroundCards() {
  const rooms = appState.meta?.meta?.rooms || [];
  els.bgGrid.innerHTML = "";

  rooms.forEach((room) => {
    const info = effectiveBackground(room);
    const badgeClass = info?.source || "asset";

    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="card-row">
        <h4>${room}</h4>
        <span class="badge ${badgeClass}">${info?.source || "asset"}</span>
      </div>
      <p class="preview-meta">In use: ${info?.file_name || "none"}</p>
      <div class="card-row">
        <input type="file" accept=".png,.jpg,.jpeg,.webp" id="bg-file-${room}" />
      </div>
      <div class="card-row">
        <button class="btn" id="bg-upload-${room}">Stage Upload</button>
        <button class="btn btn-danger" id="bg-clear-${room}">Clear Override</button>
      </div>
    `;

    els.bgGrid.appendChild(card);

    card.querySelector(`#bg-upload-${room}`).addEventListener("click", async () => {
      const input = card.querySelector(`#bg-file-${room}`);
      if (!input.files?.length) {
        setStatus(`Choose a file for room '${room}' first.`, true);
        return;
      }
      try {
        const fd = new FormData();
        fd.append("room", room);
        fd.append("file", input.files[0]);
        await apiPostForm("/api/draft/background", fd);
        setStatus(`Staged background for '${room}'.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });

    card.querySelector(`#bg-clear-${room}`).addEventListener("click", async () => {
      try {
        const fd = new FormData();
        fd.append("room", room);
        fd.append("clear", "1");
        await apiPostForm("/api/draft/background", fd);
        setStatus(`Background override for '${room}' marked for removal.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });
}

function renderAnimCards() {
  const groups = appState.meta?.meta?.anim_groups || [];
  els.animGrid.innerHTML = "";

  groups.forEach((group) => {
    const info = effectiveAnim(group);
    const badgeClass = info?.source || "asset";

    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="card-row">
        <h4>${group}</h4>
        <span class="badge ${badgeClass}">${info?.source || "asset"}</span>
      </div>
      <p class="preview-meta">In use: ${formatAnimFiles(info)}</p>
      <div class="card-row">
        <input type="file" multiple accept=".png" id="anim-file-${group}" />
      </div>
      <div class="card-row">
        <button class="btn" id="anim-upload-${group}">Stage Frames</button>
        <button class="btn btn-danger" id="anim-clear-${group}">Clear Override</button>
      </div>
      <p class="preview-meta">Frame count: ${info?.count || 0}</p>
    `;

    els.animGrid.appendChild(card);

    card.querySelector(`#anim-upload-${group}`).addEventListener("click", async () => {
      const input = card.querySelector(`#anim-file-${group}`);
      if (!input.files?.length) {
        setStatus(`Choose frame files for '${group}' first.`, true);
        return;
      }
      try {
        const fd = new FormData();
        fd.append("mode", "anim");
        fd.append("group", group);
        for (const file of input.files) {
          fd.append("files", file);
        }
        await apiPostForm("/api/draft/sprite", fd);
        setStatus(`Staged sprite frames for '${group}'.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });

    card.querySelector(`#anim-clear-${group}`).addEventListener("click", async () => {
      try {
        const fd = new FormData();
        fd.append("mode", "anim");
        fd.append("group", group);
        fd.append("clear", "1");
        await apiPostForm("/api/draft/sprite", fd);
        setStatus(`Animation override for '${group}' marked for removal.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });
}

function renderSingleCards() {
  const singles = appState.meta?.meta?.single_sprites || [];
  els.singleGrid.innerHTML = "";

  singles.forEach((name) => {
    const info = effectiveSingle(name);
    const badgeClass = info?.source || "asset";
    const idSafe = name.replace(/[^a-z0-9]/gi, "_");

    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="card-row">
        <h4>${name}</h4>
        <span class="badge ${badgeClass}">${info?.source || "asset"}</span>
      </div>
      <p class="preview-meta">In use: ${info?.file_name || "none"}</p>
      <div class="card-row">
        <input type="file" accept=".png" id="single-file-${idSafe}" />
      </div>
      <div class="card-row">
        <button class="btn" id="single-upload-${idSafe}">Stage Upload</button>
        <button class="btn btn-danger" id="single-clear-${idSafe}">Clear Override</button>
      </div>
    `;

    els.singleGrid.appendChild(card);

    card.querySelector(`#single-upload-${idSafe}`).addEventListener("click", async () => {
      const input = card.querySelector(`#single-file-${idSafe}`);
      if (!input.files?.length) {
        setStatus(`Choose a file for '${name}' first.`, true);
        return;
      }
      try {
        const fd = new FormData();
        fd.append("mode", "single");
        fd.append("name", name);
        fd.append("file", input.files[0]);
        await apiPostForm("/api/draft/sprite", fd);
        setStatus(`Staged single sprite '${name}'.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });

    card.querySelector(`#single-clear-${idSafe}`).addEventListener("click", async () => {
      try {
        const fd = new FormData();
        fd.append("mode", "single");
        fd.append("name", name);
        fd.append("clear", "1");
        await apiPostForm("/api/draft/sprite", fd);
        setStatus(`Single sprite override '${name}' marked for removal.`);
        await refreshCurrent();
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });
}

function renderCategoryList() {
  ensureActiveCategory();
  const cats = Object.keys(appState.dialogueDraft || {});
  els.categoryList.innerHTML = "";

  cats.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = `category-btn ${cat === appState.activeCategory ? "active" : ""}`;
    btn.textContent = `${cat} (${(appState.dialogueDraft[cat] || []).length})`;
    btn.addEventListener("click", () => {
      appState.activeCategory = cat;
      renderDialogueEditor();
      updatePreview();
    });
    els.categoryList.appendChild(btn);
  });
}

function renderDialogueRows() {
  ensureActiveCategory();
  const cat = appState.activeCategory;
  const rows = appState.dialogueDraft[cat] || [];

  els.activeCategoryLabel.textContent = cat || "Category";
  els.dialogueRows.innerHTML = "";

  rows.forEach((row, idx) => {
    const wrapper = document.createElement("article");
    wrapper.className = "dialogue-row";
    wrapper.innerHTML = `
      <div class="card-row">
        <strong>Row ${idx + 1}</strong>
        <button class="btn btn-danger" data-remove-row="${idx}">Delete</button>
      </div>
      <label>
        Player Text
        <textarea data-field="player" data-idx="${idx}">${row.player || ""}</textarea>
      </label>
      <label>
        Pet Text
        <textarea data-field="pet" data-idx="${idx}">${row.pet || ""}</textarea>
      </label>
      <div class="dialogue-grid">
        <label>
          Social (optional)
          <input data-field="social" data-idx="${idx}" value="${row.social ?? ""}" />
        </label>
        <label>
          Fun (optional)
          <input data-field="fun" data-idx="${idx}" value="${row.fun ?? ""}" />
        </label>
      </div>
    `;

    wrapper.querySelector("[data-remove-row]").addEventListener("click", () => {
      rows.splice(idx, 1);
      renderDialogueEditor();
      updatePreview();
    });

    wrapper.querySelectorAll("textarea, input").forEach((field) => {
      field.addEventListener("input", () => {
        const targetIdx = Number(field.dataset.idx);
        const key = field.dataset.field;
        if (!rows[targetIdx]) return;
        rows[targetIdx][key] = field.value;
        updatePreview();
      });
    });

    els.dialogueRows.appendChild(wrapper);
  });
}

function renderDialogueEditor() {
  renderCategoryList();
  renderDialogueRows();
}

function normalizeDialogueForSubmit() {
  const out = {};
  for (const [cat, rows] of Object.entries(appState.dialogueDraft || {})) {
    const cleanCat = String(cat || "").trim();
    if (!cleanCat) continue;

    out[cleanCat] = (rows || []).map((row) => {
      const item = {
        player: String(row.player || "").trim(),
        pet: String(row.pet || "").trim(),
      };

      const socialRaw = String(row.social ?? "").trim();
      const funRaw = String(row.fun ?? "").trim();
      if (socialRaw !== "") item.social = Number(socialRaw);
      if (funRaw !== "") item.fun = Number(funRaw);
      return item;
    });
  }
  return out;
}

async function stageDialogueDraft() {
  const payload = { dialogue: normalizeDialogueForSubmit() };
  await apiPostJson("/api/draft/dialogue", payload);
}

function bindDialogueButtons() {
  els.addCategoryBtn.addEventListener("click", () => {
    const name = prompt("Category name:", "new_category");
    if (!name) return;
    const key = name.trim();
    if (!key) return;
    if (appState.dialogueDraft[key]) {
      setStatus(`Category '${key}' already exists.`, true);
      return;
    }
    appState.dialogueDraft[key] = [];
    appState.activeCategory = key;
    renderDialogueEditor();
    updatePreview();
  });

  els.renameCategoryBtn.addEventListener("click", () => {
    const oldKey = appState.activeCategory;
    if (!oldKey) return;
    const next = prompt("Rename category:", oldKey);
    if (!next) return;
    const nextKey = next.trim();
    if (!nextKey || nextKey === oldKey) return;
    if (appState.dialogueDraft[nextKey]) {
      setStatus(`Category '${nextKey}' already exists.`, true);
      return;
    }
    appState.dialogueDraft[nextKey] = appState.dialogueDraft[oldKey] || [];
    delete appState.dialogueDraft[oldKey];
    appState.activeCategory = nextKey;
    renderDialogueEditor();
    updatePreview();
  });

  els.deleteCategoryBtn.addEventListener("click", () => {
    const key = appState.activeCategory;
    if (!key) return;
    if (!confirm(`Delete category '${key}' from draft?`)) return;
    delete appState.dialogueDraft[key];
    ensureActiveCategory();
    renderDialogueEditor();
    updatePreview();
  });

  els.addRowBtn.addEventListener("click", () => {
    const key = appState.activeCategory;
    if (!key) return;
    appState.dialogueDraft[key].push({ player: "", pet: "", social: "", fun: "" });
    renderDialogueEditor();
    updatePreview();
  });

  els.saveDialogueBtn.addEventListener("click", async () => {
    try {
      await stageDialogueDraft();
      setStatus("Staged dialogue draft.");
      await refreshCurrent();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  els.clearDialogueBtn.addEventListener("click", async () => {
    if (!confirm("Clear dialogue override and fall back to bundled dialogue?")) return;
    try {
      await apiPostJson("/api/draft/dialogue", { clear: true });
      setStatus("Dialogue override marked for removal.");
      await refreshCurrent();
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

function bindStepButtons() {
  els.stepPrevBtn.addEventListener("click", () => {
    setStep(appState.stepIndex - 1);
  });

  els.stepNextBtn.addEventListener("click", () => {
    setStep(appState.stepIndex + 1);
  });

  els.stepSaveNextBtn.addEventListener("click", async () => {
    const stepKey = STEP_ORDER[appState.stepIndex];
    try {
      if (stepKey === "dialogue") {
        await stageDialogueDraft();
        setStatus("Dialogue staged. Returning to Background.");
        await refreshCurrent();
        setStep(0);
      } else {
        setStep(appState.stepIndex + 1);
      }
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

function bindActionBar() {
  els.validateBtn.addEventListener("click", async () => {
    try {
      const data = await apiPostJson("/api/validate", {});
      const errs = data.errors || [];
      const warns = data.warnings || [];
      if (errs.length) {
        setStatus(`Validation failed: ${errs[0]}`, true);
      } else if (warns.length) {
        setStatus(`Validation warning: ${warns[0]}`);
      } else {
        setStatus("Validation passed.");
      }
      await refreshCurrent();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  els.applyBtn.addEventListener("click", async () => {
    if (!confirm("Apply staged draft changes and create a snapshot?")) return;
    try {
      const data = await apiPostJson("/api/apply", {});
      setStatus(`Applied successfully. Snapshot: ${data.snapshot_id}`);
      await refreshAll();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  els.discardBtn.addEventListener("click", async () => {
    if (!confirm("Discard all draft changes?")) return;
    try {
      await apiPostJson("/api/draft/discard", {});
      setStatus("Draft discarded.");
      await refreshAll();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  els.downloadSnapshotBtn.addEventListener("click", () => {
    const sid = els.snapshotSelect.value;
    if (!sid) {
      setStatus("Choose a snapshot to download.", true);
      return;
    }
    const url = `/api/snapshot_download?snapshot_id=${encodeURIComponent(sid)}`;
    window.location.href = url;
    setStatus(`Downloading snapshot '${sid}'...`);
  });

  els.restoreBtn.addEventListener("click", async () => {
    const sid = els.snapshotSelect.value;
    if (!sid) {
      setStatus("Choose a snapshot to restore.", true);
      return;
    }
    if (!confirm(`Restore snapshot '${sid}'?`)) return;
    try {
      await apiPostJson("/api/restore", { snapshot_id: sid });
      setStatus(`Restored snapshot '${sid}'.`);
      await refreshAll();
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

function initPreviewSelectors() {
  const rooms = appState.meta?.meta?.rooms || [];
  const groups = appState.meta?.meta?.anim_groups || [];

  els.previewRoom.innerHTML = rooms.map((room) => `<option value="${room}">${room}</option>`).join("");
  els.previewGroup.innerHTML = groups.map((group) => `<option value="${group}">${group}</option>`).join("");

  if (!rooms.includes(appState.preview.room) && rooms.length) {
    appState.preview.room = rooms[0];
  }
  if (!groups.includes(appState.preview.group) && groups.length) {
    appState.preview.group = groups[0];
  }

  els.previewRoom.value = appState.preview.room;
  els.previewGroup.value = appState.preview.group;

  els.previewRoom.onchange = () => {
    appState.preview.room = els.previewRoom.value;
    updatePreview();
  };
  els.previewGroup.onchange = () => {
    appState.preview.group = els.previewGroup.value;
    updatePreview();
  };
  els.previewFrame.oninput = () => {
    appState.preview.frame = Number(els.previewFrame.value || 0);
    updatePreview();
  };
}

async function loadImage(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function previewSampleText() {
  ensureActiveCategory();
  const cat = appState.activeCategory;
  if (!cat || !appState.dialogueDraft[cat]?.length) return "You: ...\nHim: ...";
  const row = appState.dialogueDraft[cat][0] || {};
  return `You: ${String(row.player || "...").trim()}\nHim: ${String(row.pet || "...").trim()}`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

async function updatePreview() {
  const ctx = els.previewCanvas.getContext("2d");
  const room = appState.preview.room;
  const group = appState.preview.group;
  const frame = Number(appState.preview.frame || 0);
  const nonce = Date.now();

  const roomUrl = `/api/preview_asset?kind=room&room=${encodeURIComponent(room)}&source=effective&_=${nonce}`;
  const spriteUrl = `/api/preview_asset?kind=sprite_anim&group=${encodeURIComponent(group)}&source=effective&frame=${frame}&_=${nonce}`;

  const [roomImg, spriteImg] = await Promise.all([loadImage(roomUrl), loadImage(spriteUrl)]);

  ctx.clearRect(0, 0, 240, 240);
  ctx.fillStyle = "#05090d";
  ctx.fillRect(0, 0, 240, 240);

  if (roomImg) {
    ctx.drawImage(roomImg, 0, 0, 240, 240);
  }

  if (spriteImg) {
    const sw = spriteImg.width;
    const sh = spriteImg.height;
    const px = Math.round((240 - sw) / 2);
    const py = Math.round(192 - sh);
    ctx.drawImage(spriteImg, px, py);
  }

  const bubble = previewSampleText();
  ctx.fillStyle = "rgba(8, 14, 20, 0.86)";
  roundRect(ctx, 10, 10, 220, 64, 10);
  ctx.fill();
  ctx.strokeStyle = "rgba(160, 228, 214, 0.6)";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = "#d8f9f1";
  ctx.font = "11px 'Avenir Next', 'Trebuchet MS', sans-serif";
  const lines = bubble.split("\n");
  lines.slice(0, 2).forEach((line, i) => {
    ctx.fillText(line.slice(0, 40), 16, 31 + i * 18);
  });

  const roomSource = effectiveBackground(room)?.source || "asset";
  const groupSource = effectiveAnim(group)?.source || "asset";
  els.previewMeta.textContent = `Room source: ${roomSource} | Sprite source: ${groupSource} | Frame: ${frame}`;
}

async function refreshSnapshots() {
  const data = await apiGet("/api/snapshots");
  const list = data.snapshots || [];
  els.snapshotSelect.innerHTML = [
    `<option value="">Select snapshot</option>`,
    ...list.map((item) => {
      const extra = item.created_at ? ` ${item.created_at}` : "";
      return `<option value="${item.id}">${item.id}${extra}</option>`;
    }),
  ].join("");
}

async function refreshCurrent() {
  appState.current = await apiGet("/api/current");

  const draftHasChanges = Boolean(appState.current?.draft?.has_changes);
  els.applyBtn.disabled = !draftHasChanges;

  renderBackgroundCards();
  renderAnimCards();
  renderSingleCards();

  const templateData = appState.current?.dialogue?.template || {};
  const effectiveData = appState.current?.dialogue?.data || {};
  appState.dialogueDraft = buildDialogueDraft(templateData, effectiveData);
  ensureActiveCategory();
  renderDialogueEditor();

  await updatePreview();
}

async function refreshAll() {
  await refreshCurrent();
  await refreshSnapshots();
}

async function initialize() {
  try {
    appState.meta = await apiGet("/api/meta");
    initPreviewSelectors();
    bindStepButtons();
    bindDialogueButtons();
    bindActionBar();
    await refreshAll();
    setStep(0);
    setStatus("Customizer ready.");
  } catch (err) {
    setStatus(err.message, true);
  }
}

els.startBtn.addEventListener("click", () => {
  document.getElementById("editor-root").scrollIntoView({ behavior: "smooth", block: "start" });
});

initialize();
