const ui = {
  appVersion: document.querySelector("#appVersion"),
  catalog: document.querySelector("#catalog"),
  emptyState: document.querySelector("#emptyState"),
  search: document.querySelector("#searchInput"),
  filters: document.querySelector("#categoryFilters"),
  resultCount: document.querySelector("#resultCount"),
  title: document.querySelector("#catalogTitle"),
  presetCatalog: document.querySelector("#presetCatalog"),
  catalogCompatibility: document.querySelector("#catalogCompatibility"),
  catalogCompatibilityIcon: document.querySelector("#catalogCompatibilityIcon"),
  catalogCompatibilityTitle: document.querySelector("#catalogCompatibilityTitle"),
  catalogCompatibilityDetail: document.querySelector("#catalogCompatibilityDetail"),
  refreshCatalogCompatibility: document.querySelector("#refreshCatalogCompatibility"),
  catalogGuidance: document.querySelector("#catalogGuidance"),
  catalogGuidanceContext: document.querySelector("#catalogGuidanceContext"),
  catalogGuidanceCards: document.querySelector("#catalogGuidanceCards"),
  importProfileButton: document.querySelector("#importProfileButton"),
  exportProfileButton: document.querySelector("#exportProfileButton"),
  profileFileInput: document.querySelector("#profileFileInput"),
  changeCount: document.querySelector("#changeCount"),
  previewButton: document.querySelector("#previewButton"),
  saveButton: document.querySelector("#saveButton"),
  drawerSaveButton: document.querySelector("#drawerSaveButton"),
  commitManagedApplyButton: document.querySelector("#commitManagedApplyButton"),
  managedApplyConfirmationWrap: document.querySelector("#managedApplyConfirmationWrap"),
  managedApplyConfirmation: document.querySelector("#managedApplyConfirmation"),
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
  commitTestedSystemButton: document.querySelector("#commitTestedSystemButton"),
  rollbackCommittedSystemButton: document.querySelector("#rollbackCommittedSystemButton"),
  testActivationLog: document.querySelector("#testActivationLog"),
  safetyModeNote: document.querySelector("#safetyModeNote"),
  programsNav: document.querySelector("#programsNav"),
  settingsNav: document.querySelector("#settingsNav"),
  servicesNav: document.querySelector("#servicesNav"),
  driversNav: document.querySelector("#driversNav"),
  programsPage: document.querySelector("#programsPage"),
  settingsPage: document.querySelector("#settingsPage"),
  servicesPage: document.querySelector("#servicesPage"),
  driversPage: document.querySelector("#driversPage"),
  pageTitle: document.querySelector("#pageTitle"),
  settingsCatalog: document.querySelector("#settingsCatalog"),
  settingsEmptyState: document.querySelector("#settingsEmptyState"),
  settingsSearch: document.querySelector("#settingsSearch"),
  settingsFilters: document.querySelector("#settingsFilters"),
  settingsCount: document.querySelector("#settingsCount"),
  settingsTitle: document.querySelector("#settingsTitle"),
  unknownSettingsNote: document.querySelector("#unknownSettingsNote"),
  effectiveSettingsStatus: document.querySelector("#effectiveSettingsStatus"),
  effectiveSettingsDetail: document.querySelector("#effectiveSettingsDetail"),
  refreshEffectiveSettings: document.querySelector("#refreshEffectiveSettings"),
  serviceSummaryCards: document.querySelector("#serviceSummaryCards"),
  serviceContextNote: document.querySelector("#serviceContextNote"),
  servicesInspectionStatus: document.querySelector("#servicesInspectionStatus"),
  servicesInspectionTitle: document.querySelector("#servicesInspectionTitle"),
  servicesInspectionDetail: document.querySelector("#servicesInspectionDetail"),
  refreshServices: document.querySelector("#refreshServices"),
  servicesSearch: document.querySelector("#servicesSearch"),
  servicesFilters: document.querySelector("#servicesFilters"),
  servicesTitle: document.querySelector("#servicesTitle"),
  servicesCount: document.querySelector("#servicesCount"),
  servicesCatalog: document.querySelector("#servicesCatalog"),
  servicesEmptyState: document.querySelector("#servicesEmptyState"),
  driverSummaryCards: document.querySelector("#driverSummaryCards"),
  driverContextNote: document.querySelector("#driverContextNote"),
  driverHardwareStatus: document.querySelector("#driverHardwareStatus"),
  driverHardwareIcon: document.querySelector("#driverHardwareIcon"),
  driverHardwareTitle: document.querySelector("#driverHardwareTitle"),
  driverHardwareDetail: document.querySelector("#driverHardwareDetail"),
  refreshDrivers: document.querySelector("#refreshDrivers"),
  driverSafetyNote: document.querySelector("#driverSafetyNote"),
  driverSafetyTitle: document.querySelector("#driverSafetyTitle"),
  driverSafetyDetail: document.querySelector("#driverSafetyDetail"),
  driversTitle: document.querySelector("#driversTitle"),
  driversCount: document.querySelector("#driversCount"),
  driversFilters: document.querySelector("#driversFilters"),
  driversCatalog: document.querySelector("#driversCatalog"),
  driversEmptyState: document.querySelector("#driversEmptyState"),
  topActions: document.querySelector(".top-actions"),
  homeManagerNav: document.querySelector("#homeManagerNav"),
  homeManagerPage: document.querySelector("#homeManagerPage"),
  homeManagerStatus: document.querySelector("#homeManagerStatus"),
  homeManagerStatusTitle: document.querySelector("#homeManagerStatusTitle"),
  homeManagerStatusDetail: document.querySelector("#homeManagerStatusDetail"),
  homeManagerUserCount: document.querySelector("#homeManagerUserCount"),
  homeManagerUsers: document.querySelector("#homeManagerUsers"),
  homeManagerState: document.querySelector("#homeManagerState"),
  homeManagerPackageSearch: document.querySelector("#homeManagerPackageSearch"),
  homeManagerPackageCount: document.querySelector("#homeManagerPackageCount"),
  homeManagerSelectedUser: document.querySelector("#homeManagerSelectedUser"),
  homeManagerPreviewButton: document.querySelector("#homeManagerPreviewButton"),
  homeManagerAdoptionButton: document.querySelector("#homeManagerAdoptionButton"),
  homeManagerCatalog: document.querySelector("#homeManagerCatalog"),
  homeManagerCatalogEmpty: document.querySelector("#homeManagerCatalogEmpty"),
  homePreviewBackdrop: document.querySelector("#homePreviewBackdrop"),
  homePreviewDrawer: document.querySelector("#homePreviewDrawer"),
  homePreviewTitle: document.querySelector("#homePreviewTitle"),
  closeHomePreview: document.querySelector("#closeHomePreview"),
  closeHomePreviewFooter: document.querySelector("#closeHomePreviewFooter"),
  homePreviewDiffTab: document.querySelector("#homePreviewDiffTab"),
  homePreviewSourceTab: document.querySelector("#homePreviewSourceTab"),
  homePreviewCode: document.querySelector("#homePreviewCode code"),
  homeAdoptionBackdrop: document.querySelector("#homeAdoptionBackdrop"),
  homeAdoptionDrawer: document.querySelector("#homeAdoptionDrawer"),
  homeAdoptionTitle: document.querySelector("#homeAdoptionTitle"),
  closeHomeAdoption: document.querySelector("#closeHomeAdoption"),
  closeHomeAdoptionFooter: document.querySelector("#closeHomeAdoptionFooter"),
  homeAdoptionStatus: document.querySelector("#homeAdoptionStatus"),
  homeAdoptionFileCount: document.querySelector("#homeAdoptionFileCount"),
  homeAdoptionCode: document.querySelector("#homeAdoptionCode code"),
  homeAdoptionValidation: document.querySelector("#homeAdoptionValidation"),
  homeAdoptionValidationIcon: document.querySelector("#homeAdoptionValidationIcon"),
  homeAdoptionValidationTitle: document.querySelector("#homeAdoptionValidationTitle"),
  homeAdoptionValidationDetail: document.querySelector("#homeAdoptionValidationDetail"),
  homeAdoptionValidationLog: document.querySelector("#homeAdoptionValidationLog"),
  validateHomeAdoptionButton: document.querySelector("#validateHomeAdoptionButton"),
  homeBuildPreview: document.querySelector("#homeBuildPreview"),
  homeBuildPreviewIcon: document.querySelector("#homeBuildPreviewIcon"),
  homeBuildPreviewTitle: document.querySelector("#homeBuildPreviewTitle"),
  homeBuildPreviewDetail: document.querySelector("#homeBuildPreviewDetail"),
  homeBuildPreviewLog: document.querySelector("#homeBuildPreviewLog"),
  startHomeBuildPreviewButton: document.querySelector("#startHomeBuildPreviewButton"),
  cancelHomeBuildPreviewButton: document.querySelector("#cancelHomeBuildPreviewButton"),
  homeApplyFlow: document.querySelector("#homeApplyFlow"),
  homeApplyIcon: document.querySelector("#homeApplyIcon"),
  homeApplyTitle: document.querySelector("#homeApplyTitle"),
  homeApplyDetail: document.querySelector("#homeApplyDetail"),
  prepareHomeApplyButton: document.querySelector("#prepareHomeApplyButton"),
  commitHomeApplyButton: document.querySelector("#commitHomeApplyButton"),
  homeApplyConfirmationWrap: document.querySelector("#homeApplyConfirmationWrap"),
  homeApplyConfirmation: document.querySelector("#homeApplyConfirmation"),
  homeApplyLog: document.querySelector("#homeApplyLog"),
  generationsNav: document.querySelector("#generationsNav"),
  generationsPage: document.querySelector("#generationsPage"),
  generationStatus: document.querySelector("#generationStatus"),
  generationStatusTitle: document.querySelector("#generationStatusTitle"),
  generationStatusDetail: document.querySelector("#generationStatusDetail"),
  generationCount: document.querySelector("#generationCount"),
  generationList: document.querySelector("#generationList"),
  refreshGenerations: document.querySelector("#refreshGenerations"),
  generationBoundary: document.querySelector("#generationBoundary"),
  generationBoundaryTitle: document.querySelector("#generationBoundaryTitle"),
  generationBoundaryDetail: document.querySelector("#generationBoundaryDetail"),
};

const model = {
  token: "",
  localWriteEnabled: true,
  catalog: [],
  catalogCompatibility: { status: "loading", packages: [], warnings: [] },
  catalogGuidance: { schemaVersion: 1, alternativeGroups: [], companions: [], contextRecommendations: [] },
  presets: [],
  driverProfiles: { schemaVersion: 1, profiles: [] },
  settingsCatalog: [],
  state: { schemaVersion: 1, packages: [], options: {} },
  savedPackages: new Set(),
  selected: new Set(),
  options: {},
  savedOptions: {},
  settingErrors: new Map(),
  dependencyIssues: [],
  settingsCategory: "Усі",
  servicesCategory: "Усі",
  driversCategory: "Усі",
  page: "programs",
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
  permanentActivation: null,
  effectiveSettings: { status: "idle", settings: [], warnings: [] },
  homeManager: {
    status: "loading",
    integrations: [],
    users: [],
    sources: [],
    userState: { status: "missing", profileCount: 0, state: { schemaVersion: 1, users: {} } },
    warnings: [],
  },
  homeUserKey: null,
  homePackageSelections: new Map(),
  homePreview: { diff: "", generated: "" },
  homePreviewMode: "diff",
  homeAdoption: null,
  homeAdoptionValidation: null,
  homeBuildPreview: { jobId: null, status: "idle", nextCursor: 0, events: [] },
  homeBuildLog: [],
  homeApplyIntent: null,
  managedApplyIntent: null,
  generations: { status: "loading", generations: [], warnings: [] },
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
    options: NcmSettings.normalizeOptions(model.options),
  };
}

function dirtyCount() {
  const all = new Set([...model.savedPackages, ...model.selected]);
  let count = 0;
  for (const item of all) {
    if (model.savedPackages.has(item) !== model.selected.has(item)) count += 1;
  }
  return count + NcmSettings.optionChangeCount(model.savedOptions, model.options);
}

function refreshDependencyIssues() {
  model.dependencyIssues = NcmSettings.dependencyIssues(
    model.settingsCatalog,
    model.options,
    model.effectiveSettings.settings,
  );
}

function updateChangeState() {
  refreshDependencyIssues();
  const count = dirtyCount();
  const lastTwo = count % 100;
  const last = count % 10;
  const label = lastTwo >= 11 && lastTwo <= 14
    ? "змін"
    : last === 1 ? "зміна" : last >= 2 && last <= 4 ? "зміни" : "змін";
  ui.changeCount.textContent = count ? `${count} ${label}` : "Немає змін";
  ui.changeCount.classList.toggle("dirty", count > 0);
  const dependencyErrors = model.dependencyIssues.filter(
    (issue) => issue.status === "unsatisfied",
  ).length;
  const compatibilityErrors = NcmCatalog.selectionCompatibilityIssues(
    model.selected,
    model.catalogCompatibility,
  ).length;
  const invalid = model.settingErrors.size > 0 || dependencyErrors > 0 || compatibilityErrors > 0;
  ui.changeCount.textContent = model.settingErrors.size
    ? `${model.settingErrors.size} некоректне значення`
    : dependencyErrors
      ? `${dependencyErrors} невирішена залежність`
      : compatibilityErrors
        ? countLabel(
          compatibilityErrors,
          "несумісний пакет",
          "несумісні пакети",
          "несумісних пакетів",
        )
      : (count ? `${count} ${label}` : "Немає змін");
  ui.changeCount.classList.toggle("invalid", invalid);
  const managedWrite = model.helper?.managedWriteEnabled === true;
  ui.saveButton.disabled = (!model.localWriteEnabled && !managedWrite) || count === 0 || invalid;
  ui.drawerSaveButton.disabled = (!model.localWriteEnabled && !managedWrite) || count === 0 || invalid;
  ui.previewButton.disabled = invalid;
  if (model.managedApplyIntent) clearManagedApplyIntent();
  if (ui.presetCatalog) renderPresets();
  if (ui.catalogGuidance) renderCatalogGuidance();
  if (ui.serviceSummaryCards) renderServiceOverview();
  if (ui.driverSummaryCards) renderDriverOverview();
}

function systemCatalog() {
  return model.catalog.filter((app) => (app.scopes || ["system"]).includes("system"));
}

function buildFilters() {
  const smart = model.catalogCompatibility.status === "passed"
    ? ["Сумісні", "Потребують уваги"]
    : [];
  const categories = ["Усі", "Популярні", ...smart, ...new Set(systemCatalog().map((app) => app.category))];
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
  const compatibility = NcmCatalog.packageCompatibility(model.catalogCompatibility, app.attribute);
  const categoryMatch = model.category === "Усі"
    || (model.category === "Популярні" && app.featured)
    || (model.category === "Сумісні" && compatibility.status === "compatible" && !compatibility.unfree)
    || (model.category === "Потребують уваги" && (compatibility.status !== "compatible" || compatibility.unfree))
    || app.category === model.category;
  const text = `${app.name} ${app.attribute} ${app.description} ${(app.tags || []).join(" ")}`
    .toLocaleLowerCase("uk");
  return categoryMatch && (!query || text.includes(query));
}

function appCard(app) {
  const card = document.createElement("article");
  const selected = model.selected.has(app.attribute);
  const compatibility = NcmCatalog.packageCompatibility(model.catalogCompatibility, app.attribute);
  card.className = `app-card${selected ? " selected" : ""}${compatibility.status === "incompatible" ? " incompatible" : ""}`;

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
  const compatibilityBadge = document.createElement("span");
  const compatibilityCopy = {
    "missing-attribute": "Немає в nixpkgs",
    "unsupported-platform": "Не для цієї платформи",
    "broken-package": "Позначено як зламаний",
    "evaluation-rejected": "Nix відхилив пакет",
    "inspection-unavailable": "Не перевірено",
  };
  compatibilityBadge.className = `compatibility-badge ${compatibility.status}${compatibility.unfree ? " unfree" : ""}`;
  compatibilityBadge.textContent = compatibility.unfree
    ? "Невільна ліцензія"
    : compatibility.status === "compatible"
      ? "Сумісний"
      : (compatibilityCopy[compatibility.reason] || "Не перевірено");
  compatibilityBadge.title = compatibility.unfree && compatibility.license
    ? `Ліцензія: ${compatibility.license}`
    : compatibilityBadge.textContent;
  copy.append(name, packageName, description, compatibilityBadge);
  if (compatibility.status === "incompatible") {
    const alternative = NcmCatalog.bestAlternative(
      app.attribute,
      model.catalogGuidance,
      model.catalogCompatibility,
    );
    if (alternative) {
      const alternativeApp = model.catalog.find((item) => item.attribute === alternative.attribute);
      const hint = document.createElement("div");
      hint.className = "alternative-hint";
      const hintText = document.createElement("span");
      hintText.textContent = `Альтернатива: ${alternativeApp?.name || alternative.attribute}`;
      const hintButton = document.createElement("button");
      hintButton.type = "button";
      hintButton.textContent = model.selected.has(alternative.attribute) ? "Додано" : "Додати";
      hintButton.disabled = model.selected.has(alternative.attribute);
      hintButton.title = alternative.reason;
      hintButton.addEventListener("click", () => {
        model.selected.add(alternative.attribute);
        renderCatalog();
        updateChangeState();
        showToast(`Додано сумісну альтернативу: ${alternativeApp?.name || alternative.attribute}.`);
      });
      hint.append(hintText, hintButton);
      copy.append(hint);
    }
  }

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "app-toggle";
  toggle.textContent = "✓";
  toggle.setAttribute("aria-label", `${selected ? "Вилучити" : "Додати"} ${app.name}`);
  toggle.setAttribute("aria-pressed", String(selected));
  if (!selected && compatibility.status === "incompatible") {
    toggle.disabled = true;
    toggle.title = `${compatibilityBadge.textContent}. Додавання вимкнено для поточної цілі.`;
  }
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
  const available = systemCatalog();
  const visible = available.filter(matches);
  ui.catalog.replaceChildren(...visible.map(appCard));
  ui.emptyState.hidden = visible.length > 0;
  ui.resultCount.textContent = `${visible.length} із ${available.length}`;
  ui.title.textContent = model.category === "Усі" ? "Усі програми" : model.category;
}

function catalogApp(attribute) {
  return model.catalog.find((item) => item.attribute === attribute);
}

function guidanceContextLabel() {
  const context = model.catalogCompatibility.context || {};
  const desktopLabels = {
    plasma: "Plasma",
    gnome: "GNOME",
    xfce: "Xfce",
    cinnamon: "Cinnamon",
    mate: "MATE",
    hyprland: "Hyprland",
    sway: "Sway",
  };
  const gpuLabels = { amd: "AMD GPU", intel: "Intel GPU", nvidia: "NVIDIA GPU" };
  const facts = (context.desktopEnvironments || []).map((item) => desktopLabels[item] || item);
  const isWsl = (context.configurationFlags || []).includes("wsl");
  if (!isWsl) {
    if (context.runtimeHardwareInspected && context.formFactor === "laptop") facts.push("ноутбук");
    for (const vendor of context.gpuVendors || []) {
      if (gpuLabels[vendor]) facts.push(gpuLabels[vendor]);
    }
    if (context.kvmAvailable) facts.push("KVM");
  }
  if (isWsl) facts.push("NixOS-WSL");
  return facts.length
    ? `Враховано: ${[...new Set(facts)].join(" · ")}. Нічого не додається автоматично.`
    : "Показуємо лише пояснювані зв’язки; нічого не додається автоматично.";
}

function renderCatalogGuidance() {
  if (!ui.catalogGuidance) return;
  const alternatives = NcmCatalog.incompatibleAlternativeSuggestions(
    systemCatalog(),
    model.selected,
    model.catalogGuidance,
    model.catalogCompatibility,
    2,
  );
  const companions = NcmCatalog.companionSuggestions(
    model.selected,
    model.catalogGuidance,
    model.catalogCompatibility,
    2,
  );
  const contextual = NcmCatalog.contextSuggestions(
    model.selected,
    model.catalogGuidance,
    model.catalogCompatibility,
    3,
  );
  const seen = new Set();
  const suggestions = [...alternatives, ...companions, ...contextual]
    .filter((item) => {
      if (seen.has(item.attribute)) return false;
      seen.add(item.attribute);
      return true;
    })
    .slice(0, 4);
  ui.catalogGuidance.hidden = suggestions.length === 0;
  ui.catalogGuidanceContext.textContent = guidanceContextLabel();
  const kindLabels = {
    alternative: "Сумісна альтернатива",
    companion: "Супутній інструмент",
    context: "Для цієї системи",
  };
  ui.catalogGuidanceCards.replaceChildren(...suggestions.map((suggestion) => {
    const app = catalogApp(suggestion.attribute);
    const card = document.createElement("article");
    card.className = `guidance-card ${suggestion.kind}`;
    const kind = document.createElement("span");
    kind.className = "guidance-kind";
    kind.textContent = kindLabels[suggestion.kind] || "Рекомендація";
    const title = document.createElement("strong");
    title.textContent = suggestion.title;
    const packageName = document.createElement("span");
    packageName.className = "guidance-package";
    packageName.textContent = `${app?.name || suggestion.attribute} · pkgs.${suggestion.attribute}`;
    const reason = document.createElement("p");
    reason.textContent = suggestion.reason;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Додати до вибору";
    button.addEventListener("click", () => {
      model.selected.add(suggestion.attribute);
      renderCatalog();
      updateChangeState();
      showToast(`Додано за рекомендацією: ${app?.name || suggestion.attribute}.`);
    });
    card.append(kind, title, packageName, reason, button);
    return card;
  }));
}

function countLabel(count, one, few, many) {
  const lastTwo = count % 100;
  const last = count % 10;
  const word = lastTwo >= 11 && lastTwo <= 14
    ? many
    : last === 1 ? one : last >= 2 && last <= 4 ? few : many;
  return `${count} ${word}`;
}

function presetCard(preset) {
  const card = document.createElement("article");
  const delta = NcmCatalog.presetDelta(preset, currentState());
  const compatibility = NcmCatalog.presetCompatibility(preset, model.catalogCompatibility);
  card.className = `preset-card${delta === 0 ? " complete" : ""}`;

  const symbol = document.createElement("span");
  symbol.className = "preset-symbol";
  symbol.textContent = preset.symbol;
  const copy = document.createElement("div");
  const category = document.createElement("span");
  category.className = "preset-category";
  category.textContent = preset.category;
  const name = document.createElement("h3");
  name.textContent = preset.name;
  const description = document.createElement("p");
  description.textContent = preset.description;
  const summary = document.createElement("small");
  const optionCount = Object.keys(preset.options || {}).length;
  summary.textContent = countLabel(preset.packages.length, "програма", "програми", "програм")
    + (optionCount ? ` · ${countLabel(optionCount, "системна опція", "системні опції", "системних опцій")}` : "");
  copy.append(category, name, description, summary);

  const button = document.createElement("button");
  button.type = "button";
  button.disabled = delta === 0 || !compatibility.compatible;
  button.textContent = delta === 0
    ? "Додано"
    : compatibility.compatible ? "Додати набір" : "Є несумісні пакунки";
  if (!compatibility.compatible) {
    button.title = `Недоступні для поточної цілі: ${compatibility.incompatible.join(", ")}`;
  }
  button.addEventListener("click", () => {
    const result = NcmCatalog.applyPreset(preset, currentState());
    model.selected = new Set(result.state.packages);
    model.options = NcmSettings.normalizeOptions(result.state.options);
    model.settingErrors.clear();
    renderPresets();
    renderCatalog();
    renderSettings();
    renderServices();
    renderDrivers();
    updateChangeState();
    const changes = result.addedPackages + result.changedOptions;
    showToast(`${preset.name}: додано або оновлено ${countLabel(changes, "елемент", "елементи", "елементів")}.`);
  });
  card.append(symbol, copy, button);
  return card;
}

function renderPresets() {
  ui.presetCatalog.replaceChildren(...model.presets.map(presetCard));
}

function renderCatalogCompatibility() {
  const report = model.catalogCompatibility;
  const packages = report.packages || [];
  const compatible = packages.filter((item) => item.status === "compatible").length;
  const incompatible = packages.filter((item) => item.status === "incompatible").length;
  const unfree = packages.filter((item) => item.unfree).length;
  ui.catalogCompatibility.className = "catalog-compatibility-status";
  ui.refreshCatalogCompatibility.disabled = report.status === "loading";
  if (report.status === "loading") {
    ui.catalogCompatibility.classList.add("loading");
    ui.catalogCompatibilityIcon.textContent = "◎";
    ui.catalogCompatibilityTitle.textContent = "Перевіряємо сумісність каталогу…";
    ui.catalogCompatibilityDetail.textContent = "Nix evaluator лише читає пакунки поточної конфігурації.";
    return;
  }
  if (report.status === "passed") {
    ui.catalogCompatibility.classList.add(incompatible ? "attention" : "passed");
    ui.catalogCompatibilityIcon.textContent = incompatible ? "!" : "✓";
    ui.catalogCompatibilityTitle.textContent = `Перевірено для ${report.system || "поточної платформи"}`;
    ui.catalogCompatibilityDetail.textContent = `${compatible} сумісних · ${incompatible} недоступних · ${unfree} з невільною ліцензією · ${report.durationMs || 0} мс`;
    return;
  }
  ui.catalogCompatibility.classList.add("attention");
  ui.catalogCompatibilityIcon.textContent = "?";
  ui.catalogCompatibilityTitle.textContent = "Сумісність не перевірено";
  ui.catalogCompatibilityDetail.textContent = report.warnings?.[0]
    || "Каталог залишається доступним; остаточну перевірку виконає build-preview.";
}

async function refreshCatalogCompatibility() {
  model.catalogCompatibility = { status: "loading", packages: [], warnings: [] };
  renderCatalogCompatibility();
  try {
    model.catalogCompatibility = NcmCatalog.normalizeCompatibilityReport(
      await api("/api/catalog-compatibility"),
    );
  } catch (error) {
    model.catalogCompatibility = {
      status: "failed",
      packages: [],
      warnings: [error.message],
    };
  }
  if (!["Усі", "Популярні", ...new Set(systemCatalog().map((app) => app.category))].includes(model.category)
      && model.catalogCompatibility.status !== "passed") {
    model.category = "Усі";
  }
  renderCatalogCompatibility();
  buildFilters();
  renderPresets();
  renderCatalog();
  renderCatalogGuidance();
  buildServicesFilters();
  renderServices();
  buildDriversFilters();
  renderDrivers();
  updateChangeState();
}

function exportProfile() {
  try {
    const content = NcmCatalog.serializeProfile(currentState(), model.settingsCatalog, NcmSettings);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `nix-control-manager-profile-${stamp}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast("Профіль експортовано у JSON-файл.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function importProfileFile() {
  const [file] = ui.profileFileInput.files || [];
  ui.profileFileInput.value = "";
  if (!file) return;
  if (file.size > 1024 * 1024) {
    showToast("Файл профілю завеликий: дозволено до 1 МБ.", true);
    return;
  }
  try {
    const state = NcmCatalog.parseProfile(await file.text(), model.settingsCatalog, NcmSettings);
    const knownPackages = new Set(model.catalog.map((app) => app.attribute));
    for (const attribute of state.packages) {
      if (!knownPackages.has(attribute)) {
        model.catalog.push({
          attribute,
          name: attribute,
          description: "Пакунок з імпортованого профілю; його буде збережено без змін.",
          category: "Інші",
          featured: false,
          symbol: attribute.slice(0, 1).toLocaleUpperCase("uk"),
          tags: ["імпорт"],
          scopes: ["system"],
        });
      }
    }
    model.selected = new Set(state.packages);
    model.options = NcmSettings.normalizeOptions(state.options);
    model.settingErrors.clear();
    buildFilters();
    buildSettingsFilters();
    buildServicesFilters();
    renderPresets();
    renderCatalog();
    renderCatalogCompatibility();
    renderSettings();
    renderServices();
    updateChangeState();
    showToast(`Профіль імпортовано: ${state.packages.length} пакунків, ${Object.keys(state.options).length} опцій.`);
  } catch (error) {
    showToast(`Не вдалося імпортувати профіль: ${error.message}`, true);
  }
}

function settingDefinitions() {
  const known = new Set(model.settingsCatalog.map((definition) => definition.path));
  const unknown = Object.keys(model.options)
    .filter((path) => !known.has(path))
    .sort()
    .map((path) => ({
      path,
      name: path,
      description: "Опція з наявного state-файлу, якої немає в поточному типізованому каталозі.",
      category: "Інші",
      valueType: "json",
      nixosType: "невідомий тип",
      risk: "medium",
      unknown: true,
    }));
  return [...model.settingsCatalog, ...unknown];
}

function buildSettingsFilters() {
  const categories = ["Усі", ...new Set(settingDefinitions().map((item) => item.category))];
  ui.settingsFilters.replaceChildren(...categories.map((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter${category === model.settingsCategory ? " active" : ""}`;
    button.textContent = category;
    button.addEventListener("click", () => {
      model.settingsCategory = category;
      buildSettingsFilters();
      renderSettings();
    });
    return button;
  }));
}

function settingMatches(definition) {
  const query = ui.settingsSearch.value.trim().toLocaleLowerCase("uk");
  const categoryMatch = model.settingsCategory === "Усі"
    || definition.category === model.settingsCategory;
  const text = `${definition.name} ${definition.path} ${definition.description} ${definition.category}`
    .toLocaleLowerCase("uk");
  return categoryMatch && (!query || text.includes(query));
}

const serviceCategoryLabels = {
  connectivity: "Мережа і зв’язок",
  desktop: "Робочий стіл",
  hardware: "Обладнання",
  maintenance: "Обслуговування",
  security: "Безпека",
  virtualization: "Віртуалізація",
};

function serviceDefinitions() {
  return NcmSettings.serviceDefinitions(model.settingsCatalog);
}

function serviceTargetContext() {
  return model.catalogCompatibility?.context || { configurationFlags: [] };
}

function serviceNeedsAttention(definition) {
  const actual = effectiveSetting(definition.path);
  return !NcmSettings.serviceTargetStatus(definition, serviceTargetContext()).supported
    || ["conflict", "evaluation-failed", "option-missing"].includes(actual?.assessment);
}

function buildServicesFilters() {
  const categories = [
    "Усі",
    "Керовані",
    "Потребують уваги",
    ...new Set(serviceDefinitions().map((definition) => definition.service.category)),
  ];
  ui.servicesFilters.replaceChildren(...categories.map((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter${category === model.servicesCategory ? " active" : ""}`;
    button.textContent = serviceCategoryLabels[category] || category;
    button.addEventListener("click", () => {
      model.servicesCategory = category;
      buildServicesFilters();
      renderServices();
    });
    return button;
  }));
}

function serviceMatches(definition) {
  const query = ui.servicesSearch.value.trim().toLocaleLowerCase("uk");
  const categoryMatch = model.servicesCategory === "Усі"
    || (model.servicesCategory === "Керовані" && Object.hasOwn(model.options, definition.path))
    || (model.servicesCategory === "Потребують уваги" && serviceNeedsAttention(definition))
    || definition.service.category === model.servicesCategory;
  const text = `${definition.name} ${definition.path} ${definition.description} ${definition.category} ${
    serviceCategoryLabels[definition.service.category] || definition.service.category
  }`.toLocaleLowerCase("uk");
  return categoryMatch && (!query || text.includes(query));
}

function effectiveSetting(path) {
  return model.effectiveSettings.settings?.find((setting) => setting.path === path) || null;
}

function actualValueText(definition, value) {
  if (value === null) return "null (автоматично)";
  if (definition.valueType === "boolean") return value ? "Увімкнено" : "Вимкнено";
  if (definition.valueType === "enum") {
    return definition.choices?.find((choice) => choice.value === value)?.label || String(value);
  }
  if (Array.isArray(value) && value.length === 0) return "Немає";
  const formatted = NcmSettings.formatEditorValue(definition, value);
  return formatted === "" ? "порожнє значення" : formatted;
}

function sourceLabel(source) {
  const normalized = source.replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.slice(-3).join("/") || source;
}

function usableActualValue(definition) {
  const actual = effectiveSetting(definition.path);
  if (!actual?.available || actual.value === null) return undefined;
  try {
    return NcmSettings.parseEditorValue(
      definition,
      NcmSettings.formatEditorValue(definition, actual.value),
    );
  } catch {
    return undefined;
  }
}

function priorityLabel(actual) {
  if (actual.activePriority === null || actual.activePriority === undefined) return "";
  const labels = {
    forced: "примусове перевизначення",
    "strong-override": "сильне перевизначення",
    normal: "звичайне визначення",
    "weak-override": "послаблене перевизначення",
    "module-default": "модульне стандартне (mkDefault)",
    "option-default": "вбудоване стандартне опції",
    "weak-default": "слабке стандартне визначення",
  };
  return `пріоритет ${actual.activePriority} · ${labels[actual.priorityKind] || "інший"}`;
}

function assessmentLabel(actual) {
  const count = actual.definitions?.length || actual.definitionFiles?.length || 0;
  const labels = {
    conflict: "активні scalar-значення конфліктують",
    "evaluation-failed": "активне значення не вдалося обчислити",
    "option-missing": "опції немає в цій версії NixOS",
    "single-definition": "одне активне визначення",
    "list-merged": `об’єднано активні списки: ${count}`,
    "equal-definitions": `активні scalar-значення однакові: ${count}`,
    "type-merged": `значення об’єднано типом опції: ${count}`,
  };
  return labels[actual.assessment] || "";
}

function effectiveDefinitions(actual) {
  if (actual.definitions?.length) return actual.definitions;
  return (actual.definitionFiles || []).map((file) => ({
    file,
    valueAvailable: false,
    value: null,
  }));
}

function appendDefinitionDetails(panel, definition, actual) {
  const definitions = effectiveDefinitions(actual);
  if (!definitions.length) return;
  const sources = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = `Активні визначення: ${definitions.length}`;
  const list = document.createElement("ul");
  for (const active of definitions) {
    const item = document.createElement("li");
    const file = document.createElement("code");
    file.textContent = sourceLabel(active.file);
    file.title = active.file;
    const activeValue = document.createElement("span");
    activeValue.textContent = active.valueAvailable
      ? actualValueText(definition, active.value)
      : "значення недоступне";
    item.append(file, activeValue);
    list.append(item);
  }
  sources.append(summary, list);
  panel.append(sources);
}

function effectiveSettingPanel(definition, managed) {
  const panel = document.createElement("div");
  panel.className = "effective-setting";
  const actual = effectiveSetting(definition.path);
  const label = document.createElement("span");
  label.className = "effective-setting-label";
  label.textContent = "Фактично в NixOS";
  const value = document.createElement("strong");
  const comparison = document.createElement("span");
  comparison.className = "effective-setting-comparison";
  const provenance = document.createElement("div");
  provenance.className = "effective-setting-provenance";

  if (model.effectiveSettings.status === "loading" || model.effectiveSettings.status === "idle") {
    value.textContent = "Читаємо…";
    comparison.textContent = "лише читання";
  } else if (!actual?.available) {
    value.textContent = actual?.assessment === "conflict" ? "Конфлікт" : "Недоступно";
    comparison.textContent = assessmentLabel(actual || {});
    panel.classList.add("unavailable");
    panel.classList.toggle("conflict", actual?.assessment === "conflict");
  } else {
    value.textContent = actualValueText(definition, actual.value);
    const same = managed
      && JSON.stringify(model.options[definition.path]) === JSON.stringify(actual.value);
    const ownershipLabels = {
      inherited: "успадковано з конфігурації",
      managed: "визначено модулем NCM",
      shared: "NCM та інші модулі",
    };
    comparison.textContent = managed
      ? (same ? "запропоноване значення збігається" : "запропоноване значення відрізняється")
      : (ownershipLabels[actual.ownership] || "лише читається");
    panel.classList.toggle("will-change", managed && !same);
    panel.classList.toggle("same", same);
  }
  panel.append(label, value, comparison);
  if (actual) {
    const assessment = assessmentLabel(actual);
    const priority = priorityLabel(actual);
    for (const text of [assessment, priority].filter(Boolean)) {
      const badge = document.createElement("span");
      badge.textContent = text;
      badge.title = text.startsWith("пріоритет")
        ? "У Nix менше числове значення означає сильніший override. Показано лише активний пріоритет."
        : "Пояснення стосується активних визначень після фільтрації override.";
      provenance.append(badge);
    }
    panel.classList.toggle("forced", actual.priorityKind === "forced");
    panel.classList.toggle("merged", ["list-merged", "equal-definitions", "type-merged"].includes(actual.assessment));
    if (provenance.childElementCount) panel.append(provenance);
    appendDefinitionDetails(panel, definition, actual);
  }
  return panel;
}

function refreshCardComparison(card, definition) {
  const actual = effectiveSetting(definition.path);
  if (!actual?.available) return;
  const panel = card.querySelector(".effective-setting");
  const comparison = panel?.querySelector(".effective-setting-comparison");
  if (!panel || !comparison) return;
  const same = Object.hasOwn(model.options, definition.path)
    && JSON.stringify(model.options[definition.path]) === JSON.stringify(actual.value);
  comparison.textContent = same
    ? "запропоноване значення збігається"
    : "запропоноване значення відрізняється";
  panel.classList.toggle("same", same);
  panel.classList.toggle("will-change", !same);
}

function dependencyValueLabel(path, value) {
  const definition = model.settingsCatalog.find((item) => item.path === path);
  if (!definition) return JSON.stringify(value);
  return actualValueText(definition, value);
}

function settingDependencyPanel(definition) {
  const issues = model.dependencyIssues.filter(
    (issue) => issue.path === definition.path && issue.status !== "satisfied",
  );
  if (!issues.length) return null;
  const panel = document.createElement("section");
  panel.className = `setting-dependency ${issues.some((issue) => issue.status === "unsatisfied") ? "invalid" : "unknown"}`;
  for (const issue of issues) {
    const item = document.createElement("div");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = issue.status === "unsatisfied"
      ? "Залежність не виконано"
      : "Залежність не вдалося перевірити";
    const message = document.createElement("p");
    message.textContent = issue.message;
    const requirement = document.createElement("small");
    requirement.textContent = `${issue.requiredName}: потрібно «${dependencyValueLabel(
      issue.requiredPath,
      issue.requiredValue,
    )}».`;
    copy.append(title, message, requirement);

    const repair = document.createElement("button");
    repair.type = "button";
    repair.textContent = `Налаштувати: ${issue.requiredName}`;
    const requiredActual = effectiveSetting(issue.requiredPath);
    const manuallyBlocked = [
      "conflict", "evaluation-failed", "option-missing",
    ].includes(requiredActual?.assessment);
    repair.disabled = manuallyBlocked;
    repair.title = manuallyBlocked
      ? "Батьківська опція потребує ручного огляду."
      : `Явно додати ${issue.requiredPath} до керованого state.`;
    repair.addEventListener("click", () => {
      model.options[issue.requiredPath] = JSON.parse(JSON.stringify(issue.requiredValue));
      model.settingErrors.delete(issue.requiredPath);
      renderSettings();
      renderServices();
      updateChangeState();
    });
    item.append(copy, repair);
    panel.append(item);
  }
  return panel;
}

function refreshDependencyPanels() {
  refreshDependencyIssues();
  for (const container of [ui.settingsCatalog, ui.servicesCatalog]) {
    for (const card of container.querySelectorAll(".setting-card[data-setting-path]")) {
      const definition = settingDefinitions().find((item) => item.path === card.dataset.settingPath);
      card.querySelector(".setting-dependency")?.remove();
      if (!definition?.unknown) {
        const panel = settingDependencyPanel(definition);
        const field = card.querySelector(".setting-field");
        if (panel) card.insertBefore(panel, field);
      }
    }
  }
}

function renderEffectiveSettingsStatus() {
  const inspection = model.effectiveSettings;
  ui.refreshEffectiveSettings.disabled = inspection.status === "loading";
  if (inspection.status === "loading") {
    ui.effectiveSettingsStatus.textContent = "Читаємо фактичну конфігурацію NixOS…";
    ui.effectiveSettingsDetail.textContent = "Nix evaluator не виконує build, activation або запис файлів.";
    return;
  }
  if (inspection.status === "passed") {
    const target = inspection.configurationMode === "flake"
      ? `flake: ${inspection.flakeTarget}`
      : "configuration.nix (channels)";
    const attention = inspection.settings?.filter((setting) => [
      "conflict", "evaluation-failed", "option-missing",
    ].includes(setting.assessment)).length || 0;
    ui.effectiveSettingsStatus.textContent = attention
      ? `Фактичну конфігурацію прочитано · потребують уваги: ${attention}`
      : "Фактичну конфігурацію прочитано";
    ui.effectiveSettingsDetail.textContent = `${target} · ${inspection.durationMs} мс · лише читання`;
    return;
  }
  const warning = inspection.warnings?.[0]?.split("\n", 1)[0];
  ui.effectiveSettingsStatus.textContent = "Фактична конфігурація недоступна";
  ui.effectiveSettingsDetail.textContent = warning || "Перевірку ще не виконано.";
}

async function refreshEffectiveSettings() {
  model.effectiveSettings = { status: "loading", settings: [], warnings: [] };
  renderEffectiveSettingsStatus();
  renderSettings();
  renderServices();
  renderDrivers();
  try {
    model.effectiveSettings = await api("/api/effective-settings");
  } catch (error) {
    model.effectiveSettings = { status: "failed", settings: [], warnings: [error.message] };
  }
  renderEffectiveSettingsStatus();
  renderSettings();
  renderServices();
  renderDrivers();
}

function settingControl(definition, managed, card, surface = "settings") {
  const field = document.createElement("div");
  field.className = "setting-field";
  const controlId = `setting-${surface}-${definition.path.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const label = document.createElement("label");
  label.htmlFor = controlId;
  label.textContent = surface === "services" ? "Бажаний стан" : "Значення";
  let control;

  if (definition.valueType === "boolean" || definition.valueType === "enum") {
    control = document.createElement("select");
    const choices = definition.valueType === "boolean"
      ? [{ value: "true", label: "Увімкнено" }, { value: "false", label: "Вимкнено" }]
      : definition.choices;
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = choice.value;
      option.textContent = choice.label;
      control.append(option);
    }
  } else if (definition.valueType === "string-list" || definition.valueType === "integer-list") {
    control = document.createElement("textarea");
    control.rows = 2;
    control.placeholder = definition.valueType === "integer-list"
      ? "Наприклад: 22, 80, 443"
      : "Значення через кому або з нового рядка";
  } else {
    control = document.createElement("input");
    control.type = definition.valueType === "integer" ? "number" : "text";
    if (definition.minimum !== undefined) control.min = String(definition.minimum);
    if (definition.maximum !== undefined) control.max = String(definition.maximum);
    if (definition.suggestions?.length) {
      const list = document.createElement("datalist");
      list.id = `${controlId}-suggestions`;
      for (const suggestion of definition.suggestions) {
        const option = document.createElement("option");
        option.value = suggestion;
        list.append(option);
      }
      control.setAttribute("list", list.id);
      field.append(list);
    }
  }

  control.id = controlId;
  control.disabled = !managed;
  control.value = NcmSettings.formatEditorValue(
    definition,
    managed ? model.options[definition.path] : definition.default,
  );
  const error = document.createElement("small");
  error.className = "setting-error";
  error.hidden = true;
  const update = () => {
    try {
      model.options[definition.path] = NcmSettings.parseEditorValue(definition, control.value);
      model.settingErrors.delete(definition.path);
      card.classList.remove("invalid");
      error.hidden = true;
    } catch (problem) {
      model.settingErrors.set(definition.path, problem.message);
      card.classList.add("invalid");
      error.textContent = problem.message;
      error.hidden = false;
    }
    refreshCardComparison(card, definition);
    updateChangeState();
    refreshDependencyPanels();
  };
  control.addEventListener(definition.valueType === "string" ? "input" : "change", update);
  if (definition.valueType.endsWith("-list") || definition.valueType === "integer") {
    control.addEventListener("input", update);
  }
  field.append(label, control, error);
  return field;
}

function serviceMetadata(definition) {
  const metadata = document.createElement("div");
  metadata.className = "service-meta";
  const modeLabels = {
    background: "постійна фонова",
    integration: "системна інтеграція",
    scheduled: "періодичний запуск",
  };
  const exposureLabels = {
    none: "без мережевого входу",
    "local-network": "видима в локальній мережі",
    "remote-access": "віддалений доступ",
  };
  const riskLabels = { low: "низький вплив", medium: "помірний вплив", high: "високий вплив" };
  const badges = [
    [serviceCategoryLabels[definition.service.category], "category"],
    [modeLabels[definition.service.mode], "mode"],
    [exposureLabels[definition.service.exposure], `exposure ${definition.service.exposure}`],
    [riskLabels[definition.risk], `risk ${definition.risk}`],
  ];
  const target = NcmSettings.serviceTargetStatus(definition, serviceTargetContext());
  if (!target.supported) {
    badges.push([target.target === "wsl" ? "не рекомендовано для WSL" : "інша цільова система", "target-warning"]);
  } else if (target.target === "wsl") {
    badges.push(["підходить для WSL", "target-ok"]);
  }
  for (const [text, className] of badges) {
    const badge = document.createElement("span");
    badge.className = `service-badge ${className}`;
    badge.textContent = text;
    metadata.append(badge);
  }
  return metadata;
}

function settingCard(definition, surface = "settings") {
  const card = document.createElement("article");
  const managed = Object.hasOwn(model.options, definition.path);
  const actual = effectiveSetting(definition.path);
  const inspectionPending = !managed && ["idle", "loading"].includes(
    model.effectiveSettings.status,
  );
  const inspectionBlocked = !managed && [
    "conflict", "evaluation-failed", "option-missing",
  ].includes(actual?.assessment);
  const serviceAttention = surface === "services" && serviceNeedsAttention(definition);
  card.className = `setting-card${surface === "services" ? " service-card" : ""}${managed ? " managed" : ""}${definition.unknown ? " unknown" : ""}${serviceAttention ? " service-attention" : ""}`;
  card.dataset.settingPath = definition.path;

  const header = document.createElement("header");
  const heading = document.createElement("div");
  const name = document.createElement("h3");
  name.textContent = definition.name;
  const path = document.createElement("code");
  path.textContent = definition.path;
  heading.append(name, path);
  const manage = document.createElement("button");
  manage.type = "button";
  manage.className = "setting-manage";
  manage.textContent = definition.unknown
    ? "Збережено"
    : (managed
      ? "Керується"
      : (inspectionPending
        ? "Перевірка…"
        : (inspectionBlocked ? "Ручний огляд" : (surface === "services" ? "Керувати" : "Не керувати"))));
  manage.setAttribute("aria-pressed", String(managed));
  manage.disabled = definition.unknown || inspectionPending || inspectionBlocked;
  if (inspectionBlocked) {
    manage.title = "NCM не додаватиме визначення, доки наявну помилку не буде розглянуто вручну.";
  } else if (inspectionPending) {
    manage.title = "Дочекайтеся завершення read-only перевірки фактичної конфігурації.";
  }
  manage.addEventListener("click", () => {
    if (Object.hasOwn(model.options, definition.path)) {
      delete model.options[definition.path];
      model.settingErrors.delete(definition.path);
    } else {
      const actual = usableActualValue(definition);
      model.options[definition.path] = JSON.parse(JSON.stringify(
        actual === undefined ? definition.default : actual,
      ));
    }
    renderSettings();
    renderServices();
    updateChangeState();
  });
  header.append(heading, manage);

  const description = document.createElement("p");
  description.textContent = definition.description;
  let metadata;
  if (surface === "services") {
    metadata = serviceMetadata(definition);
  } else {
    metadata = document.createElement("div");
    metadata.className = "setting-meta";
    const riskLabels = { low: "низький вплив", medium: "помірний вплив", high: "високий вплив" };
    metadata.textContent = `${definition.category} · ${definition.nixosType} · ${riskLabels[definition.risk]}`;
  }
  card.append(header, description, metadata);

  if (definition.unknown) {
    const raw = document.createElement("pre");
    raw.className = "unknown-setting-value";
    raw.textContent = JSON.stringify(model.options[definition.path], null, 2);
    card.append(raw);
  } else {
    card.append(effectiveSettingPanel(definition, managed));
    const dependency = settingDependencyPanel(definition);
    if (dependency) card.append(dependency);
    card.append(settingControl(definition, managed, card, surface));
  }
  return card;
}

function renderSettings() {
  refreshDependencyIssues();
  const definitions = settingDefinitions();
  const visible = definitions.filter(settingMatches);
  ui.settingsCatalog.replaceChildren(...visible.map(settingCard));
  ui.settingsEmptyState.hidden = visible.length > 0;
  ui.settingsCount.textContent = `${visible.length} із ${definitions.length}`;
  ui.settingsTitle.textContent = model.settingsCategory === "Усі"
    ? "Рекомендовані налаштування"
    : model.settingsCategory;
  const unknownCount = definitions.filter((item) => item.unknown).length;
  ui.unknownSettingsNote.hidden = unknownCount === 0;
  ui.unknownSettingsNote.textContent = unknownCount
    ? `${unknownCount} опцій поза каталогом збережено без змін і показано лише для читання.`
    : "";
}

function renderServicesInspectionStatus() {
  const inspection = model.effectiveSettings;
  ui.refreshServices.disabled = inspection.status === "loading";
  ui.servicesInspectionStatus.classList.toggle("passed", inspection.status === "passed");
  ui.servicesInspectionStatus.classList.toggle("attention", inspection.status === "failed");
  if (["idle", "loading"].includes(inspection.status)) {
    ui.servicesInspectionTitle.textContent = inspection.status === "loading"
      ? "Читаємо фактичний стан служб…"
      : "Фактична конфігурація ще не прочитана";
    ui.servicesInspectionDetail.textContent = "Nix evaluator не запускає, не зупиняє і не перезапускає служби.";
    return;
  }
  if (inspection.status === "passed") {
    const summary = NcmSettings.serviceSummary(
      model.settingsCatalog,
      model.options,
      inspection.settings,
      serviceTargetContext(),
    );
    ui.servicesInspectionTitle.textContent = summary.attention
      ? `Стан прочитано · ручний огляд: ${summary.attention}`
      : "Фактичний стан служб прочитано";
    ui.servicesInspectionDetail.textContent = `${inspection.durationMs} мс · лише читання конфігурації`;
    return;
  }
  ui.servicesInspectionTitle.textContent = "Фактичний стан служб недоступний";
  ui.servicesInspectionDetail.textContent = inspection.warnings?.[0]?.split("\n", 1)[0]
    || "Каталог залишається доступним; остаточну перевірку виконає build-preview.";
}

function renderServiceOverview() {
  const summary = NcmSettings.serviceSummary(
    model.settingsCatalog,
    model.options,
    model.effectiveSettings.settings,
    serviceTargetContext(),
  );
  const cards = [
    [String(summary.total), "у перевіреному каталозі", "catalog"],
    [String(summary.enabled), "фактично увімкнено", "enabled"],
    [String(summary.managed), "керуються NCM", "managed"],
    [String(summary.pending), "підготовлено змін", summary.pending ? "pending" : "stable"],
  ].map(([value, label, className]) => {
    const card = document.createElement("article");
    card.className = `service-summary-card ${className}`;
    const strong = document.createElement("strong");
    strong.textContent = value;
    const small = document.createElement("small");
    small.textContent = label;
    card.append(strong, small);
    return card;
  });
  ui.serviceSummaryCards.replaceChildren(...cards);
  const isWsl = (serviceTargetContext().configurationFlags || []).includes("wsl");
  ui.serviceContextNote.textContent = isWsl
    ? `Ціль: NixOS-WSL · ${summary.notRecommended} служб для фізичної NixOS позначено застереженням.`
    : "Ціль: звичайна NixOS · нічого не вмикається автоматично.";
}

function renderServices() {
  refreshDependencyIssues();
  const definitions = serviceDefinitions();
  const visible = definitions.filter(serviceMatches);
  ui.servicesCatalog.replaceChildren(...visible.map((definition) => settingCard(definition, "services")));
  ui.servicesEmptyState.hidden = visible.length > 0;
  ui.servicesCount.textContent = `${visible.length} із ${definitions.length}`;
  ui.servicesTitle.textContent = model.servicesCategory === "Усі"
    ? "Усі служби"
    : (serviceCategoryLabels[model.servicesCategory] || model.servicesCategory);
  renderServicesInspectionStatus();
  renderServiceOverview();
}

const driverCategoryLabels = {
  firmware: "Firmware",
  graphics: "Графіка",
};

const driverVendorLabels = {
  amd: "AMD",
  intel: "Intel",
  microsoft: "Microsoft",
  nvidia: "NVIDIA",
  other: "інший виробник",
  virtio: "VirtIO",
};

function driverContext() {
  return model.catalogCompatibility?.context || {};
}

function driverProfiles() {
  return model.driverProfiles?.profiles || [];
}

function driverAssessment(profile) {
  return NcmSettings.driverProfileAssessment(profile, driverContext());
}

function buildDriversFilters() {
  const categories = ["Усі", "Рекомендовані", "Потребують огляду", "graphics", "firmware"];
  ui.driversFilters.replaceChildren(...categories.map((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter${category === model.driversCategory ? " active" : ""}`;
    button.textContent = driverCategoryLabels[category] || category;
    button.addEventListener("click", () => {
      model.driversCategory = category;
      buildDriversFilters();
      renderDrivers();
    });
    return button;
  }));
}

function driverMatches(profile) {
  const status = driverAssessment(profile).status;
  return model.driversCategory === "Усі"
    || (model.driversCategory === "Рекомендовані" && status === "recommended")
    || (model.driversCategory === "Потребують огляду" && ["review", "unknown"].includes(status))
    || profile.category === model.driversCategory;
}

function driverOptionRow(path, desired) {
  const row = document.createElement("li");
  const definition = model.settingsCatalog.find((item) => item.path === path);
  const key = document.createElement("code");
  key.textContent = path;
  const values = document.createElement("span");
  const wanted = definition ? actualValueText(definition, desired) : JSON.stringify(desired);
  const actual = effectiveSetting(path);
  const actualText = actual?.available && definition
    ? actualValueText(definition, actual.value)
    : "не прочитано";
  values.textContent = `буде: ${wanted} · зараз: ${actualText}`;
  row.append(key, values);
  return row;
}

function driverProfileCard(profile) {
  const assessment = driverAssessment(profile);
  const delta = NcmSettings.driverProfileDelta(profile, model.options);
  const card = document.createElement("article");
  card.className = `driver-card ${assessment.status}${delta === 0 ? " configured" : ""}`;

  const header = document.createElement("header");
  const heading = document.createElement("div");
  const category = document.createElement("span");
  category.className = "driver-category";
  category.textContent = driverCategoryLabels[profile.category] || profile.category;
  const title = document.createElement("h3");
  title.textContent = profile.name;
  heading.append(category, title);
  const status = document.createElement("span");
  status.className = `driver-status ${assessment.status}`;
  const statusLabels = {
    recommended: "відповідає обладнанню",
    review: "потрібен ручний огляд",
    "not-applicable": "не для цієї системи",
    unsupported: "недоступно для WSL",
    unknown: "обладнання не визначено",
  };
  status.textContent = delta === 0 ? "профіль підготовлено" : statusLabels[assessment.status];
  header.append(heading, status);

  const description = document.createElement("p");
  description.textContent = profile.description;
  const metadata = document.createElement("div");
  metadata.className = "driver-meta";
  const riskLabels = { low: "низький ризик", medium: "помірний ризик", high: "високий ризик" };
  const facts = [riskLabels[profile.risk], `${Object.keys(profile.options).length} NixOS-опції`];
  if (profile.vendors.length) {
    facts.unshift(profile.vendors.map((vendor) => driverVendorLabels[vendor] || vendor).join(" / "));
  }
  for (const text of facts) {
    const badge = document.createElement("span");
    badge.textContent = text;
    metadata.append(badge);
  }

  const options = document.createElement("ul");
  options.className = "driver-options";
  options.append(...Object.entries(profile.options).map(([path, desired]) => (
    driverOptionRow(path, desired)
  )));

  const warnings = document.createElement("ul");
  warnings.className = "driver-warnings";
  for (const warning of profile.warnings) {
    const item = document.createElement("li");
    item.textContent = warning;
    warnings.append(item);
  }

  const footer = document.createElement("footer");
  const explanation = document.createElement("small");
  const reasonLabels = {
    "hardware-match": "Виробник GPU збігається з профілем; зміна все одно потребує build.",
    "hybrid-gpu": "Виявлено кілька GPU. NCM не вгадує PRIME bus IDs або режим offload.",
    "manual-review": "Точне покоління пристрою неможливо безпечно визначити лише за виробником.",
    "hardware-unknown": "Read-only перевірка не дала достатньо даних для рекомендації.",
    "vendor-mismatch": "Виявлений виробник GPU не відповідає цьому профілю.",
    "feature-mismatch": "Потрібна функція, наприклад Steam, у поточній конфігурації не виявлена.",
    wsl: "Драйвером GPU керує Windows-хост; Linux-профіль тут не застосовується.",
  };
  explanation.textContent = reasonLabels[assessment.reason] || "Потрібна перевірка сумісності.";
  const button = document.createElement("button");
  button.type = "button";
  const blocked = ["unsupported", "not-applicable", "unknown"].includes(assessment.status);
  button.disabled = blocked || delta === 0;
  button.textContent = delta === 0
    ? "Підготовлено"
    : assessment.status === "recommended" ? "Підготувати профіль" : "Підготувати після огляду";
  button.addEventListener("click", () => {
    const result = NcmSettings.applyDriverProfile(profile, currentState());
    model.options = NcmSettings.normalizeOptions(result.state.options);
    for (const path of Object.keys(profile.options)) model.settingErrors.delete(path);
    renderSettings();
    renderServices();
    renderDrivers();
    updateChangeState();
    showToast(`${profile.name}: підготовлено ${countLabel(
      result.changedOptions, "опцію", "опції", "опцій",
    )}. Жодних змін ще не застосовано.`);
  });
  footer.append(explanation, button);
  card.append(header, description, metadata, options, warnings, footer);
  return card;
}

function renderDriverOverview() {
  const profiles = driverProfiles();
  const summary = NcmSettings.driverSummary(profiles, model.options, driverContext());
  const facts = NcmSettings.driverTargetFacts(driverContext());
  const cards = [
    [String(summary.total), "перевірених профілів", "driver-total"],
    [String(summary.recommended), "відповідають обладнанню", summary.recommended ? "enabled" : "stable"],
    [String(summary.review), "потребують огляду", summary.review ? "pending" : "stable"],
    [String(summary.configured), "підготовлено повністю", summary.configured ? "managed" : "stable"],
  ].map(([value, label, className]) => {
    const card = document.createElement("article");
    card.className = `service-summary-card ${className}`;
    const strong = document.createElement("strong");
    strong.textContent = value;
    const small = document.createElement("small");
    small.textContent = label;
    card.append(strong, small);
    return card;
  });
  ui.driverSummaryCards.replaceChildren(...cards);
  const vendors = facts.vendors.map((vendor) => driverVendorLabels[vendor] || vendor);
  const drivers = facts.configuredDrivers.length ? facts.configuredDrivers.join(", ") : "не задано явно";
  ui.driverContextNote.textContent = facts.target === "wsl"
    ? "Ціль: NixOS-WSL · драйвер GPU належить Windows-хосту."
    : `GPU: ${vendors.length ? vendors.join(" + ") : "не визначено"} · поточний videoDrivers: ${drivers}.`;
}

function renderDriverHardwareStatus() {
  const report = model.catalogCompatibility;
  const facts = NcmSettings.driverTargetFacts(driverContext());
  ui.refreshDrivers.disabled = report.status === "loading";
  ui.driverHardwareStatus.classList.toggle("passed", report.status === "passed" && facts.hardwareInspected);
  ui.driverHardwareStatus.classList.toggle("attention", report.status !== "loading" && (
    facts.target === "wsl" || !facts.hardwareInspected || facts.hybrid
  ));
  if (report.status === "loading") {
    ui.driverHardwareIcon.textContent = "◎";
    ui.driverHardwareTitle.textContent = "Читаємо апаратний контекст…";
    ui.driverHardwareDetail.textContent = "Лише обмежені дані /sys та оцінена конфігурація NixOS.";
  } else if (facts.target === "wsl") {
    ui.driverHardwareIcon.textContent = "◇";
    ui.driverHardwareTitle.textContent = "NixOS-WSL не керує драйвером GPU";
    ui.driverHardwareDetail.textContent = "Графічний пристрій і драйвер надає Windows-хост; профілі фізичної NixOS заблоковано.";
  } else if (!facts.hardwareInspected || facts.vendors.length === 0) {
    ui.driverHardwareIcon.textContent = "?";
    ui.driverHardwareTitle.textContent = "GPU не вдалося визначити надійно";
    ui.driverHardwareDetail.textContent = "Vendor-specific профілі залишаються заблокованими; generic firmware доступний лише для ручного огляду.";
  } else {
    ui.driverHardwareIcon.textContent = facts.hybrid ? "!" : "✓";
    ui.driverHardwareTitle.textContent = facts.hybrid
      ? "Виявлено гібридну або multi-GPU систему"
      : `Виявлено GPU: ${facts.vendors.map((vendor) => driverVendorLabels[vendor] || vendor).join(" + ")}`;
    ui.driverHardwareDetail.textContent = facts.hybrid
      ? "Профілі показані лише як кандидати: PRIME bus IDs і режим offload NCM не вгадує."
      : "Виробника прочитано з PCI sysfs; точне покоління та підтримка перевіряються build-preview.";
  }
  ui.driverSafetyNote.classList.toggle("attention", facts.target === "wsl" || facts.hybrid || !facts.hardwareInspected);
  ui.driverSafetyTitle.textContent = facts.hybrid
    ? "Multi-GPU потребує окремого ручного плану"
    : facts.target === "wsl"
      ? "Linux-драйвери для цієї WSL-цілі не застосовуються"
      : "Профіль не застосовується автоматично";
  ui.driverSafetyDetail.textContent = facts.hybrid
    ? "Поточний етап не генерує PRIME bus IDs, offload або reverse-sync — помилковий здогад тут небезпечний."
    : facts.target === "wsl"
      ? "NCM показує контекст, але не пропонує змін для драйверів фізичної NixOS."
      : "Навіть рекомендований варіант лише змінює чернетку й потребує preview, build та окремої активації.";
}

function renderDrivers() {
  const profiles = driverProfiles();
  const visible = profiles.filter(driverMatches);
  ui.driversCatalog.replaceChildren(...visible.map(driverProfileCard));
  ui.driversEmptyState.hidden = visible.length > 0;
  ui.driversCount.textContent = `${visible.length} із ${profiles.length}`;
  ui.driversTitle.textContent = model.driversCategory === "Усі"
    ? "Рекомендації для обладнання"
    : (driverCategoryLabels[model.driversCategory] || model.driversCategory);
  renderDriverOverview();
  renderDriverHardwareStatus();
}

function homeUserKey(user) {
  return `${user.integration}\u0000${user.name}`;
}

function selectedHomeUser() {
  return model.homeManager.users.find((user) => homeUserKey(user) === model.homeUserKey) || null;
}

function initializeHomePackageSelections() {
  const profiles = model.homeManager.userState?.state?.users || {};
  for (const user of model.homeManager.users) {
    const key = homeUserKey(user);
    const profile = profiles[user.name];
    const packages = profile?.integration === user.integration ? profile.packages : [];
    model.homePackageSelections.set(key, new Set(packages || []));
  }
  if (!selectedHomeUser() && model.homeManager.users.length) {
    model.homeUserKey = homeUserKey(model.homeManager.users[0]);
  }
}

function homePackageCard(app, selectedPackages, disabled) {
  const card = document.createElement("article");
  const selected = selectedPackages.has(app.attribute);
  card.className = `app-card home-package-card${selected ? " selected" : ""}`;

  const symbol = document.createElement("div");
  symbol.className = "app-symbol";
  symbol.textContent = app.symbol;
  const copy = document.createElement("div");
  copy.className = "app-copy";
  const name = document.createElement("h3");
  name.textContent = app.name;
  const packageName = document.createElement("span");
  packageName.className = "package-name";
  packageName.textContent = `home.packages · pkgs.${app.attribute}`;
  const description = document.createElement("p");
  description.textContent = app.description;
  copy.append(name, packageName, description);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "app-toggle";
  toggle.textContent = "✓";
  toggle.disabled = disabled;
  toggle.setAttribute("aria-label", `${selected ? "Вилучити" : "Додати"} ${app.name} для користувача`);
  toggle.setAttribute("aria-pressed", String(selected));
  toggle.addEventListener("click", () => {
    if (selectedPackages.has(app.attribute)) selectedPackages.delete(app.attribute);
    else selectedPackages.add(app.attribute);
    renderHomeManagerPackages();
  });
  const category = document.createElement("div");
  category.className = "category-badge";
  category.textContent = app.category;
  card.append(symbol, copy, toggle, category);
  return card;
}

function renderHomeManagerPackages() {
  const user = selectedHomeUser();
  const invalidState = model.homeManager.userState?.status === "invalid";
  const selectedPackages = user
    ? model.homePackageSelections.get(homeUserKey(user)) || new Set()
    : new Set();
  const query = ui.homeManagerPackageSearch.value.trim().toLocaleLowerCase("uk");
  const homeCatalog = model.catalog.filter(
    (app) => (app.scopes || ["system", "home-manager"]).includes("home-manager"),
  );
  const knownAttributes = new Set(homeCatalog.map((app) => app.attribute));
  const unknown = [...selectedPackages]
    .filter((attribute) => !knownAttributes.has(attribute))
    .map((attribute) => ({
      attribute,
      name: attribute,
      description: "Пакунок із наявного user-state; він буде збережений у кандидатові.",
      category: "Інші",
      symbol: attribute.slice(0, 1).toLocaleUpperCase("uk"),
      tags: ["наявний"],
      scopes: ["home-manager"],
    }));
  const available = [...homeCatalog, ...unknown];
  const visible = user
    ? available.filter((app) => {
      const text = `${app.name} ${app.attribute} ${app.description}`.toLocaleLowerCase("uk");
      return !query || text.includes(query);
    })
    : [];
  ui.homeManagerCatalog.replaceChildren(
    ...visible.map((app) => homePackageCard(app, selectedPackages, invalidState)),
  );
  ui.homeManagerCatalogEmpty.hidden = visible.length > 0;
  ui.homeManagerPackageCount.textContent = user ? `${visible.length} із ${available.length}` : "";
  ui.homeManagerPreviewButton.disabled = !user || invalidState;
  ui.homeManagerAdoptionButton.disabled = !user || invalidState;
  ui.homeManagerPreviewButton.textContent = user
    ? `Переглянути user-модуль (${selectedPackages.size})`
    : "Переглянути user-модуль";
  const integration = user?.integration === "nixos-module" ? "Модуль NixOS" : "Standalone";
  const writeMode = model.helper?.homeManagerLiveWriteEnabled === true
    ? "opt-in запис доступний"
    : "запис вимкнено";
  ui.homeManagerSelectedUser.textContent = user
    ? `${user.name} · ${integration} · ${writeMode}`
    : "Спочатку виберіть користувача";
}

function renderHomeManager() {
  const inspection = model.homeManager;
  const integrationLabels = {
    "nixos-module": "Модуль NixOS",
    standalone: "Standalone",
  };
  ui.homeManagerStatus.classList.toggle("detected", inspection.status === "detected");
  ui.homeManagerStatus.classList.toggle("warning", inspection.userState?.status === "invalid");
  if (inspection.status === "detected") {
    ui.homeManagerStatusTitle.textContent = "Home Manager виявлено";
    ui.homeManagerStatusDetail.textContent = inspection.integrations
      .map((item) => integrationLabels[item] || item).join(" · ");
  } else {
    ui.homeManagerStatusTitle.textContent = "Home Manager не виявлено";
    ui.homeManagerStatusDetail.textContent = "Перевірено системну конфігурацію та стандартний standalone-каталог.";
  }
  ui.homeManagerUserCount.textContent = `${inspection.users.length} користувачів`;

  const cards = inspection.users.map((user) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `home-manager-card${homeUserKey(user) === model.homeUserKey ? " selected" : ""}`;
    card.setAttribute("aria-pressed", String(homeUserKey(user) === model.homeUserKey));
    const icon = document.createElement("span");
    icon.className = "home-user-icon";
    icon.textContent = user.name.slice(0, 1).toLocaleUpperCase("uk");
    const copy = document.createElement("div");
    const name = document.createElement("h3");
    name.textContent = user.name;
    const integration = document.createElement("strong");
    integration.textContent = integrationLabels[user.integration] || user.integration;
    const source = document.createElement("code");
    source.textContent = user.source;
    copy.append(name, integration, source);
    card.append(icon, copy);
    card.addEventListener("click", () => {
      model.homeUserKey = homeUserKey(user);
      renderHomeManager();
    });
    return card;
  });
  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "home-manager-empty";
    empty.textContent = inspection.status === "detected"
      ? "Інтеграцію знайдено, але ім’я користувача неможливо надійно визначити статично."
      : "Наявних Home Manager профілів не знайдено.";
    cards.push(empty);
  }
  ui.homeManagerUsers.replaceChildren(...cards);

  const state = inspection.userState || {};
  const stateCard = document.createElement("article");
  stateCard.className = `home-manager-state-card ${state.status || "missing"}`;
  const title = document.createElement("strong");
  const statusLabels = {
    missing: "User-state ще не створено",
    current: "User-state прочитано",
    invalid: "User-state пошкоджено або несумісний",
  };
  title.textContent = statusLabels[state.status] || state.status;
  const path = document.createElement("code");
  path.textContent = state.path || "user-state.local.json";
  const detail = document.createElement("p");
  detail.textContent = state.status === "current"
    ? `${state.profileCount} керованих профілів · схема ${state.state?.schemaVersion}`
    : state.status === "invalid"
      ? (state.warning || "Файл не буде використано до ручного виправлення.")
      : "Канонічний ncm/user-state.json ще відсутній; зовнішній legacy state використовується лише як джерело міграції.";
  const boundary = document.createElement("small");
  boundary.textContent = model.helper?.homeManagerLiveWriteEnabled === true
    ? "Opt-in запис через helper · активація вимкнена · flake inputs не змінюються"
    : "Запис вимкнено · активація вимкнена · flake inputs не змінюються";
  stateCard.append(title, path, detail, boundary);
  ui.homeManagerState.replaceChildren(stateCard);
  renderHomeManagerPackages();
}

function showPage(page) {
  model.page = page;
  const settings = page === "settings";
  const services = page === "services";
  const drivers = page === "drivers";
  const homeManager = page === "home-manager";
  const generations = page === "generations";
  const programs = !settings && !services && !drivers && !homeManager && !generations;
  ui.programsPage.hidden = !programs;
  ui.settingsPage.hidden = !settings;
  ui.servicesPage.hidden = !services;
  ui.driversPage.hidden = !drivers;
  ui.homeManagerPage.hidden = !homeManager;
  ui.generationsPage.hidden = !generations;
  ui.programsNav.classList.toggle("active", programs);
  ui.settingsNav.classList.toggle("active", settings);
  ui.servicesNav.classList.toggle("active", services);
  ui.driversNav.classList.toggle("active", drivers);
  ui.homeManagerNav.classList.toggle("active", homeManager);
  ui.generationsNav.classList.toggle("active", generations);
  ui.topActions.hidden = homeManager || generations;
  ui.pageTitle.textContent = generations
    ? "Покоління"
    : homeManager
    ? "Home Manager"
    : services
    ? "Служби"
    : drivers
    ? "Драйвери"
    : (settings ? "Налаштування" : "Програми");
  if (settings) renderSettings();
  if (services) renderServices();
  if (drivers) renderDrivers();
  if (homeManager) renderHomeManager();
  if (generations) renderGenerations();
}

function generationBadge(label, className) {
  const badge = document.createElement("span");
  badge.className = `generation-badge ${className}`;
  badge.textContent = label;
  return badge;
}

function renderGenerations() {
  const inspection = model.generations || { status: "unavailable", generations: [] };
  const items = inspection.generations || [];
  ui.generationStatus.classList.toggle("detected", inspection.status === "detected");
  ui.generationStatus.classList.toggle("warning", inspection.status !== "detected");
  ui.generationStatusTitle.textContent = inspection.status === "detected"
    ? "Системний профіль прочитано"
    : "Покоління NixOS не знайдено";
  const current = items.find((item) => item.currentProfile);
  ui.generationStatusDetail.textContent = current
    ? `Покоління ${current.number} є поточним у профілі · перегляд лише для читання`
    : (inspection.warnings?.[0] || "Системний профіль недоступний у цьому середовищі.");
  ui.generationCount.textContent = `${items.length} ${items.length === 1 ? "покоління" : "поколінь"}`;

  const cards = items.map((item) => {
    const card = document.createElement("article");
    card.className = `generation-card${item.currentProfile ? " current" : ""}`;
    const header = document.createElement("header");
    const title = document.createElement("div");
    const number = document.createElement("strong");
    number.textContent = `Покоління ${item.number}`;
    const version = document.createElement("small");
    version.textContent = item.nixosVersion || "Версію NixOS не визначено";
    title.append(number, version);
    const badges = document.createElement("div");
    badges.className = "generation-badges";
    if (item.currentProfile) badges.append(generationBadge("профіль", "profile"));
    if (item.currentRuntime) badges.append(generationBadge("активне", "runtime"));
    if (item.booted) badges.append(generationBadge("запущене", "booted"));
    header.append(title, badges);
    const path = document.createElement("code");
    path.textContent = item.systemPath;
    const date = document.createElement("p");
    date.textContent = item.createdAt
      ? new Date(item.createdAt).toLocaleString("uk-UA")
      : "Час створення невідомий";
    card.append(header, path, date);
    return card;
  });
  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "home-manager-empty";
    empty.textContent = "У цьому середовищі немає доступного системного профілю NixOS.";
    cards.push(empty);
  }
  ui.generationList.replaceChildren(...cards);
}

async function refreshGenerations() {
  ui.refreshGenerations.disabled = true;
  try {
    model.generations = await api("/api/generations");
    renderGenerations();
  } catch (error) {
    showToast(`Не вдалося оновити покоління: ${error.message}`, true);
  } finally {
    ui.refreshGenerations.disabled = false;
  }
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

function renderHomePreview() {
  const diff = model.homePreviewMode === "diff";
  ui.homePreviewDiffTab.classList.toggle("active", diff);
  ui.homePreviewSourceTab.classList.toggle("active", !diff);
  ui.homePreviewDiffTab.setAttribute("aria-selected", String(diff));
  ui.homePreviewSourceTab.setAttribute("aria-selected", String(!diff));
  ui.homePreviewCode.textContent = diff
    ? (model.homePreview.diff || "Змін немає.")
    : model.homePreview.generated;
}

function currentHomeCandidate() {
  const user = selectedHomeUser();
  if (!user) return null;
  return {
    username: user.name,
    integration: user.integration,
    packages: [...(model.homePackageSelections.get(homeUserKey(user)) || [])].sort(),
  };
}

async function openHomePreview() {
  const user = selectedHomeUser();
  const candidate = currentHomeCandidate();
  if (!user || !candidate) return;
  ui.homeManagerPreviewButton.disabled = true;
  try {
    const preview = await api("/api/home-manager/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(candidate),
    });
    if (
      preview.readOnly !== true
      || preview.writeEnabled !== false
      || preview.activationEnabled !== false
      || preview.flakeInputMutationEnabled !== false
    ) {
      throw new Error("Сервер не підтвердив безпечну preview-only межу");
    }
    model.homePreview = preview;
    model.homePreviewMode = "diff";
    ui.homePreviewTitle.textContent = `${user.name} · керований user-модуль`;
    renderHomePreview();
    ui.homePreviewBackdrop.hidden = false;
    ui.homePreviewDrawer.inert = false;
    ui.homePreviewDrawer.classList.add("open");
    ui.homePreviewDrawer.setAttribute("aria-hidden", "false");
    ui.closeHomePreview.focus();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    renderHomeManagerPackages();
  }
}

function closeHomePreview() {
  ui.homePreviewDrawer.classList.remove("open");
  ui.homePreviewDrawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    ui.homePreviewBackdrop.hidden = true;
    ui.homePreviewDrawer.inert = true;
  }, 220);
}

function renderHomeAdoption() {
  const plan = model.homeAdoption;
  if (!plan) return;
  const labels = {
    ready: "готовий до перевірки",
    "no-changes": "вже підключено",
    manual: "потрібен ручний перегляд",
    blocked: "заблоковано",
  };
  ui.homeAdoptionStatus.textContent = labels[plan.status] || plan.status;
  ui.homeAdoptionStatus.classList.toggle("passed", plan.safeToValidate);
  ui.homeAdoptionFileCount.textContent = `${plan.changes.length} файлів · apply вимкнено`;
  const warningText = (plan.warnings || []).map((item) => `Попередження: ${item}`).join("\n");
  ui.homeAdoptionCode.textContent = plan.combinedDiff
    || warningText
    || "Підключення вже відповідає кандидату; змін немає.";
  ui.validateHomeAdoptionButton.disabled = !plan.safeToValidate;
  ui.homeAdoptionValidation.className = "candidate-validation";
  ui.homeAdoptionValidationIcon.textContent = "◇";
  ui.homeAdoptionValidationTitle.textContent = "Кандидат ще не перевірено";
  ui.homeAdoptionValidationDetail.textContent = "Перевірка створить тимчасову копію, виконає parse/eval і видалить її.";
  ui.homeAdoptionValidationLog.hidden = true;
  ui.homeAdoptionValidationLog.textContent = "";
  resetHomeApplyFlow();
  updateHomeBuildPreviewControls();
}

function resetHomeApplyFlow() {
  model.homeApplyIntent = null;
  ui.homeApplyFlow.className = "candidate-validation home-apply-flow";
  ui.homeApplyIcon.textContent = "◇";
  ui.homeApplyTitle.textContent = "Live-збереження ще не підготовлено";
  ui.homeApplyDetail.textContent = model.helper?.homeManagerLiveWriteEnabled === true
    ? "Після локальної перевірки helper незалежно звірить точний план і видасть короткоживуче підтвердження."
    : "Потрібен окремо налаштований live-home-manager helper; активація за будь-яких умов вимкнена.";
  ui.homeApplyConfirmation.checked = false;
  ui.homeApplyConfirmationWrap.hidden = true;
  ui.commitHomeApplyButton.hidden = true;
  ui.homeApplyLog.hidden = true;
  ui.homeApplyLog.textContent = "";
  updateHomeApplyControls();
}

function updateHomeApplyControls() {
  const exactLocalValidation = model.homeAdoptionValidation?.status === "passed";
  const helperReady = model.helper?.homeManagerLiveWriteEnabled === true
    && model.helper?.homeManagerApplyEnabled === true;
  const preparing = ui.homeApplyFlow.classList.contains("running");
  ui.prepareHomeApplyButton.disabled = preparing
    || !helperReady
    || !exactLocalValidation
    || model.homeAdoption?.status !== "ready";
  const intentReady = typeof model.homeApplyIntent?.intentId === "string"
    && typeof model.homeApplyIntent?.planFingerprint === "string";
  ui.commitHomeApplyButton.disabled = preparing
    || !intentReady
    || ui.homeApplyConfirmation.checked !== true;
}

async function prepareHomeApply() {
  const candidate = currentHomeCandidate();
  if (!candidate) return;
  model.homeApplyIntent = null;
  ui.homeApplyFlow.className = "candidate-validation home-apply-flow running";
  ui.homeApplyIcon.textContent = "◌";
  ui.homeApplyTitle.textContent = "Helper звіряє точний план…";
  ui.homeApplyDetail.textContent = "Створюється одноразовий UID-bound receipt; цільові файли ще не змінюються.";
  ui.homeApplyConfirmationWrap.hidden = true;
  ui.commitHomeApplyButton.hidden = true;
  updateHomeApplyControls();
  try {
    const result = await api("/api/helper/home-manager/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(candidate),
    });
    if (
      result.status !== "passed"
      || result.fixtureOnly !== false
      || result.liveWriteEnabled !== true
      || result.activationEnabled !== false
      || result.homeManagerActivationEnabled !== false
      || result.confirmationRequired !== true
      || typeof result.intentId !== "string"
      || !/^[0-9a-f]{64}$/.test(result.planFingerprint || "")
    ) {
      throw new Error("Helper не підтвердив межу точного live-збереження");
    }
    model.homeApplyIntent = result;
    ui.homeApplyFlow.className = "candidate-validation home-apply-flow passed";
    ui.homeApplyIcon.textContent = "✓";
    ui.homeApplyTitle.textContent = "Точний план готовий до підтвердження";
    ui.homeApplyDetail.textContent = `Fingerprint ${result.planFingerprint.slice(0, 12)}… · receipt діє ${result.expiresInSeconds} с.`;
    ui.homeApplyConfirmation.checked = false;
    ui.homeApplyConfirmationWrap.hidden = false;
    ui.commitHomeApplyButton.hidden = false;
    ui.homeApplyLog.textContent = [
      `TARGET       ${result.targetId}`,
      `USER         ${result.username} · ${result.integration}`,
      `FINGERPRINT  ${result.planFingerprint}`,
      "ACTIVATION   disabled",
    ].join("\n");
    ui.homeApplyLog.hidden = false;
  } catch (error) {
    ui.homeApplyFlow.className = "candidate-validation home-apply-flow failed";
    ui.homeApplyIcon.textContent = "!";
    ui.homeApplyTitle.textContent = "Helper не підготував збереження";
    ui.homeApplyDetail.textContent = error.message;
  } finally {
    updateHomeApplyControls();
  }
}

async function commitHomeApply() {
  const intent = model.homeApplyIntent;
  if (!intent || ui.homeApplyConfirmation.checked !== true) return;
  ui.homeApplyFlow.className = "candidate-validation home-apply-flow running";
  ui.homeApplyIcon.textContent = "◌";
  ui.homeApplyTitle.textContent = "Очікуємо Polkit-авторизацію…";
  ui.homeApplyDetail.textContent = "Після дозволу helper атомарно запише файли, повторно оцінить їх і за потреби виконає rollback.";
  updateHomeApplyControls();
  try {
    const result = await api("/api/helper/home-manager/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intentId: intent.intentId,
        planFingerprint: intent.planFingerprint,
        confirmed: true,
      }),
    });
    if (
      result.state !== "committed"
      || result.fixtureOnly !== false
      || result.liveWriteEnabled !== true
      || result.activationEnabled !== false
      || result.homeManagerActivationEnabled !== false
      || result.switchEnabled !== false
      || result.authorizedByPolkit !== true
    ) {
      throw new Error("Helper не підтвердив завершену неактивуючу транзакцію");
    }
    model.homeApplyIntent = null;
    ui.homeApplyFlow.className = "candidate-validation home-apply-flow passed";
    ui.homeApplyIcon.textContent = "✓";
    ui.homeApplyTitle.textContent = "Джерельні файли безпечно збережено";
    ui.homeApplyDetail.textContent = `Транзакція ${result.transaction.transactionId} завершена. Home Manager не активовано.`;
    ui.homeApplyConfirmationWrap.hidden = true;
    ui.commitHomeApplyButton.hidden = true;
    ui.prepareHomeApplyButton.disabled = true;
    ui.homeApplyLog.textContent += `\nCOMMITTED     ${result.filesWritten} файлів\nACTIVATION    not executed`;
    showToast("Home Manager джерела збережено; активацію не виконано");
    try {
      model.homeManager = await api("/api/home-manager");
      initializeHomePackageSelections();
      renderHomeManager();
    } catch (refreshError) {
      showToast(`Джерела збережено, але стан сторінки не оновлено: ${refreshError.message}`, true);
    }
  } catch (error) {
    model.homeApplyIntent = null;
    ui.homeApplyFlow.className = "candidate-validation home-apply-flow failed";
    ui.homeApplyIcon.textContent = "!";
    ui.homeApplyTitle.textContent = "Збереження не завершено";
    ui.homeApplyDetail.textContent = `${error.message}. Для повтору заново підготуйте точний план.`;
    ui.homeApplyConfirmationWrap.hidden = true;
    ui.commitHomeApplyButton.hidden = true;
  } finally {
    updateHomeApplyControls();
  }
}

async function openHomeAdoption() {
  const candidate = currentHomeCandidate();
  const user = selectedHomeUser();
  if (!candidate || !user) return;
  ui.homeManagerAdoptionButton.disabled = true;
  try {
    const plan = await api("/api/home-manager/adoption-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(candidate),
    });
    if (
      plan.readOnly !== true
      || plan.safeToApply !== false
      || plan.writeEnabled !== false
      || plan.activationEnabled !== false
      || plan.flakeInputMutationEnabled !== false
    ) {
      throw new Error("Сервер не підтвердив read-only межу плану підключення");
    }
    model.homeAdoption = plan;
    model.homeAdoptionValidation = null;
    ui.homeAdoptionTitle.textContent = `${user.name} · план підключення`;
    renderHomeAdoption();
    ui.homeAdoptionBackdrop.hidden = false;
    ui.homeAdoptionDrawer.inert = false;
    ui.homeAdoptionDrawer.classList.add("open");
    ui.homeAdoptionDrawer.setAttribute("aria-hidden", "false");
    ui.closeHomeAdoption.focus();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    renderHomeManagerPackages();
  }
}

function closeHomeAdoption() {
  ui.homeAdoptionDrawer.classList.remove("open");
  ui.homeAdoptionDrawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    ui.homeAdoptionBackdrop.hidden = true;
    ui.homeAdoptionDrawer.inert = true;
  }, 220);
}

async function validateHomeAdoption() {
  const candidate = currentHomeCandidate();
  if (!candidate) return;
  ui.validateHomeAdoptionButton.disabled = true;
  ui.homeAdoptionValidation.className = "candidate-validation running";
  ui.homeAdoptionValidationIcon.textContent = "◌";
  ui.homeAdoptionValidationTitle.textContent = "Перевіряємо тимчасову копію…";
  model.homeAdoptionValidation = null;
  updateHomeBuildPreviewControls();
  try {
    const result = await api("/api/home-manager/validate-adoption", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(candidate),
    });
    if (
      result.readOnly !== true
      || result.writeEnabled !== false
      || result.buildEnabled !== false
      || result.activationEnabled !== false
      || result.flakeInputMutationEnabled !== false
      || result.workingCopyRemoved !== true
    ) {
      throw new Error("Сервер не підтвердив видалення безпечної тимчасової копії");
    }
    model.homeAdoptionValidation = result;
    const passed = result.status === "passed";
    ui.homeAdoptionValidation.className = `candidate-validation ${passed ? "passed" : "failed"}`;
    ui.homeAdoptionValidationIcon.textContent = passed ? "✓" : "!";
    ui.homeAdoptionValidationTitle.textContent = passed
      ? "Тимчасовий кандидат перевірено"
      : "Перевірка кандидата не пройшла";
    ui.homeAdoptionValidationDetail.textContent = passed
      ? "Nix-файли прочитано, конфігурацію оцінено, тимчасову копію видалено."
      : `Статус: ${result.status}. Джерельні файли не змінено.`;
    const checks = (result.checks || []).map(
      (check) => `${check.status.toUpperCase()}  ${check.name}`,
    );
    ui.homeAdoptionValidationLog.textContent = [
      ...checks,
      ...(result.warnings || []).map((item) => `WARN    ${item}`),
    ].join("\n");
    ui.homeAdoptionValidationLog.hidden = false;
    updateHomeBuildPreviewControls();
    updateHomeApplyControls();
  } catch (error) {
    ui.homeAdoptionValidation.className = "candidate-validation failed";
    ui.homeAdoptionValidationIcon.textContent = "!";
    ui.homeAdoptionValidationTitle.textContent = "Помилка безпечної перевірки";
    ui.homeAdoptionValidationDetail.textContent = error.message;
  } finally {
    ui.validateHomeAdoptionButton.disabled = !model.homeAdoption?.safeToValidate;
    updateHomeBuildPreviewControls();
    updateHomeApplyControls();
  }
}

function updateHomeBuildPreviewControls() {
  const active = activeBuildStatuses.has(model.homeBuildPreview?.status);
  const validation = model.homeAdoptionValidation;
  const exactValidation = validation?.status === "passed"
    && typeof validation.planFingerprint === "string"
    && validation.planFingerprint.length === 64;
  ui.startHomeBuildPreviewButton.disabled = active || !exactValidation;
  ui.cancelHomeBuildPreviewButton.hidden = !active;
  ui.cancelHomeBuildPreviewButton.disabled = model.homeBuildPreview?.status === "cancelling";
}

function renderHomeBuildPreview(result) {
  if (
    result.workflow !== "home-manager"
    || result.configurationWriteEnabled !== false
    || result.activationEnabled !== false
    || result.homeManagerActivationEnabled !== false
    || result.switchEnabled !== false
    || result.flakeInputMutationEnabled !== false
    || result.lockFileWriteEnabled !== false
    || result.activationPreviewReady !== false
  ) {
    throw new Error("Сервер не підтвердив безпечну межу Home Manager build-preview");
  }
  const previousJobId = model.homeBuildPreview?.jobId;
  const previousCursor = result.jobId === previousJobId
    ? (model.homeBuildPreview?.nextCursor || 0) : 0;
  if (result.jobId !== previousJobId) model.homeBuildLog = [];
  if (result.logsTruncated && !model.homeBuildLog.length) {
    model.homeBuildLog.push("… попередні рядки журналу вже недоступні …");
  }
  for (const event of result.events || []) {
    if ((event.sequence || 0) <= previousCursor) continue;
    const prefix = event.stream === "stderr" ? "ERR · "
      : event.stream === "command" ? "" : event.stream === "stdout" ? "OUT · " : "NCM · ";
    model.homeBuildLog.push(prefix + event.message);
  }
  model.homeBuildPreview = { ...result, events: [] };
  if (model.homeBuildLog.length > 2000) model.homeBuildLog = model.homeBuildLog.slice(-2000);

  const status = result.status || "idle";
  const active = activeBuildStatuses.has(status);
  ui.homeBuildPreview.classList.remove("running", "passed", "failed", "cancelled");
  if (active) ui.homeBuildPreview.classList.add("running");
  else if (status === "passed") ui.homeBuildPreview.classList.add("passed");
  else if (status === "cancelled") ui.homeBuildPreview.classList.add("cancelled");
  else if (status !== "idle") ui.homeBuildPreview.classList.add("failed");

  const titles = {
    idle: "Home Manager build-preview ще не запущено",
    queued: "Home Manager build-preview у черзі",
    preparing: "План повторно звіряється і перевіряється",
    running: "Nix збирає activationPackage",
    cancelling: "Home Manager build зупиняється",
    cleaning: "Тимчасова копія видаляється",
    passed: "activationPackage успішно зібрано",
    failed: "Home Manager build завершився помилкою",
    cancelled: "Home Manager build скасовано",
    blocked: "Home Manager build заблоковано",
    unavailable: "Автоматична збірка недоступна",
  };
  ui.homeBuildPreviewTitle.textContent = titles[status] || `Home Manager build: ${status}`;
  if (status === "passed") {
    ui.homeBuildPreviewDetail.textContent = "Точний перевірений activationPackage готовий у Nix store. Конфігурацію не записано; activation і home-manager switch не запускалися.";
  } else if (status === "cancelled") {
    ui.homeBuildPreviewDetail.textContent = "Процес Nix зупинено й тимчасову копію видалено. Уже зібрані об’єкти Nix store можуть лишитися для повторного використання.";
  } else if (result.error?.message) {
    ui.homeBuildPreviewDetail.textContent = `${result.error.message}. Конфігурацію й Home Manager профіль не змінено.`;
  } else if (active) {
    ui.homeBuildPreviewDetail.textContent = "Журнал оновлюється. Дозволено лише непривілейований запис до Nix store; activation відсутня.";
  } else {
    ui.homeBuildPreviewDetail.textContent = "Після успішної перевірки можна непривілейовано зібрати точний activationPackage. Запуск activation або home-manager switch відсутній.";
  }
  ui.homeBuildPreviewIcon.textContent = status === "passed" ? "✓"
    : status === "cancelled" ? "■" : active ? "◇" : status === "idle" ? "▱" : "!";
  ui.homeBuildPreviewLog.textContent = model.homeBuildLog.join("\n");
  ui.homeBuildPreviewLog.hidden = model.homeBuildLog.length === 0;
  updateHomeBuildPreviewControls();
}

let homeBuildPollTimer;
async function pollHomeBuildPreview() {
  window.clearTimeout(homeBuildPollTimer);
  const jobId = model.homeBuildPreview?.jobId;
  if (!jobId) return;
  try {
    const cursor = model.homeBuildPreview.nextCursor || 0;
    const result = await api(`/api/home-manager/build-preview/${jobId}?after=${cursor}`);
    renderHomeBuildPreview(result);
    if (activeBuildStatuses.has(result.status)) {
      homeBuildPollTimer = window.setTimeout(pollHomeBuildPreview, 500);
    }
  } catch (error) {
    showToast(`Не вдалося оновити Home Manager build-журнал: ${error.message}`, true);
    homeBuildPollTimer = window.setTimeout(pollHomeBuildPreview, 1500);
  }
}

async function startHomeBuildPreview() {
  const candidate = currentHomeCandidate();
  const fingerprint = model.homeAdoptionValidation?.planFingerprint;
  if (!candidate || typeof fingerprint !== "string") return;
  ui.startHomeBuildPreviewButton.disabled = true;
  try {
    const result = await api("/api/home-manager/build-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...candidate, planFingerprint: fingerprint }),
    });
    renderHomeBuildPreview(result);
    pollHomeBuildPreview();
  } catch (error) {
    showToast(error.message, true);
    updateHomeBuildPreviewControls();
  }
}

async function cancelHomeBuildPreview() {
  const jobId = model.homeBuildPreview?.jobId;
  if (!jobId) return;
  ui.cancelHomeBuildPreviewButton.disabled = true;
  try {
    renderHomeBuildPreview(await api(
      `/api/home-manager/build-preview/${jobId}/cancel`,
      { method: "POST" },
    ));
    pollHomeBuildPreview();
  } catch (error) {
    showToast(error.message, true);
    updateHomeBuildPreviewControls();
  }
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
    const activationReady = model.helper?.permanentSwitchEnabled === true;
    ui.adoptionBanner.hidden = !activationReady;
    if (activationReady) {
      ui.adoptionLabel.textContent = "Система синхронізована";
      ui.adoptionTitle.textContent = "Можна перевірити й застосувати";
      ui.adoptionDetail.textContent = "Файлових змін немає; Nix збере точний поточний source і проведе dry-preview → test → switch.";
      ui.adoptionPlanButton.textContent = "Відкрити перевірку";
    }
    return;
  }
  ui.adoptionBanner.hidden = false;
  ui.adoptionPlanButton.textContent = "Переглянути план";
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
    ? (helper.managedWriteEnabled
      ? "Керований запис NCM підключено"
      : helper.homeManagerLiveWriteEnabled
      ? "Home Manager helper підключено"
      : helper.testActivationEnabled ? "Test helper підключено" : "Read-only helper підключено")
    : "Системний helper недоступний";
  detail.textContent = available
    ? (helper.managedWriteEnabled
      ? `${helper.targetId} · лише два NCM-файли${helper.permanentSwitchEnabled ? " · exact test → switch" : " · switch вимкнено"}`
      : helper.homeManagerLiveWriteEnabled
      ? `${helper.targetId} · точний source-write · activation/switch вимкнено`
      : `${helper.targetId} · без apply/switch${helper.testActivationEnabled ? " · test з auto-recovery" : " · test вимкнено"}${helper.dryActivatePreviewEnabled ? " · dry-preview" : ""}`)
    : (helper.reason || "Unix socket не відповідає");

  const safetyTitle = ui.safetyModeNote.querySelector("strong");
  const safetyDetail = ui.safetyModeNote.querySelector("small");
  safetyTitle.textContent = helper.permanentSwitchEnabled
    ? "Exact-output режим"
    : "Безпечний режим";
  safetyDetail.textContent = helper.permanentSwitchEnabled
    ? "постійно лише після build → dry-preview → test; точний NCM-відкат"
    : "build/test не змінюють boot generation; постійний switch вимкнено";
  ui.generationBoundary.classList.toggle("available", helper.permanentSwitchEnabled === true);
  ui.generationBoundaryTitle.textContent = helper.permanentSwitchEnabled
    ? "Exact-output switch і NCM-відкат доступні"
    : "Кероване перемикання очікує helper-а";
  ui.generationBoundaryDetail.textContent = helper.permanentSwitchEnabled
    ? "Лише активна test-сесія цього користувача може стати системним профілем. Відкат повертає її точний попередній store path."
    : "Постійним можна зробити лише точний output активної test-сесії; відкат обмежено останньою NCM-активацією.";

  const planReady = model.adoption?.safeToApply === true && model.adoption.changes.length > 0;
  ui.validateHelperButton.disabled = !available || !planReady;
  ui.helperAvailability.classList.toggle("available", available);
  ui.helperAvailability.classList.toggle("unavailable", !available);
  ui.helperAvailability.querySelector("small").textContent = available
    ? (helper.managedWriteEnabled
      ? `Live target «${helper.targetId}»: запис лише state.json/packages.nix після diff, validation, підтвердження та Polkit`
      : helper.homeManagerLiveWriteEnabled
      ? `Live target «${helper.targetId}»: Home Manager source-write лише після точного receipt, підтвердження та Polkit; activation вимкнена`
      : `Live target «${helper.targetId}»: перевірка${helper.dryActivatePreviewEnabled ? " та авторизований dry-preview" : ""}${helper.testActivationEnabled ? "; test лише з одноразовим receipt та auto-recovery" : "; test вимкнено"}`)
    : (helper.reason || "Системний helper не налаштовано");
  updateActivationPreviewControls();
  if (ui.homeApplyFlow) updateHomeApplyControls();
  updateChangeState();
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
  ui.runTestActivationButton.textContent = "Тимчасово виконати test";
  ui.recoverTestActivationButton.textContent = "Відновити зараз";
  ui.commitTestedSystemButton.textContent = "Зробити постійним";
  ui.rollbackCommittedSystemButton.textContent = "Відкотити цю активацію";
  const ready = model.buildPreview?.activationPreviewReady === true;
  const helperReady = model.helper?.dryActivatePreviewEnabled === true;
  ui.runActivationPreviewButton.disabled = !ready || !helperReady;
  const prepared = model.activationPreview?.testActivationPrepared === true
    && typeof model.activationPreview?.testReceipt === "string";
  const testReady = model.helper?.testActivationEnabled === true && prepared;
  const active = model.testActivation?.status === "active";
  const permanentStatus = model.permanentActivation?.status;
  const transitionActive = new Set([
    "commit-prepared", "committing", "rollback-prepared", "rolling-back",
  ]).has(permanentStatus);
  const committed = permanentStatus === "committed";
  const testSessionOnly = active && !permanentStatus;
  const permanentAvailable = model.helper?.permanentSwitchEnabled === true;
  ui.runTestActivationButton.disabled = !testReady || active || transitionActive || committed;
  ui.runTestActivationButton.hidden = active || transitionActive || committed;
  ui.recoverTestActivationButton.hidden = !testSessionOnly;
  ui.commitTestedSystemButton.hidden = !testSessionOnly || !permanentAvailable;
  ui.commitTestedSystemButton.disabled = !testSessionOnly || !permanentAvailable;
  ui.rollbackCommittedSystemButton.hidden = !committed;
  ui.rollbackCommittedSystemButton.disabled = !committed;
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
  if (result.status === "active" || result.status === "recovered") {
    model.permanentActivation = null;
  }
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

function renderPermanentActivation(result) {
  model.permanentActivation = result;
  const status = result.status;
  const running = new Set([
    "commit-prepared", "committing", "rollback-prepared", "rolling-back",
  ]).has(status);
  const passed = status === "committed" || status === "rolled-back";
  ui.activationPreview.classList.remove("running", "passed", "failed");
  ui.activationPreview.classList.add(running ? "running" : passed ? "passed" : "failed");
  ui.activationPreviewIcon.textContent = running ? "◇" : passed ? "✓" : "!";
  const titles = {
    "commit-prepared": "Готується точне системне перемикання",
    committing: "Перевірений кандидат стає постійним",
    committed: "Перевірене покоління застосовано постійно",
    "commit-failed": "Постійне перемикання не завершилося",
    recovered: "Невдале перемикання безпечно компенсовано",
    "recovery-required": "Потрібне системне відновлення",
    "rollback-prepared": "Готується точний відкат",
    "rolling-back": "Повертається попередня система",
    "rolled-back": "Попередню систему відновлено",
    "rollback-required": "Автоматичний відкат потребує уваги",
  };
  ui.activationPreviewTitle.textContent = titles[status] || `Стан активації: ${status}`;
  if (status === "committed") {
    ui.activationPreviewDetail.textContent = "Runtime і системний профіль вказують на перевірений store path. Доступний відкат саме цієї NCM-активації.";
  } else if (status === "rolled-back") {
    ui.activationPreviewDetail.textContent = "Runtime і системний профіль повернуто до точного попереднього store path.";
  } else if (running) {
    ui.activationPreviewDetail.textContent = "Операцію виконує окрема системна служба; сторінка читає лише підписаний журнал цієї сесії.";
  } else {
    ui.activationPreviewDetail.textContent = "Системний профіль не вважається успішно зміненим. Перегляньте журнал і стан поколінь.";
  }
  const lines = [];
  if (result.sessionId) lines.push(`SESSION ${result.sessionId}`);
  if (result.systemPath) lines.push(`SYSTEM ${result.systemPath}`);
  if (result.transitionUnit) lines.push(`UNIT ${result.transitionUnit}`);
  ui.testActivationLog.textContent = lines.join("\n");
  ui.testActivationLog.hidden = lines.length === 0;
  ui.commitTestedSystemButton.textContent = "Зробити постійним";
  ui.rollbackCommittedSystemButton.textContent = "Відкотити цю активацію";
  updateActivationPreviewControls();
}

let activationSessionPollTimer;
async function pollActivationSession() {
  window.clearTimeout(activationSessionPollTimer);
  const sessionId = model.permanentActivation?.sessionId || model.testActivation?.sessionId;
  if (!sessionId) return;
  try {
    const result = await api("/api/helper/activation-session-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    });
    renderPermanentActivation(result);
    if (new Set([
      "commit-prepared", "committing", "rollback-prepared", "rolling-back",
    ]).has(result.status)) {
      activationSessionPollTimer = window.setTimeout(pollActivationSession, 750);
    } else {
      void refreshGenerations();
    }
  } catch (error) {
    showToast(`Не вдалося прочитати стан активації: ${error.message}`, true);
    activationSessionPollTimer = window.setTimeout(pollActivationSession, 1500);
  }
}

async function commitTestedSystem() {
  const sessionId = model.testActivation?.sessionId;
  if (!sessionId) return;
  const confirmed = window.confirm(
    "Зробити саме цей протестований NixOS-кандидат постійним? Системний профіль і runtime буде перемкнено на точний store path. Після успіху NCM запропонує точний відкат.",
  );
  if (!confirmed) return;
  ui.commitTestedSystemButton.disabled = true;
  ui.commitTestedSystemButton.textContent = "Очікування Polkit…";
  try {
    renderPermanentActivation(await api("/api/helper/commit-tested-system", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, confirmed: true }),
    }));
    pollActivationSession();
  } catch (error) {
    ui.commitTestedSystemButton.textContent = "Зробити постійним";
    showToast(`Switch відхилено: ${error.message}`, true);
    updateActivationPreviewControls();
  }
}

async function rollbackCommittedSystem() {
  const sessionId = model.permanentActivation?.sessionId;
  if (!sessionId || model.permanentActivation?.status !== "committed") return;
  const confirmed = window.confirm(
    "Відкотити цю NCM-активацію до точного попереднього покоління? Поточні служби буде перемкнено назад.",
  );
  if (!confirmed) return;
  ui.rollbackCommittedSystemButton.disabled = true;
  ui.rollbackCommittedSystemButton.textContent = "Очікування Polkit…";
  try {
    renderPermanentActivation(await api("/api/helper/rollback-committed-system", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, confirmed: true }),
    }));
    pollActivationSession();
  } catch (error) {
    ui.rollbackCommittedSystemButton.textContent = "Відкотити цю активацію";
    showToast(`Відкат відхилено: ${error.message}`, true);
    updateActivationPreviewControls();
  }
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

function clearManagedApplyIntent() {
  model.managedApplyIntent = null;
  if (!ui.managedApplyConfirmation) return;
  ui.managedApplyConfirmation.checked = false;
  ui.managedApplyConfirmationWrap.hidden = true;
  ui.commitManagedApplyButton.hidden = true;
  ui.commitManagedApplyButton.disabled = true;
  ui.drawerSaveButton.hidden = false;
}

function updateManagedApplyControls() {
  const prepared = model.managedApplyIntent !== null;
  ui.managedApplyConfirmationWrap.hidden = !prepared;
  ui.commitManagedApplyButton.hidden = !prepared;
  ui.commitManagedApplyButton.disabled = !prepared || !ui.managedApplyConfirmation.checked;
  ui.drawerSaveButton.hidden = prepared;
}

async function prepareManagedSave() {
  ui.saveButton.disabled = true;
  ui.drawerSaveButton.disabled = true;
  try {
    const result = await api("/api/helper/managed/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentState()),
    });
    model.managedApplyIntent = {
      intentId: result.intentId,
      planFingerprint: result.planFingerprint,
    };
    model.preview = {
      ...model.preview,
      diff: result.combinedDiff || model.preview.diff,
    };
    renderPreview();
    if (!ui.drawer.classList.contains("open")) {
      ui.backdrop.hidden = false;
      ui.drawer.inert = false;
      ui.drawer.classList.add("open");
      ui.drawer.setAttribute("aria-hidden", "false");
    }
    updateManagedApplyControls();
    showToast("Кандидат перевірено. Перегляньте diff і підтвердьте точний запис.");
  } catch (error) {
    clearManagedApplyIntent();
    showToast(error.message, true);
    updateChangeState();
  }
}

async function commitManagedSave() {
  const intent = model.managedApplyIntent;
  if (!intent || !ui.managedApplyConfirmation.checked) return;
  ui.commitManagedApplyButton.disabled = true;
  try {
    const result = await api("/api/helper/managed/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intentId: intent.intentId,
        planFingerprint: intent.planFingerprint,
        confirmed: true,
      }),
    });
    model.savedPackages = new Set(model.selected);
    model.savedOptions = JSON.parse(JSON.stringify(model.options));
    clearManagedApplyIntent();
    updateChangeState();
    showToast(`Записано ${result.filesWritten} керовані файли; активацію не виконано.`);
  } catch (error) {
    clearManagedApplyIntent();
    showToast(error.message, true);
    updateChangeState();
  }
}

async function save() {
  if (!model.localWriteEnabled && model.helper?.managedWriteEnabled === true) {
    await prepareManagedSave();
    return;
  }
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
    model.savedOptions = JSON.parse(JSON.stringify(model.options));
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
    ui.appVersion.textContent = `v${config.version || "alpha"}`;
    ui.appVersion.title = `${config.releaseChannel || "alpha"} release`;
    model.localWriteEnabled = config.localWriteEnabled !== false;
    if (!model.localWriteEnabled) {
      ui.saveButton.title = "Локальне збереження вимкнено в режимі лише читання";
      ui.drawerSaveButton.title = "Локальне збереження вимкнено в режимі лише читання";
    }
    const [catalog, guidance, presets, settingsCatalog, driverProfilesRaw, state, system, adoption, helper, buildPreview, homeManager, homeBuildPreview, generations] = await Promise.all([
      api("/api/catalog"),
      api("/api/catalog-guidance"),
      api("/api/presets"),
      api("/api/settings-catalog"),
      api("/api/driver-profiles"),
      api("/api/state"),
      api("/api/system"),
      api("/api/adoption"),
      api("/api/helper"),
      api("/api/build-preview"),
      api("/api/home-manager"),
      api("/api/home-manager/build-preview"),
      api("/api/generations"),
    ]);
    model.catalog = catalog;
    model.catalogGuidance = NcmCatalog.normalizeCatalogGuidance(guidance);
    model.presets = presets;
    model.settingsCatalog = settingsCatalog;
    model.driverProfiles = NcmSettings.normalizeDriverProfiles(
      driverProfilesRaw,
      settingsCatalog,
    );
    model.state = state;
    model.options = NcmSettings.normalizeOptions(JSON.parse(JSON.stringify(state.options || {})));
    model.savedOptions = JSON.parse(JSON.stringify(model.options));
    model.homeManager = homeManager;
    model.generations = generations;
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
          tags: ["наявний"],
          scopes: ["system"],
        });
      }
    }
    model.selected = new Set(state.packages);
    model.savedPackages = new Set(state.packages);
    initializeHomePackageSelections();
    renderSystemTarget(system);
    renderHelperStatus(helper);
    renderAdoptionPlan(adoption);
    renderBuildPreview(buildPreview);
    if (activeBuildStatuses.has(buildPreview.status)) pollBuildPreview();
    renderHomeBuildPreview(homeBuildPreview);
    if (activeBuildStatuses.has(homeBuildPreview.status)) pollHomeBuildPreview();
    buildFilters();
    buildSettingsFilters();
    buildServicesFilters();
    buildDriversFilters();
    renderPresets();
    renderCatalog();
    renderSettings();
    renderServices();
    renderDrivers();
    renderHomeManager();
    renderGenerations();
    updateChangeState();
    void refreshEffectiveSettings();
    void refreshCatalogCompatibility();
  } catch (error) {
    showToast(`Не вдалося завантажити стан: ${error.message}`, true);
  }
}

ui.search.addEventListener("input", renderCatalog);
ui.refreshCatalogCompatibility.addEventListener("click", refreshCatalogCompatibility);
ui.importProfileButton.addEventListener("click", () => ui.profileFileInput.click());
ui.exportProfileButton.addEventListener("click", exportProfile);
ui.profileFileInput.addEventListener("change", importProfileFile);
ui.settingsSearch.addEventListener("input", renderSettings);
ui.servicesSearch.addEventListener("input", renderServices);
ui.homeManagerPackageSearch.addEventListener("input", renderHomeManagerPackages);
ui.programsNav.addEventListener("click", () => showPage("programs"));
ui.settingsNav.addEventListener("click", () => showPage("settings"));
ui.servicesNav.addEventListener("click", () => showPage("services"));
ui.driversNav.addEventListener("click", () => showPage("drivers"));
ui.homeManagerNav.addEventListener("click", () => showPage("home-manager"));
ui.generationsNav.addEventListener("click", () => showPage("generations"));
ui.refreshGenerations.addEventListener("click", refreshGenerations);
ui.homeManagerPreviewButton.addEventListener("click", openHomePreview);
ui.homeManagerAdoptionButton.addEventListener("click", openHomeAdoption);
ui.closeHomePreview.addEventListener("click", closeHomePreview);
ui.closeHomePreviewFooter.addEventListener("click", closeHomePreview);
ui.homePreviewBackdrop.addEventListener("click", closeHomePreview);
ui.homePreviewDiffTab.addEventListener("click", () => { model.homePreviewMode = "diff"; renderHomePreview(); });
ui.homePreviewSourceTab.addEventListener("click", () => { model.homePreviewMode = "source"; renderHomePreview(); });
ui.closeHomeAdoption.addEventListener("click", closeHomeAdoption);
ui.closeHomeAdoptionFooter.addEventListener("click", closeHomeAdoption);
ui.homeAdoptionBackdrop.addEventListener("click", closeHomeAdoption);
ui.validateHomeAdoptionButton.addEventListener("click", validateHomeAdoption);
ui.startHomeBuildPreviewButton.addEventListener("click", startHomeBuildPreview);
ui.cancelHomeBuildPreviewButton.addEventListener("click", cancelHomeBuildPreview);
ui.prepareHomeApplyButton.addEventListener("click", prepareHomeApply);
ui.commitHomeApplyButton.addEventListener("click", commitHomeApply);
ui.homeApplyConfirmation.addEventListener("change", updateHomeApplyControls);
ui.refreshEffectiveSettings.addEventListener("click", refreshEffectiveSettings);
ui.refreshServices.addEventListener("click", refreshEffectiveSettings);
ui.refreshDrivers.addEventListener("click", () => {
  void Promise.all([refreshCatalogCompatibility(), refreshEffectiveSettings()]);
});
ui.previewButton.addEventListener("click", openPreview);
ui.closePreview.addEventListener("click", closePreview);
ui.backdrop.addEventListener("click", closePreview);
ui.saveButton.addEventListener("click", save);
ui.drawerSaveButton.addEventListener("click", save);
ui.commitManagedApplyButton.addEventListener("click", commitManagedSave);
ui.managedApplyConfirmation.addEventListener("change", updateManagedApplyControls);
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
ui.commitTestedSystemButton.addEventListener("click", commitTestedSystem);
ui.rollbackCommittedSystemButton.addEventListener("click", rollbackCommittedSystem);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && ui.drawer.classList.contains("open")) closePreview();
  if (event.key === "Escape" && ui.homePreviewDrawer.classList.contains("open")) closeHomePreview();
  if (event.key === "Escape" && ui.homeAdoptionDrawer.classList.contains("open")) closeHomeAdoption();
  if (event.key === "Escape" && ui.planDrawer.classList.contains("open")) closeAdoptionPlan();
  const activeSearch = ["drivers", "generations"].includes(model.page)
    ? null
    : model.page === "settings"
    ? ui.settingsSearch
    : model.page === "services"
    ? ui.servicesSearch
    : (model.page === "programs" ? ui.search : ui.homeManagerPackageSearch);
  if (!activeSearch) return;
  if (event.key === "/" && document.activeElement !== activeSearch) {
    event.preventDefault();
    activeSearch.focus();
  }
});

initialize();
