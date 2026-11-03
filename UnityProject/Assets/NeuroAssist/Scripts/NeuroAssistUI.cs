using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using UnityEngine.TextCore.Text;

// Presentation only. NeuroAssistClient remains the single source of EEG/mode state.
[DisallowMultipleComponent]
public class NeuroAssistUI : MonoBehaviour
{
    private NeuroAssistClient client;
    private GameObject documentHost;
    private UIDocument document;
    private PanelSettings runtimePanel;
    private VisualElement root, phoneBody, phoneDock, diagnosticPanel, phoneSide;
    private VisualElement probabilityBar, diagnosticsBox, explanationBox, modeCard;
    private Label headerStatus, sourceStatus, predictionLabel, probabilityLabel, modeLabel, modeSub, diagLabel;
    private Button autoButton, modeButton, compactButton, detailsButton;
    private FontAsset regularFont, boldFont;
    private float nextRefresh;
    private bool previousFocus, previousManual, diagnosticsShown, compact, panelOpen;
    private int screenWidth, screenHeight;
    private string currentPage = "home";
    private string lastAction = "Интерфейс готов к работе";
    private readonly Dictionary<string, Texture2D> icons = new Dictionary<string, Texture2D>();
    private static readonly string[] Names = { "Звонки", "Сообщения", "Почта", "Календарь", "Документы", "Браузер", "Контакты", "Задачи" };
    private static readonly string[] IconIds = { "calls", "messages", "mail", "calendar", "documents", "browser", "contacts", "tasks" };
    private static readonly int[] Badges = { 0, 3, 5, 0, 0, 0, 0, 4 };

    void Start()
    {
        client = GetComponent<NeuroAssistClient>();
        var panel = Resources.Load<PanelSettings>("NeuroAssistPanel");
        var style = Resources.Load<StyleSheet>("NeuroAssistStyle");
        regularFont = Resources.Load<FontAsset>("NeuroAssistRegularSDF");
        boldFont = Resources.Load<FontAsset>("NeuroAssistBoldSDF");
        if (client == null || panel == null || style == null || regularFont == null || boldFont == null)
        {
            Debug.LogError("NeuroAssist: UI assets не готовы. Остановите Play и выберите NeuroAssist > Repair UI assets.");
            return;
        }
        // Use an editor-created asset for TextCore initialization, then clone it so resizing
        // Game View never dirties the user's PanelSettings asset.
        runtimePanel = Instantiate(panel);
        runtimePanel.name = "NeuroAssist runtime panel";
        runtimePanel.scaleMode = PanelScaleMode.ConstantPixelSize;
        runtimePanel.scale = 1f;
        // Icons have their own mip chains. A non-mipmapped dynamic atlas would
        // discard that minification filtering, so keep only these textures out.
        var atlasSettings = runtimePanel.dynamicAtlasSettings;
        atlasSettings.customFilter = PreserveIconMipmaps;
        runtimePanel.dynamicAtlasSettings = atlasSettings;
        documentHost = new GameObject("NeuroAssist UI Toolkit (runtime)");
        documentHost.SetActive(false);
        document = documentHost.AddComponent<UIDocument>();
        document.panelSettings = runtimePanel;
        document.sortingOrder = 20;
        documentHost.SetActive(true);
        root = document.rootVisualElement;
        if (root == null)
        {
            Debug.LogError("NeuroAssist: UIDocument не создал корневой элемент.");
            return;
        }
        root.Clear();
        root.styleSheets.Add(style);
        root.AddToClassList("root");
        root.style.unityFontDefinition = new StyleFontDefinition(regularFont);

        var halo = Div("ambient-halo"); halo.pickingMode = PickingMode.Ignore; root.Add(halo);
        var frame = Div("frame"); root.Add(frame);
        var top = Div("topbar"); frame.Add(top);
        var branding = Div("branding"); top.Add(branding);
        branding.Add(Text("NEUROASSIST", "brand", true));
        branding.Add(Text("Рабочий день. В вашем ритме.", "sub-brand"));
        var topActions = Div("top-actions"); top.Add(topActions);
        headerStatus = Text("Ожидание EEG", "top-status"); headerStatus.pickingMode = PickingMode.Position; topActions.Add(headerStatus);
        compactButton = ActionButton("Диагностика", "compact-button", () =>
        {
            panelOpen = !panelOpen; ApplyPresentation();
        });
        topActions.Add(compactButton);

        var dashboard = Div("dashboard"); frame.Add(dashboard);
        phoneSide = Div("phone-side"); dashboard.Add(phoneSide);
        var phoneShadow = Div("phone-shadow"); phoneShadow.pickingMode = PickingMode.Ignore; phoneSide.Add(phoneShadow);
        var phone = Div("phone-outer"); phone.name = "phone"; phoneSide.Add(phone);
        var inner = Div("phone-inner"); phone.Add(inner);
        var status = Div("status-line"); inner.Add(status);
        status.Add(Text("9:41", "status-time", true));
        var island = Div("dynamic-island"); island.Add(Div("camera-lens")); status.Add(island);
        status.Add(Icon("status", "status-icons"));
        // No ScrollView on home screens. The complete design scales as one panel.
        phoneBody = Div("phone-content"); phoneBody.name = "phone-content"; inner.Add(phoneBody);
        phoneDock = Div("dock"); inner.Add(phoneDock);
        AddDockButton("calls", "Звонки"); AddDockButton("mail", "Почта");
        AddDockButton("browser", "Браузер"); AddDockButton("camera", "Камера");
        var homeArea = Div("home-indicator-area"); homeArea.Add(Div("home-indicator")); inner.Add(homeArea);

        BuildDiagnostics(dashboard);
        frame.Add(Text("Учебный прототип · EEGMAT · классификация условий эксперимента, не измерение усталости", "footer"));
        UpdateScale();
        RenderPhone();
        Refresh(true);
    }

    private void BuildDiagnostics(VisualElement dashboard)
    {
        diagnosticPanel = Div("panel"); diagnosticPanel.name = "diagnostics"; dashboard.Add(diagnosticPanel);
        var cap = Div("panel-cap"); diagnosticPanel.Add(cap);
        cap.Add(Div("accent-mark")); cap.Add(Text("АДАПТАЦИЯ В РЕАЛЬНОМ ВРЕМЕНИ", "panel-eyebrow", true));
        diagnosticPanel.Add(Text("Нейроадаптация", "panel-title", true));
        diagnosticPanel.Add(Text("Распознавание условий эксперимента\nи адаптация рабочего интерфейса.", "panel-subtitle"));
        diagnosticPanel.Add(Div("divider"));
        diagnosticPanel.Add(Text("ИСТОЧНИК · EEG / EDF", "panel-label", true));
        sourceStatus = Text("Ожидание подключения", "panel-value", true); sourceStatus.pickingMode = PickingMode.Position; diagnosticPanel.Add(sourceStatus);
        predictionLabel = Text("Модель: ожидание данных", "prediction-text"); diagnosticPanel.Add(predictionLabel);
        var probLine = Div("prob-line"); diagnosticPanel.Add(probLine);
        probLine.Add(Text("Вероятность\nарифметической задачи", "prob-description"));
        probabilityLabel = Text("—", "prob-number", true); probLine.Add(probabilityLabel);
        var track = Div("bar-track"); diagnosticPanel.Add(track);
        probabilityBar = Div("bar-fill"); probabilityBar.style.width = Length.Percent(0); track.Add(probabilityBar);
        modeCard = Div("mode-card"); diagnosticPanel.Add(modeCard);
        modeLabel = Text("Полный интерфейс", "mode-title", true); modeCard.Add(modeLabel);
        modeSub = Text("Автоматическое управление", "mode-sub"); modeCard.Add(modeSub);
        var buttons = Div("button-row"); diagnosticPanel.Add(buttons);
        autoButton = ActionButton("Ручное управление", "panel-button", () =>
        {
            if (client.IsManual) client.RestoreAutomaticMode(); else client.HoldCurrentModeManually();
            Refresh(true);
        });
        buttons.Add(autoButton);
        modeButton = ActionButton("Концентрация", "panel-button-primary", () =>
        {
            client.SetFocusManually(!client.IsFocus);
            lastAction = client.IsFocus ? "Включена концентрация" : "Включён полный режим";
            Refresh(true);
        });
        buttons.Add(modeButton);
        explanationBox = Div("explanation-box"); diagnosticPanel.Add(explanationBox);
        AddInfo(explanationBox, "01", "Четыре главных приложения", "Крупные кнопки и спокойная сетка 2 × 2.");
        AddInfo(explanationBox, "02", "Уведомления собраны вместе", "Меньше отвлечений. Всё доступно по нажатию.");
        diagnosticsBox = Div("diagnostic-details"); diagnosticPanel.Add(diagnosticsBox);
        diagnosticsBox.style.display = DisplayStyle.None;
        diagLabel = Text("Нет полученных EEG-окон", "diagnostic-summary"); diagLabel.pickingMode = PickingMode.Position; diagnosticPanel.Add(diagLabel);
        detailsButton = ActionButton("Подробнее об EEG   ›", "details-button", () =>
        {
            diagnosticsShown = !diagnosticsShown;
            diagnosticsBox.style.display = diagnosticsShown ? DisplayStyle.Flex : DisplayStyle.None;
            explanationBox.style.display = diagnosticsShown ? DisplayStyle.None : DisplayStyle.Flex;
            detailsButton.text = diagnosticsShown ? "Скрыть подробности   ‹" : "Подробнее об EEG   ›";
            UpdateDiagnostics();
        });
        diagnosticPanel.Add(detailsButton);
    }

    void Update()
    {
        if (document == null || client == null || phoneBody == null) return;
        if (screenWidth != Screen.width || screenHeight != Screen.height) UpdateScale();
        if (Time.unscaledTime < nextRefresh && previousFocus == client.IsFocus && previousManual == client.IsManual) return;
        nextRefresh = Time.unscaledTime + .3f;
        Refresh(false);
    }

    private void UpdateScale()
    {
        screenWidth = Mathf.Max(1, Screen.width); screenHeight = Mathf.Max(1, Screen.height);
        compact = (float)screenWidth / screenHeight < 1.04f;
        // Design budgets include topbar, phone (874), footer and frame padding.
        // The smaller axis wins: no screen crop at either aspect ratio.
        float width = compact ? 480f : 1040f;
        runtimePanel.scale = Mathf.Max(.01f, Mathf.Min(screenWidth / width, screenHeight / 1000f));
        ApplyPresentation();
    }

    private void ApplyPresentation()
    {
        root.EnableInClassList("compact", compact);
        compactButton.style.display = compact ? DisplayStyle.Flex : DisplayStyle.None;
        compactButton.text = panelOpen ? "К телефону" : "Диагностика";
        phoneSide.style.display = compact && panelOpen ? DisplayStyle.None : DisplayStyle.Flex;
        diagnosticPanel.style.display = !compact || panelOpen ? DisplayStyle.Flex : DisplayStyle.None;
    }

    private void Refresh(bool force)
    {
        if (client == null || phoneBody == null) return;
        bool focus = client.IsFocus;
        if (force || focus != previousFocus) RenderPhone();
        previousFocus = focus; previousManual = client.IsManual;
        bool connected = client.Status == "Воспроизведение ЭЭГ" || client.Status == "Подключено";
        headerStatus.text = connected ? "EEG подключён" : "Нет связи с EEG";
        headerStatus.EnableInClassList("offline", !connected);
        headerStatus.tooltip = client.Status;
        sourceStatus.text = client.Status; sourceStatus.tooltip = client.Status;
        probabilityLabel.text = client.Windows == 0 ? "—" : client.Probability.ToString("F2");
        probabilityBar.style.width = Length.Percent(Mathf.Clamp01(client.Probability) * 100f);
        predictionLabel.text = "Модель: " + (client.Prediction == "arithmetic" ? "arithmetic · задача" : client.Prediction == "rest" ? "rest · покой" : "ожидание данных");
        modeLabel.text = focus ? "Режим концентрации" : "Полный интерфейс";
        modeCard.EnableInClassList("mode-focus", focus);
        modeSub.text = client.IsManual ? "Ручной выбор · автоматика приостановлена" : "Автоматически · защита от колебаний";
        autoButton.text = client.IsManual ? "Вернуть автоматику" : "Ручное управление";
        modeButton.text = focus ? "Полный режим" : "Концентрация";
        diagLabel.text = "EEG-окон: " + client.Windows + "  ·  Совпадений: " + client.CorrectWindows + "/" + client.LabelledWindows;
        diagLabel.tooltip = "Совпадения с известной меткой записи. Последнее действие: " + lastAction;
        if (diagnosticsShown) UpdateDiagnostics();
    }

    private void UpdateDiagnostics()
    {
        if (diagnosticsBox == null) return;
        diagnosticsBox.Clear();
        var edf = Text("EDF: " + client.Recording, "diagnostic-file"); edf.tooltip = client.Recording; edf.pickingMode = PickingMode.Position; diagnosticsBox.Add(edf);
        diagnosticsBox.Add(Text("Условие записи: " + client.ExperimentalCondition, "diagnostic-text"));
        diagnosticsBox.Add(Text("RMS: " + client.SignalRms.ToString("F1") + " мкВ", "diagnostic-text"));
        diagnosticsBox.Add(Text("Метка записи служит для контроля,\nа не для переключения интерфейса.", "diagnostic-note"));
    }

    private void RenderPhone()
    {
        phoneBody.Clear();
        phoneDock.style.display = currentPage == "home" && !client.IsFocus ? DisplayStyle.Flex : DisplayStyle.None;
        phoneBody.EnableInClassList("focus-content", currentPage == "home" && client.IsFocus);
        if (currentPage != "home") { RenderPage(); return; }
        if (client.IsFocus) RenderFocusHome(); else RenderFullHome();
    }

    private void RenderFullHome()
    {
        var banner = Div("work-banner"); phoneBody.Add(banner);
        banner.Add(Icon("work", "banner-icon"));
        var title = Div("banner-text"); banner.Add(title);
        title.Add(Text("Рабочий телефон", "banner-title", true));
        title.Add(Text("Компания · Менеджер проекта", "banner-subtitle"));
        var avatar = Div("banner-avatar"); avatar.Add(Text("АС", "avatar-text")); banner.Add(avatar);
        var grid = Div("app-grid-full"); grid.name = "full-grid"; phoneBody.Add(grid);
        for (int row = 0; row < 2; row++)
        {
            var line = Div("app-row"); grid.Add(line);
            for (int col = 0; col < 4; col++)
            {
                int i = row * 4 + col; string target = Names[i];
                var slot = ActionButton(null, "app-slot", () => OpenPage(target)); slot.tooltip = target;
                slot.Add(IconWithBadge(IconIds[i], "app-icon", Badges[i]));
                slot.Add(Text(target, "app-caption")); line.Add(slot);
            }
        }
        var section = Div("section-row"); phoneBody.Add(section);
        section.Add(Text("Недавние уведомления", "section-title", true));
        section.Add(ActionButton("Все ›", "link", () => OpenPage("Уведомления")));
        AddNotification(phoneBody, "mail", "Почта · 5 мин назад", "Коммерческое предложение", "Коллеги, обновила документ.\nПосмотрите, пожалуйста, до конца дня.");
        AddNotification(phoneBody, "calendar", "Календарь · 15 мин назад", "Встреча с командой", "14:30–15:30\nПереговорная 3 · третий этаж");
        AddNotification(phoneBody, "messages", "Сообщения · 27 мин назад", "Алексей Петров", "Материалы к презентации готовы?\nОбсудим несколько моментов.");
    }

    private void RenderFocusHome()
    {
        var heading = Div("focus-heading-row"); phoneBody.Add(heading);
        var greeting = Div(); heading.Add(greeting);
        greeting.Add(Text("Доброе утро,", "focus-greeting"));
        greeting.Add(Text("Алексей", "focus-name", true));
        var back = ActionButton(null, "focus-return", () =>
        {
            client.SetFocusManually(false); lastAction = "Открыт полный режим"; Refresh(true);
        });
        back.Add(Icon("allapps", "return-icon")); back.Add(Text("Полный режим", "return-label", true)); back.Add(Text("›", "chevron")); heading.Add(back);
        phoneBody.Add(Text("Сосредоточьтесь на главном.\nВсё остальное подождёт.", "focus-subtitle"));
        var grid = Div("focus-grid"); grid.name = "focus-grid"; phoneBody.Add(grid);
        for (int row = 0; row < 2; row++)
        {
            var line = Div("focus-row"); grid.Add(line);
            if (row == 1) line.AddToClassList("focus-row-last");
            for (int col = 0; col < 2; col++)
            {
                int i = row * 2 + col; string target = Names[i];
                var tile = ActionButton(null, "focus-tile", () => OpenPage(target)); tile.tooltip = target;
                if (col == 0) tile.AddToClassList("tile-first");
                tile.Add(IconWithBadge(IconIds[i], "focus-tile-icon", Badges[i]));
                tile.Add(Text(target, "focus-caption", true)); line.Add(tile);
            }
        }
        var group = ActionButton(null, "focus-notification", () => OpenPage("Уведомления"));
        group.Add(Icon("notifications", "focus-notification-icon"));
        var copy = Div("notification-copy"); group.Add(copy);
        copy.Add(Text("6 уведомлений\nобъединены", "focus-notification-title", true));
        copy.Add(Text("Сообщения, письма\nи события — в одном месте", "focus-notification-sub"));
        group.Add(Text("›", "chevron")); phoneBody.Add(group);
        var all = ActionButton(null, "allapps-button", () => OpenPage("Все приложения"));
        all.Add(Icon("allapps", "allapps-icon")); all.Add(Text("Все приложения", "allapps-label", true)); all.Add(Text("›", "chevron")); phoneBody.Add(all);
    }

    private void RenderPage()
    {
        string page = currentPage;
        phoneBody.Add(ActionButton("‹  На главный экран", "phone-page-back", () => { currentPage = "home"; RenderPhone(); }));
        phoneBody.Add(Text(page, "phone-page-title", true));
        phoneBody.Add(Text(page == "Все приложения" ? "Все рабочие инструменты под рукой" : "Рабочее пространство · демонстрация", "phone-page-sub"));
        if (page == "Все приложения")
        {
            // Eight rows fit without scrolling; back navigation stays visible above them.
            for (int i = 0; i < Names.Length; i++)
            {
                string target = Names[i]; var item = ActionButton(null, "directory-item", () => OpenPage(target));
                item.Add(Icon(IconIds[i], "directory-icon")); item.Add(Text(target, "directory-label", true)); item.Add(Text("›", "chevron")); phoneBody.Add(item);
            }
            return;
        }
        string[] items;
        if (page == "Уведомления") items = new[] { "Коммерческое предложение", "Встреча с командой", "Алексей · Материалы к презентации", "Обновление документа", "Ответ клиенту", "Напоминание о встрече" };
        else if (page == "Звонки" || page == "Контакты") items = new[] { "Руководитель проекта", "Алексей Петров", "Команда разработки" };
        else if (page == "Почта") items = new[] { "Коммерческое предложение", "Ответ клиенту", "План встречи" };
        else if (page == "Календарь") items = new[] { "14:30 · Встреча с командой", "17:00 · Подготовка отчёта" };
        else if (page == "Сообщения") items = new[] { "Алексей · Материалы к презентации", "Коллеги · Рабочие вопросы" };
        else items = new[] { "Текущая рабочая задача", "Недавняя активность", "Избранное" };
        var feedback = Text("Выберите запись, чтобы открыть подробности.", "page-feedback");
        foreach (string item in items)
        {
            var row = ActionButton(null, "phone-page-item", () =>
            {
                lastAction = "Открыто: " + item; feedback.text = item + "\nЗапись открыта в учебном прототипе."; Refresh(false);
            });
            row.Add(Text(item, "phone-page-item-label", true)); row.Add(Text("›", "chevron")); phoneBody.Add(row);
        }
        phoneBody.Add(feedback);
        if (page != "Уведомления") phoneBody.Add(ActionButton("Выполнить демодействие", "phone-page-primary", () =>
        {
            lastAction = "Действие в разделе «" + page + "» выполнено";
            feedback.text = "Готово. Демонстрационное действие выполнено."; Refresh(false);
        }));
    }

    private void OpenPage(string page)
    {
        currentPage = page; lastAction = "Открыт раздел «" + page + "»"; RenderPhone(); Refresh(false);
    }

    private void AddDockButton(string id, string target)
    {
        var button = ActionButton(null, "dock-button", () => OpenPage(target)); button.tooltip = target;
        button.Add(Icon(id, "dock-image")); phoneDock.Add(button);
    }

    private void AddNotification(VisualElement parent, string icon, string meta, string title, string preview)
    {
        var card = ActionButton(null, "notification", () => OpenPage("Уведомления"));
        card.Add(Icon(icon, "notification-icon"));
        var copy = Div("notification-copy"); card.Add(copy);
        copy.Add(Text(meta, "notification-meta")); copy.Add(Text(title, "notification-title", true)); copy.Add(Text(preview, "notification-preview"));
        card.Add(Text("›", "notification-chevron")); parent.Add(card);
    }

    private void AddInfo(VisualElement parent, string number, string title, string description)
    {
        var row = Div("info-row"); parent.Add(row); row.Add(Text(number, "info-number", true));
        var copy = Div("info-copy"); row.Add(copy); copy.Add(Text(title, "info-title", true)); copy.Add(Text(description, "info-label"));
    }

    private VisualElement IconWithBadge(string id, string iconClass, int count)
    {
        var holder = Div("icon-holder"); holder.Add(Icon(id, iconClass));
        if (count > 0) holder.Add(Text(count.ToString(), iconClass == "focus-tile-icon" ? "badge badge-large" : "badge", true));
        return holder;
    }

    private static bool PreserveIconMipmaps(Texture2D texture, ref DynamicAtlasFilters filtersToApply)
    {
        return texture == null || !texture.name.StartsWith("icon_", StringComparison.Ordinal);
    }

    private Image Icon(string id, string className)
    {
        if (!icons.TryGetValue(id, out Texture2D texture)) { texture = Resources.Load<Texture2D>("icon_" + id); icons[id] = texture; }
        var image = new Image { image = texture, scaleMode = ScaleMode.ScaleToFit, pickingMode = PickingMode.Ignore };
        image.AddToClassList(className); return image;
    }

    private static VisualElement Div(string className = null)
    {
        var element = new VisualElement(); if (!string.IsNullOrEmpty(className)) element.AddToClassList(className); return element;
    }

    private Label Text(string content, string classes, bool bold = false)
    {
        var label = new Label(content) { pickingMode = PickingMode.Ignore, enableRichText = false };
        foreach (string cls in classes.Split(' ')) label.AddToClassList(cls);
        if (bold) label.style.unityFontDefinition = new StyleFontDefinition(boldFont);
        return label;
    }

    private Button ActionButton(string content, string className, Action click)
    {
        var button = new Button(click) { text = content ?? string.Empty };
        button.AddToClassList("na-button"); button.AddToClassList(className);
        button.style.unityFontDefinition = new StyleFontDefinition(regularFont);
        return button;
    }

    void OnDestroy()
    {
        if (documentHost != null) Destroy(documentHost);
        if (runtimePanel != null) Destroy(runtimePanel);
    }
}
