const ui = {
  catalog: document.querySelector("#catalog"),
  emptyState: document.querySelector("#emptyState"),
  search: document.querySelector("#searchInput"),
  filters: document.querySelector("#categoryFilters"),
  resultCount: document.querySelector("#resultCount"),
  title: document.querySelector("#catalogTitle"),
  changeCount: document.querySelector("#changeCount"),
  previewButton: document.querySelector("#previewButton"),
  saveButton: document.querySelector("#saveButton"),
  drawerSaveButton: document.querySelector("#drawerSaveButton"),
  drawer: document.querySelector("#previewDrawer"),
  backdrop: document.querySelector("#drawerBackdrop"),
  closePreview: document.querySelector("#closePreview"),
  previewCode: document.querySelector("#previewCode code"),
  diffTab: document.querySelector("#diffTab"),
  sourceTab: document.querySelector("#sourceTab"),
  toast: document.querySelector("#toast"),
  systemTarget: document.querySelector("#systemTarget"),
  helperTarget: document.querySelector("#helperTarget"),
  adoptionBanner: document.querySelector("#adoptionBanner"),
  adoptionLabel: document.querySelector("#adoptionLabel"),
  adoptionTitle: document.querySelector("#adoptionTitle"),
  adoptionDetail: document.querySelector("#adoptionDetail"),
  adoptionPlanButton: document.querySelector("#adoptionPlanButton"),
  planBackdrop: document.querySelector("#planBackdrop"),
  planDrawer: document.querySelector("#planDrawer"),
  closePlan: document.querySelector("#closePlan"),
  closePlanFooter: document.querySelector("#closePlanFooter"),
  planStatus: document.querySelector("#planStatus"),
  planFileCount: document.querySelector("#planFileCount"),
  planCode: document.querySelector("#planCode"),
  candidateValidation: document.querySelector("#candidateValidation"),
  candidateValidationIcon: document.querySelector("#candidateValidationIcon"),
  candidateValidationTitle: document.querySelector("#candidateValidationTitle"),
  candidateValidationDetail: document.querySelector("#candidateValidationDetail"),
  candidateValidationLog: document.querySelector("#candidateValidationLog"),
  validateCandidateButton: document.querySelector("#validateCandidateButton"),
  validateHelperButton: document.querySelector("#validateHelperButton"),
  helperAvailability: document.querySelector("#helperAvailability"),
  buildPreview: document.querySelector("#buildPreview"),
  buildPreviewIcon: document.querySelector("#buildPreviewIcon"),
  buildPreviewTitle: document.querySelector("#buildPreviewTitle"),
  buildPreviewDetail: document.querySelector("#buildPreviewDetail"),
  buildPreviewLog: document.querySelector("#buildPreviewLog"),
  startBuildPreviewButton: document.querySelector("#startBuildPreviewButton"),
  cancelBuildPreviewButton: document.querySelector("#cancelBuildPreviewButton"),
  activationPreview: document.querySelector("#activationPreview"),
  activationPreviewIcon: document.querySelector("#activationPreviewIcon"),
  activationPreviewTitle: document.querySelector("#activationPreviewTitle"),
  activationPreviewDetail: document.querySelector("#activationPreviewDetail"),
  closureDiffLog: document.querySelector("#closureDiffLog"),
  activationPreviewLog: document.querySelector("#activationPreviewLog"),
  runActivationPreviewButton: document.querySelector("#runActivationPreviewButton"),
  runTestActivationButton: document.querySelector("#runTestActivationButton"),
  recoverTestActivationButton: document.querySelector("#recoverTestActivationButton"),
  testActivationLog: document.querySelector("#testActivationLog"),
};

const model = {
  token: "",
  catalog: [],
  state: { schemaVersion: 1, packages: [], options: {} },
  savedPackages: new Set(),
  selected: new Set(),
  category: "Усі",
  preview: { diff: "", generated: "" },
  previewMode: "diff",
  adoption: null,
  candidateValidation: null,
  helper: null,
  buildPreview: { jobId: null, status: "idle", nextCursor: 0, events: [] },
  buildLog: [],
  activationPreview: null,
  testActivation: null,
};

const activeBuildStatuses = new Set(["queued", "preparing", "running", "analyzing", "cancelling", "cleaning"]);

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (model.token) headers["X-NCM-Token"] = model.token;
  const response = await fetch(path, { ...options, headers });
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function currentState() {
  return {
    schemaVersion: 1,
    packages: [...model.selected].sort(),
    options: model.state.options || {},
  };
}

function dirtyCount() {
  const all = new Set([...model.savedPackages, ...model.selected]);
  let count = 0;
  for (const item of all) {
    if (model.savedPackages.has(item) !== model.selected.has(item)) count += 1;
  }
  return count;
}

function updateChangeState() {
  const count = dirtyCount();
  const lastTwo = count % 100;
  const last = count % 10;
  const label = lastTwo >= 11 && lastTwo <= 14
    ? "змін"
    : last === 1 ? "зміна" : last >= 2 && last <= 4 ? "зміни" : "змін";
  ui.changeCount.textContent = count ? `${count} ${label}` : "Немає змін";
  ui.changeCount.classList.toggle("dirty", count > 0);
  ui.saveButton.disabled = count === 0;
  ui.drawerSaveButton.disabled = count === 0;
}

function buildFilters() {
  const categories = ["Усі", ...new Set(model.catalog.map((app) => app.category))];
  ui.filters.replaceChildren(...categories.map((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter${category === model.category ? " active" : ""}`;
    button.textContent = category;
    button.addEventListener("click", () => {
      model.category = category;
      buildFilters();
      renderCatalog();
    });
    return button;
  }));
}

function matches(app) {
  const query = ui.search.value.trim().toLocaleLowerCase("uk");
  const categoryMatch = model.category === "Усі" || app.category === model.category;
  const text = `${app.name} ${app.attribute} ${app.description}`.toLocaleLowerCase("uk");
  return categoryMatch && (!query || text.includes(query));
}

function appCard(app) {
  const card = document.createElement("article");
  const selected = model.selected.has(app.attribute);
  card.className = `app-card${selected ? " selected" : ""}`;

  const symbol = document.createElement("div");
  symbol.className = "app-symbol";
  symbol.textContent = app.symbol;

  const copy = document.createElement("div");
  copy.className = "app-copy";
  const name = document.createElement("h3");
  name.textContent = app.name;
  const packageName = document.createElement("span");
  packageName.className = "package-name";
  packageName.textContent = `pkgs.${app.attribute}`;
  const description = document.createElement("p");
  description.textContent = app.description;
  copy.append(name, packageName, description);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "app-toggle";
  toggle.textContent = "✓";
  toggle.setAttribute("aria-label", `${selected ? "Вилучити" : "Додати"} ${app.name}`);
  toggle.setAttribute("aria-pressed", String(selected));
  toggle.addEventListener("click", () => {
    if (model.selected.has(app.attribute)) model.selected.delete(app.attribute);
    else model.selected.add(app.attribute);
    renderCatalog();
    updateChangeState();
  });

  const category = document.createElement("div");
  category.className = "category-badge";
  category.textContent = app.category;
  card.append(symbol, copy, toggle, category);
  return card;
}

function renderCatalog() {
  const visible = model.catalog.filter(matches);
  ui.catalog.replaceChildren(...visible.map(appCard));
  ui.emptyState.hidden = visible.length > 0;
  ui.resultCount.textContent = `${visible.length} із ${model.catalog.length}`;
  ui.title.textContent = model.category === "Усі" ? "Рекомендовані програми" : model.category;
}

function renderPreview() {
  ui.diffTab.classList.toggle("active", model.previewMode === "diff");
  ui.sourceTab.classList.toggle("active", model.previewMode === "source");
  ui.diffTab.setAttribute("aria-selected", String(model.previewMode === "diff"));
  ui.sourceTab.setAttribute("aria-selected", String(model.previewMode === "source"));
  const content = model.previewMode === "diff"
    ? (model.preview.diff || "Змін немає.")
    : model.preview.generated;
  ui.previewCode.textContent = content;
}

function renderSystemTarget(system) {
  const platform = system.platform;
  const managed = system.managedModule;
  const state = system.state;
  const title = ui.systemTarget.querySelector("strong");
  const detail = ui.systemTarget.querySelector("small");
  ui.systemTarget.classList.remove("connected", "warning");

  if (!platform.isNixOS) {
    title.textContent = "Режим розробки";
    detail.textContent = "цільову NixOS не виявлено";
    return;
  }

  title.textContent = `${platform.name}${platform.release ? ` ${platform.release}` : ""}`;
  const mode = system.configuration.mode === "flake" ? "flake" :
    system.configuration.mode === "channels" ? "channels" : "без конфігурації";
  if (managed.status === "connected" && state.status === "current") {
    ui.systemTarget.classList.add("connected");
    detail.textContent = `${platform.hostname} · ${mode} · підключено`;
  } else if (managed.status === "connected") {
    ui.systemTarget.classList.add("warning");
    detail.textContent = `${platform.hostname} · ${mode} · потрібна міграція`;
  } else {
    ui.systemTarget.classList.add("warning");
    detail.textContent = `${platform.hostname} · ${mode} · не підключено`;
  }
}

function fileChangeLabel(count) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} файлова зміна`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} файлові зміни`;
  }
  return `${count} файлових змін`;
}

function renderAdoptionPlan(plan) {
  model.adoption = plan;
  if (plan.status === "no-changes") {
    ui.adoptionBanner.hidden = true;
    return;
  }
  ui.adoptionBanner.hidden = false;
  const descriptions = {
    "migration-ready": ["Міграція legacy-стану", "План безпечної міграції готовий"],
    ready: ["Підключення конфігурації", "План підключення готовий"],
    manual: ["Потрібен ручний перегляд", "Автоматичну зміну обмежено"],
    blocked: ["План заблоковано", "Потрібно усунути проблему зі станом"],
  };
  const [label, title] = descriptions[plan.status] || ["План конфігурації", plan.status];
  ui.adoptionLabel.textContent = label;
  ui.adoptionTitle.textContent = title;
  const warning = plan.warnings[0];
  ui.adoptionDetail.textContent = warning || `${fileChangeLabel(plan.changes.length)} без застосування`;
}

function renderHelperStatus(helper) {
  model.helper = helper;
  const available = helper.available === true;
  const title = ui.helperTarget.querySelector("strong");
  const detail = ui.helperTarget.querySelector("small");
  ui.helperTarget.classList.toggle("connected", available);
  ui.helperTarget.classList.toggle("warning", !available);
  title.textContent = available
    ? (helper.testActivationEnabled ? "Test helper підключено" : "Read-only helper підключено")
    : "Системний helper недоступний";
  detail.textContent = available
    ? `${helper.targetId} · без apply/switch${helper.testActivationEnabled ? " · test з auto-recovery" : " · test вимкнено"}${helper.dryActivatePreviewEnabled ? " · dry-preview" : ""}`
    : (helper.reason || "Unix socket не відповідає");

  const planReady = model.adoption?.safeToApply === true && model.adoption.changes.length > 0;
  ui.validateHelperButton.disabled = !available || !planReady;
  ui.helperAvailability.classList.toggle("available", available);
  ui.helperAvailability.classList.toggle("unavailable", !available);
  ui.helperAvailability.querySelector("small").textContent = available
    ? `Live target «${helper.targetId}»: перевірка${helper.dryActivatePreviewEnabled ? " та авторизований dry-preview" : ""}${helper.testActivationEnabled ? "; test лише з одноразовим receipt та auto-recovery" : "; test вимкнено"}`
    : (helper.reason || "Системний helper не налаштовано");
  updateActivationPreviewControls();
}

function openAdoptionPlan() {
  const plan = model.adoption;
  if (!plan) return;
  ui.planStatus.textContent = plan.status;
  ui.planFileCount.textContent = fileChangeLabel(plan.changes.length);
  const warningText = plan.warnings.length
    ? `ПОПЕРЕДЖЕННЯ\n${plan.warnings.map((warning) => `• ${warning}`).join("\n")}\n\n`
    : "";
  ui.planCode.textContent = warningText + (plan.combinedDiff || "Змін файлів не запропоновано.");
  ui.planBackdrop.hidden = false;
  ui.planDrawer.inert = false;
  ui.planDrawer.classList.add("open");
  ui.planDrawer.setAttribute("aria-hidden", "false");
  ui.closePlan.focus();
}

function validationLog(result) {
  const lines = [];
  if (result.source === "system-helper") {
    lines.push("SYSTEM HELPER · LIVE READ-ONLY · APPLY DISABLED");
    lines.push(`Receipt issued: ${result.validationReceiptIssued ? "YES (blocked)" : "no"}`);
    lines.push("");
  }
  for (const check of result.checks) {
    lines.push(`${check.status.toUpperCase()} · ${check.name} · ${check.durationMs} ms`);
    if (Array.isArray(check.command) && check.command.length) {
      lines.push(`$ ${check.command.join(" ")}`);
    }
    if (check.stdout) lines.push(check.stdout.trim());
    if (check.stderr) lines.push(check.stderr.trim());
    lines.push("");
  }
  for (const warning of result.warnings) lines.push(`ПОПЕРЕДЖЕННЯ · ${warning}`);
  if (result.error?.message) lines.push(`HELPER · ${result.error.message}`);
  return lines.join("\n").trim();
}

function renderCandidateValidation(result) {
  model.candidateValidation = result;
  ui.candidateValidation.classList.remove("running", "passed", "failed");
  const passed = result.status === "passed";
  ui.candidateValidation.classList.add(passed ? "passed" : "failed");
  ui.candidateValidationIcon.textContent = passed ? "✓" : "!";
  const titles = {
    passed: "Кандидат пройшов перевірку",
    failed: "Nix виявив помилку",
    unavailable: "Nix недоступний",
    blocked: "Перевірку заблоковано",
  };
  ui.candidateValidationTitle.textContent = titles[result.status] || `Результат: ${result.status}`;
  const helperResult = result.source === "system-helper";
  ui.candidateValidationDetail.textContent = passed
    ? (helperResult
      ? "Системний helper перевірив точний live-план у тимчасовій копії. Він не видав receipt і не запускав apply, build або activation."
      : "Parse та evaluation успішні; тимчасову копію видалено. Build і activation не запускалися.")
    : "Цільову конфігурацію не змінено. Перегляньте технічний результат нижче.";
  const log = validationLog(result);
  ui.candidateValidationLog.textContent = log;
  ui.candidateValidationLog.hidden = !log;
  ui.validateCandidateButton.textContent = "Повторити локально";
  ui.validateCandidateButton.disabled = false;
  ui.validateHelperButton.textContent = helperResult
    ? "Повторити через helper"
    : "Через системний helper";
  renderHelperStatus(model.helper || { available: false, reason: "Системний helper не налаштовано" });
  updateBuildPreviewControls();
}

async function runCandidateValidation({ helper = false } = {}) {
  const activeButton = helper ? ui.validateHelperButton : ui.validateCandidateButton;
  ui.validateCandidateButton.disabled = true;
  ui.validateHelperButton.disabled = true;
  activeButton.textContent = "Перевірка…";
  ui.candidateValidation.classList.remove("passed", "failed");
  ui.candidateValidation.classList.add("running");
  ui.candidateValidationIcon.textContent = "◇";
  ui.candidateValidationTitle.textContent = helper
    ? "Системний helper перевіряє live-план"
    : "Nix перевіряє тимчасового кандидата";
  ui.candidateValidationDetail.textContent = helper
    ? "Helper повторно будує точний план і виконує evaluation без receipt, Polkit, apply або activation."
    : "Виконується parse та evaluation без build, switch або запису в цільову конфігурацію.";
  ui.candidateValidationLog.hidden = true;
  model.candidateValidation = null;
  updateBuildPreviewControls();
  try {
    renderCandidateValidation(await api(
      helper ? "/api/helper/validate-adoption" : "/api/validate-adoption",
      { method: "POST" },
    ));
  } catch (error) {
    ui.candidateValidation.classList.remove("running");
    ui.candidateValidation.classList.add("failed");
    ui.candidateValidationIcon.textContent = "!";
    ui.candidateValidationTitle.textContent = "Перевірка не завершилася";
    ui.candidateValidationDetail.textContent = error.message;
    activeButton.textContent = "Спробувати знову";
    ui.validateCandidateButton.disabled = false;
    renderHelperStatus(model.helper || { available: false, reason: "Системний helper не налаштовано" });
  }
}

function validateCandidate() { return runCandidateValidation(); }
function validateWithHelper() { return runCandidateValidation({ helper: true }); }

function updateBuildPreviewControls() {
  const active = activeBuildStatuses.has(model.buildPreview?.status);
  const validated = model.candidateValidation?.status === "passed";
  const planReady = model.adoption?.safeToApply === true;
  ui.startBuildPreviewButton.disabled = active || !validated || !planReady;
  ui.cancelBuildPreviewButton.hidden = !active;
  ui.cancelBuildPreviewButton.disabled = model.buildPreview?.status === "cancelling";
  updateActivationPreviewControls();
}

function updateActivationPreviewControls() {
  const ready = model.buildPreview?.activationPreviewReady === true;
  const helperReady = model.helper?.dryActivatePreviewEnabled === true;
  ui.runActivationPreviewButton.disabled = !ready || !helperReady;
  const prepared = model.activationPreview?.testActivationPrepared === true
    && typeof model.activationPreview?.testReceipt === "string";
  const testReady = model.helper?.testActivationEnabled === true && prepared;
  const active = model.testActivation?.status === "active";
  ui.runTestActivationButton.disabled = !testReady || active;
  ui.runTestActivationButton.hidden = active;
  ui.recoverTestActivationButton.hidden = !active;
}

function renderBuildPreview(result) {
  const previousJobId = model.buildPreview?.jobId;
  const previousCursor = result.jobId === previousJobId
    ? (model.buildPreview?.nextCursor || 0) : 0;
  if (result.jobId !== previousJobId) model.buildLog = [];
  if (result.logsTruncated && !model.buildLog.length) {
    model.buildLog.push("… попередні рядки журналу вже недоступні …");
  }
  for (const event of result.events || []) {
    if ((event.sequence || 0) <= previousCursor) continue;
    const prefix = event.stream === "stderr" ? "ERR · "
      : event.stream === "command" ? "" : event.stream === "stdout" ? "OUT · "
        : event.stream === "impact" ? "DIFF · " : "NCM · ";
    model.buildLog.push(prefix + event.message);
  }
  model.buildPreview = { ...result, events: [] };
  if (model.buildLog.length > 2000) model.buildLog = model.buildLog.slice(-2000);

  const status = result.status || "idle";
  const active = activeBuildStatuses.has(status);
  ui.buildPreview.classList.remove("running", "passed", "failed", "cancelled");
  if (active) ui.buildPreview.classList.add("running");
  else if (status === "passed") ui.buildPreview.classList.add("passed");
  else if (status === "cancelled") ui.buildPreview.classList.add("cancelled");
  else if (status !== "idle") ui.buildPreview.classList.add("failed");

  const titles = {
    idle: "Build-preview ще не запущено",
    queued: "Build-preview у черзі",
    preparing: "Готується ізольований кандидат",
    running: "Nix збирає кандидата",
    analyzing: "Порівнюються системні closure",
    cancelling: "Build зупиняється",
    cleaning: "Видаляється тимчасова копія",
    passed: "Кандидат успішно зібрано",
    failed: "Build завершився помилкою",
    cancelled: "Build скасовано",
    blocked: "Build заблоковано",
    unavailable: "Nix build недоступний",
  };
  ui.buildPreviewTitle.textContent = titles[status] || `Build: ${status}`;
  if (status === "passed") {
    const outputs = result.outputPaths?.length || 0;
    ui.buildPreviewDetail.textContent = `Готово: ${outputs} store path. Цільову конфігурацію та активне покоління не змінено.`;
  } else if (status === "cancelled") {
    ui.buildPreviewDetail.textContent = "Процесну групу Nix зупинено; тимчасову копію видалено. Уже готові об’єкти Nix store можуть залишитися для повторного використання.";
  } else if (result.error?.message) {
    ui.buildPreviewDetail.textContent = `${result.error.message}. Цільову конфігурацію не змінено.`;
  } else if (active) {
    ui.buildPreviewDetail.textContent = "Журнал оновлюється під час роботи. Дозволено лише непривілейований запис до Nix store; activation відсутня.";
  } else {
    ui.buildPreviewDetail.textContent = "Після перевірки можна зібрати кандидата непривілейовано. Запис дозволено лише до Nix store; test, switch та activation відсутні.";
  }
  ui.buildPreviewIcon.textContent = status === "passed" ? "✓"
    : status === "cancelled" ? "■" : active ? "◇" : status === "idle" ? "▱" : "!";
  ui.buildPreviewLog.textContent = model.buildLog.join("\n");
  ui.buildPreviewLog.hidden = model.buildLog.length === 0;
  ui.closureDiffLog.textContent = result.closureDiff || "";
  ui.closureDiffLog.hidden = !result.closureDiff;
  if (status === "passed" && result.impactAvailable) {
    ui.activationPreviewTitle.textContent = "Closure impact готовий";
    ui.activationPreviewDetail.textContent = "Пакети, версії та помітні зміни розміру порівняно з /run/current-system. Цей звіт не є повним списком дій activation.";
  } else if (status === "passed") {
    ui.activationPreviewTitle.textContent = "Closure зібрано, але diff недоступний";
    ui.activationPreviewDetail.textContent = "Системний dry-preview можна запускати лише через перевірений helper; test і switch залишаються вимкненими.";
  }
  updateBuildPreviewControls();
}

function renderActivationPreview(result) {
  model.activationPreview = result;
  ui.activationPreview.classList.remove("running", "passed", "failed");
  const passed = result.status === "passed";
  ui.activationPreview.classList.add(passed ? "passed" : "failed");
  ui.activationPreviewIcon.textContent = passed ? "✓" : "!";
  ui.activationPreviewTitle.textContent = passed
    ? "Системний dry-preview завершено"
    : "Системний dry-preview не пройшов";
  ui.activationPreviewDetail.textContent = passed
    ? "Helper виконав лише switch-to-configuration dry-activate для точно перевіреного closure. Конфігурація й активне покоління не змінилися; звіт може бути неповним."
    : "Жодної активації не виконано. Перевірте звіт helper-а.";
  const lines = [];
  if (result.command?.length) lines.push(`$ ${result.command.join(" ")}`);
  if (result.stdout) lines.push(result.stdout.trim());
  if (result.stderr) lines.push(`STDERR\n${result.stderr.trim()}`);
  ui.activationPreviewLog.textContent = lines.join("\n\n");
  ui.activationPreviewLog.hidden = lines.length === 0;
  ui.runActivationPreviewButton.textContent = "Повторити dry-preview";
  ui.runTestActivationButton.textContent = result.testActivationPrepared
    ? "Тимчасово виконати test"
    : "Test недоступний у цьому режимі";
  updateActivationPreviewControls();
}

async function runActivationPreview() {
  ui.runActivationPreviewButton.disabled = true;
  ui.runActivationPreviewButton.textContent = "Очікування авторизації…";
  ui.activationPreview.classList.remove("passed", "failed");
  ui.activationPreview.classList.add("running");
  ui.activationPreviewIcon.textContent = "◇";
  ui.activationPreviewTitle.textContent = "Helper аналізує системні зміни";
  ui.activationPreviewDetail.textContent = "Polkit підтверджує окрему read-only дію. Apply, test та switch цією операцією недоступні.";
  try {
    renderActivationPreview(await api("/api/helper/activation-preview", { method: "POST" }));
  } catch (error) {
    ui.activationPreview.classList.remove("running");
    ui.activationPreview.classList.add("failed");
    ui.activationPreviewIcon.textContent = "!";
    ui.activationPreviewTitle.textContent = "Dry-preview відхилено";
    ui.activationPreviewDetail.textContent = error.message;
    ui.runActivationPreviewButton.textContent = "Спробувати dry-preview";
    updateActivationPreviewControls();
  }
}

function renderTestActivation(result) {
  model.testActivation = result;
  const active = result.status === "active";
  const recovered = result.status === "recovered";
  ui.activationPreview.classList.remove("running", "passed", "failed");
  ui.activationPreview.classList.add(active || recovered ? "passed" : "failed");
  ui.activationPreviewIcon.textContent = active ? "◉" : recovered ? "✓" : "!";
  if (active) {
    const deadline = new Date(result.recoveryDeadline * 1000).toLocaleTimeString("uk-UA");
    ui.activationPreviewTitle.textContent = "Тимчасова test-активація активна";
    ui.activationPreviewDetail.textContent = `Попередня runtime-система буде автоматично відновлена не пізніше ${deadline}. Boot generation і switch не змінено.`;
  } else if (recovered) {
    ui.activationPreviewTitle.textContent = "Попередню runtime-систему відновлено";
    ui.activationPreviewDetail.textContent = "Test-сесію завершено. Постійний switch і зміна boot generation не виконувалися.";
  } else {
    ui.activationPreviewTitle.textContent = "Test-активація не завершилася";
    ui.activationPreviewDetail.textContent = "Автоматичний recovery лишається пріоритетним захисним механізмом.";
  }
  const lines = [];
  if (result.command?.length) lines.push(`$ ${result.command.join(" ")}`);
  if (result.sessionId) lines.push(`SESSION ${result.sessionId}`);
  if (result.stdout) lines.push(result.stdout.trim());
  if (result.stderr) lines.push(`STDERR\n${result.stderr.trim()}`);
  ui.testActivationLog.textContent = lines.join("\n\n");
  ui.testActivationLog.hidden = lines.length === 0;
  updateActivationPreviewControls();
}

async function runTestActivation() {
  const receipt = model.activationPreview?.testReceipt;
  if (!receipt) return;
  const confirmed = window.confirm(
    "Тимчасово активувати перевірений NixOS-кандидат? Служби можуть перезапуститися. Попередня runtime-система буде автоматично відновлена; switch і boot generation не зміняться.",
  );
  if (!confirmed) return;
  ui.runTestActivationButton.disabled = true;
  ui.runTestActivationButton.textContent = "Очікування Polkit…";
  try {
    renderTestActivation(await api("/api/helper/test-activation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ testReceipt: receipt }),
    }));
  } catch (error) {
    ui.activationPreview.classList.add("failed");
    ui.activationPreviewTitle.textContent = "Test-активацію відхилено";
    ui.activationPreviewDetail.textContent = error.message;
    updateActivationPreviewControls();
  }
}

async function recoverTestActivation() {
  const sessionId = model.testActivation?.sessionId;
  if (!sessionId) return;
  ui.recoverTestActivationButton.disabled = true;
  ui.recoverTestActivationButton.textContent = "Відновлення…";
  try {
    renderTestActivation(await api("/api/helper/recover-test-activation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    }));
  } catch (error) {
    ui.activationPreview.classList.add("failed");
    ui.activationPreviewTitle.textContent = "Потрібна увага до recovery";
    ui.activationPreviewDetail.textContent = error.message;
    ui.recoverTestActivationButton.disabled = false;
    ui.recoverTestActivationButton.textContent = "Повторити відновлення";
  }
}

let buildPollTimer;
async function pollBuildPreview() {
  window.clearTimeout(buildPollTimer);
  const jobId = model.buildPreview?.jobId;
  if (!jobId) return;
  try {
    const cursor = model.buildPreview.nextCursor || 0;
    const result = await api(`/api/build-preview/${jobId}?after=${cursor}`);
    renderBuildPreview(result);
    if (activeBuildStatuses.has(result.status)) {
      buildPollTimer = window.setTimeout(pollBuildPreview, 500);
    }
  } catch (error) {
    showToast(`Не вдалося оновити build-журнал: ${error.message}`, true);
    buildPollTimer = window.setTimeout(pollBuildPreview, 1500);
  }
}

async function startBuildPreview() {
  ui.startBuildPreviewButton.disabled = true;
  try {
    renderBuildPreview(await api("/api/build-preview", { method: "POST" }));
    pollBuildPreview();
  } catch (error) {
    showToast(error.message, true);
    updateBuildPreviewControls();
  }
}

async function cancelBuildPreview() {
  const jobId = model.buildPreview?.jobId;
  if (!jobId) return;
  ui.cancelBuildPreviewButton.disabled = true;
  try {
    renderBuildPreview(await api(`/api/build-preview/${jobId}/cancel`, { method: "POST" }));
    pollBuildPreview();
  } catch (error) {
    showToast(error.message, true);
    updateBuildPreviewControls();
  }
}

function closeAdoptionPlan() {
  ui.planDrawer.classList.remove("open");
  ui.planDrawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    ui.planBackdrop.hidden = true;
    ui.planDrawer.inert = true;
  }, 220);
}

async function refreshPreview() {
  model.preview = await api("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentState()),
  });
  renderPreview();
}

async function openPreview() {
  try {
    await refreshPreview();
    ui.backdrop.hidden = false;
    ui.drawer.inert = false;
    ui.drawer.classList.add("open");
    ui.drawer.setAttribute("aria-hidden", "false");
    ui.closePreview.focus();
  } catch (error) { showToast(error.message, true); }
}

function closePreview() {
  ui.drawer.classList.remove("open");
  ui.drawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    ui.backdrop.hidden = true;
    ui.drawer.inert = true;
  }, 220);
}

let toastTimer;
function showToast(message, error = false) {
  window.clearTimeout(toastTimer);
  ui.toast.textContent = message;
  ui.toast.classList.toggle("error", error);
  ui.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => ui.toast.classList.remove("visible"), 3600);
}

async function save() {
  ui.saveButton.disabled = true;
  ui.drawerSaveButton.disabled = true;
  try {
    const result = await api("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentState()),
    });
    model.preview = result;
    model.savedPackages = new Set(model.selected);
    updateChangeState();
    renderPreview();
    const outputName = result.outputPath.split(/[\\/]/).pop();
    showToast(`Модуль збережено: ${outputName}`);
  } catch (error) {
    showToast(error.message, true);
    updateChangeState();
  }
}

async function initialize() {
  try {
    const config = await api("/api/config");
    model.token = config.token;
    const [catalog, state, system, adoption, helper, buildPreview] = await Promise.all([
      api("/api/catalog"),
      api("/api/state"),
      api("/api/system"),
      api("/api/adoption"),
      api("/api/helper"),
      api("/api/build-preview"),
    ]);
    model.catalog = catalog;
    model.state = state;
    const knownPackages = new Set(catalog.map((app) => app.attribute));
    for (const attribute of state.packages) {
      if (!knownPackages.has(attribute)) {
        model.catalog.push({
          attribute,
          name: attribute,
          description: "Пакет із поточного керованого стану.",
          category: "Інші",
          featured: false,
          symbol: attribute.slice(0, 1).toLocaleUpperCase("uk"),
        });
      }
    }
    model.selected = new Set(state.packages);
    model.savedPackages = new Set(state.packages);
    renderSystemTarget(system);
    renderAdoptionPlan(adoption);
    renderHelperStatus(helper);
    renderBuildPreview(buildPreview);
    if (activeBuildStatuses.has(buildPreview.status)) pollBuildPreview();
    buildFilters();
    renderCatalog();
    updateChangeState();
  } catch (error) {
    showToast(`Не вдалося завантажити стан: ${error.message}`, true);
  }
}

ui.search.addEventListener("input", renderCatalog);
ui.previewButton.addEventListener("click", openPreview);
ui.closePreview.addEventListener("click", closePreview);
ui.backdrop.addEventListener("click", closePreview);
ui.saveButton.addEventListener("click", save);
ui.drawerSaveButton.addEventListener("click", save);
ui.diffTab.addEventListener("click", () => { model.previewMode = "diff"; renderPreview(); });
ui.sourceTab.addEventListener("click", () => { model.previewMode = "source"; renderPreview(); });
ui.adoptionPlanButton.addEventListener("click", openAdoptionPlan);
ui.closePlan.addEventListener("click", closeAdoptionPlan);
ui.closePlanFooter.addEventListener("click", closeAdoptionPlan);
ui.planBackdrop.addEventListener("click", closeAdoptionPlan);
ui.validateCandidateButton.addEventListener("click", validateCandidate);
ui.validateHelperButton.addEventListener("click", validateWithHelper);
ui.startBuildPreviewButton.addEventListener("click", startBuildPreview);
ui.cancelBuildPreviewButton.addEventListener("click", cancelBuildPreview);
ui.runActivationPreviewButton.addEventListener("click", runActivationPreview);
ui.runTestActivationButton.addEventListener("click", runTestActivation);
ui.recoverTestActivationButton.addEventListener("click", recoverTestActivation);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && ui.drawer.classList.contains("open")) closePreview();
  if (event.key === "Escape" && ui.planDrawer.classList.contains("open")) closeAdoptionPlan();
  if (event.key === "/" && document.activeElement !== ui.search) {
    event.preventDefault();
    ui.search.focus();
  }
});

initialize();
