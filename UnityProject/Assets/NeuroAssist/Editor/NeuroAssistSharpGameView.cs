#if UNITY_EDITOR
using System;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore.Text;
using UnityEngine.UIElements;

// Editor-only correction of the Game View presentation, not the application UI.
// Unity exposes GameView as an internal type. Access is guarded and version-tolerant;
// if an editor member is unavailable, the ordinary dropdown/Scale controls still work.
[InitializeOnLoad]
public static class NeuroAssistSharpGameView
{
    private const BindingFlags InstanceFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    private const string AppliedKey = "NeuroAssist.NativeGameView.v2.Applied";
    private const string ResourcesPath = "Assets/NeuroAssist/Resources/";
    private static int attempts;

    static NeuroAssistSharpGameView()
    {
        EditorApplication.delayCall += ApplyOnceAfterImport;
    }

    private static void ApplyOnceAfterImport()
    {
        if (SessionState.GetBool(AppliedKey, false)) return;
        if (EditorApplication.isCompiling || EditorApplication.isUpdating)
        {
            EditorApplication.delayCall += ApplyOnceAfterImport;
            return;
        }
        // A Game window may not exist yet during layout deserialization.
        if (Apply(false) > 0) SessionState.SetBool(AppliedKey, true);
        else if (++attempts < 5) EditorApplication.delayCall += ApplyOnceAfterImport;
    }

    [MenuItem("NeuroAssist/Sharpness/Use native Game View resolution")]
    public static void UseNativeResolution()
    {
        if (Apply(true) > 0) SessionState.SetBool(AppliedKey, true);
    }

    private static int Apply(bool report)
    {
        Type type = FindGameViewType();
        if (type == null)
        {
            if (report) ShowFallback("тип GameView недоступен");
            return 0;
        }
        PropertyInfo lowResolution = type.GetProperty("lowResolutionForAspectRatios", InstanceFlags);
        MethodInfo snapZoom = type.GetMethod("SnapZoom", InstanceFlags, null, new[] { typeof(float) }, null);
        PropertyInfo minimumScale = type.GetProperty("minScale", InstanceFlags);
        if (lowResolution == null || !lowResolution.CanWrite || snapZoom == null || minimumScale == null)
        {
            if (report) ShowFallback("API Game View отличается от проверенного по исходникам Unity");
            return 0;
        }
        int changed = 0;
        foreach (UnityEngine.Object obj in Resources.FindObjectsOfTypeAll(type))
        {
            var view = obj as EditorWindow;
            if (view == null) continue;
            try
            {
                // Reversible, local editor preferences only. Aspect/resolution selection
                // and global Windows display scaling are deliberately left untouched.
                lowResolution.SetValue(view, false);
                float fitScale = Convert.ToSingle(minimumScale.GetValue(view));
                if (float.IsNaN(fitScale) || float.IsInfinity(fitScale) || fitScale <= 0f)
                    throw new InvalidOperationException("Game View ещё не имеет корректного размера");
                // Native 1:1 in Free Aspect. For a larger fixed resolution, preserve fit.
                snapZoom.Invoke(view, new object[] { Mathf.Min(1f, fitScale) });
                view.Repaint();
                changed++;
            }
            catch (Exception ex)
            {
                if (report) ShowFallback(ex.GetBaseException().Message);
            }
        }
        if (changed > 0)
        {
            EditorApplication.QueuePlayerLoopUpdate();
            if (report) Debug.Log("NeuroAssist: Low Resolution Aspect Ratios отключён; масштаб Game установлен в 1x либо Fit для фиксированного большого разрешения. Сцена и ProjectSettings не менялись.");
        }
        else if (report) ShowFallback("нет готовой открытой вкладки Game");
        return changed;
    }

    private static void ShowFallback(string reason)
    {
        Debug.LogWarning("NeuroAssist: автоматическая настройка Game View недоступна (" + reason + "). " +
            "Во вкладке Game откройте Free Aspect, снимите Low Resolution Aspect Ratios и установите Scale 1x. " +
            "Если флажок неактивен при DPI 100%, это нормально: понижения HiDPI-разрешения в этом случае нет.");
    }

    [MenuItem("NeuroAssist/Sharpness/Print rendering report")]
    public static void PrintReport()
    {
        var report = new StringBuilder("NeuroAssist — отчёт о чёткости\n");
        report.AppendLine("Unity: " + Application.unityVersion);
        report.AppendLine("Screen: " + Screen.width + " × " + Screen.height + " px; Play: " + EditorApplication.isPlaying);
        report.AppendLine("Editor pixelsPerPoint: " + EditorGUIUtility.pixelsPerPoint.ToString("F2"));
        Type gameView = FindGameViewType();
        if (gameView != null)
        {
            foreach (UnityEngine.Object view in Resources.FindObjectsOfTypeAll(gameView))
            {
                report.AppendLine("Game View:");
                AppendProperty(report, gameView, view, "lowResolutionForAspectRatios");
                AppendProperty(report, gameView, view, "backingScale");
                AppendProperty(report, gameView, view, "targetRenderSize");
                AppendProperty(report, gameView, view, "zoomAreaScale");
            }
        }
        foreach (string id in new[] { "calls", "mail", "browser", "status" })
        {
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(ResourcesPath + "icon_" + id + ".png");
            if (texture == null) { report.AppendLine("icon_" + id + ": НЕ НАЙДЕНА"); continue; }
            report.AppendLine(texture.name + ": " + texture.width + " × " + texture.height +
                "; mip levels=" + texture.mipmapCount + "; filter=" + texture.filterMode);
        }
        foreach (string name in new[] { "NeuroAssistRegularSDF", "NeuroAssistBoldSDF" })
        {
            var font = AssetDatabase.LoadAssetAtPath<FontAsset>(ResourcesPath + name + ".asset");
            if (font == null) { report.AppendLine(name + ": НЕ НАЙДЕН"); continue; }
            report.AppendLine(name + ": " + font.atlasRenderMode + "; " + font.atlasWidth + " × " + font.atlasHeight);
        }
        foreach (UIDocument doc in UnityEngine.Object.FindObjectsByType<UIDocument>(FindObjectsSortMode.None))
        {
            if (doc.panelSettings == null || doc.rootVisualElement == null ||
                doc.rootVisualElement.Q<VisualElement>("phone") == null) continue;
            var panel = doc.panelSettings;
            report.AppendLine("UI panel: " + panel.scaleMode + "; scale=" + panel.scale.ToString("F3") +
                "; targetTexture=" + (panel.targetTexture == null ? "screen overlay" : panel.targetTexture.name));
            report.AppendLine("Icon atlas filter installed: " + (panel.dynamicAtlasSettings.customFilter != null));
        }
        Debug.Log(report.ToString());
    }

    private static Type FindGameViewType()
    {
        // Unity's editor assembly split can differ between releases.
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type type = assembly.GetType("UnityEditor.GameView", false);
            if (type != null) return type;
        }
        return null;
    }

    private static void AppendProperty(StringBuilder output, Type type, object target, string name)
    {
        try
        {
            PropertyInfo property = type.GetProperty(name, InstanceFlags);
            output.AppendLine("  " + name + ": " + (property == null ? "API unavailable" : Convert.ToString(property.GetValue(target))));
        }
        catch (Exception ex) { output.AppendLine("  " + name + ": " + ex.GetBaseException().Message); }
    }
}
#endif
