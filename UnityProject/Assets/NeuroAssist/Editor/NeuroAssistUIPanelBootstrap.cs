#if UNITY_EDITOR
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.TextCore.Text;
using UnityEngine.UIElements;

// Creates only the small local UI assets missing from the patch. Existing GUIDs are retained.
// Nothing here refreshes/reimports the project, touches a scene or changes EEG settings.
public static class NeuroAssistUIPanelBootstrap
{
    private const string Folder = "Assets/NeuroAssist/Resources/";
    private static int retries;

    [InitializeOnLoadMethod]
    private static void Init() { EditorApplication.delayCall += EnsureAsset; }

    [MenuItem("NeuroAssist/Repair UI assets")]
    public static void EnsureAsset()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode) return;
        if (EditorApplication.isCompiling || EditorApplication.isUpdating)
        {
            EditorApplication.delayCall += EnsureAsset; return;
        }
        var theme = AssetDatabase.LoadAssetAtPath<ThemeStyleSheet>(Folder + "NeuroAssistRuntimeTheme.tss");
        var regular = AssetDatabase.LoadAssetAtPath<Font>(Folder + "NeuroAssistRegular.ttf");
        var bold = AssetDatabase.LoadAssetAtPath<Font>(Folder + "NeuroAssistBold.ttf");
        if (theme == null || regular == null || bold == null)
        {
            if (retries++ < 5) EditorApplication.delayCall += EnsureAsset;
            else Debug.LogError("NeuroAssist: не все файлы патча импортированы. Повторите NeuroAssist > Repair UI assets после импорта.");
            return;
        }
        bool changed = false;
        EnsureFont(regular, "NeuroAssistRegularSDF", ref changed);
        EnsureFont(bold, "NeuroAssistBoldSDF", ref changed);
        var textSettings = AssetDatabase.LoadAssetAtPath<PanelTextSettings>(Folder + "NeuroAssistTextSettings.asset");
        if (textSettings == null)
        {
            textSettings = ScriptableObject.CreateInstance<PanelTextSettings>();
            textSettings.name = "NeuroAssistTextSettings";
            AssetDatabase.CreateAsset(textSettings, Folder + "NeuroAssistTextSettings.asset");
            changed = true;
        }
        var panel = AssetDatabase.LoadAssetAtPath<PanelSettings>(Folder + "NeuroAssistPanel.asset");
        if (panel == null)
        {
            panel = ScriptableObject.CreateInstance<PanelSettings>();
            AssetDatabase.CreateAsset(panel, Folder + "NeuroAssistPanel.asset");
            changed = true;
        }
        if (panel.themeStyleSheet != theme || panel.textSettings != textSettings ||
            panel.scaleMode != PanelScaleMode.ConstantPixelSize || panel.scale != 1f || panel.sortingOrder != 20)
        {
            panel.themeStyleSheet = theme;
            panel.textSettings = textSettings;
            panel.scaleMode = PanelScaleMode.ConstantPixelSize;
            panel.scale = 1f;
            panel.sortingOrder = 20;
            EditorUtility.SetDirty(panel); changed = true;
        }
        if (changed) AssetDatabase.SaveAssets();
    }

    private static FontAsset EnsureFont(Font source, string name, ref bool changed)
    {
        string path = Folder + name + ".asset";
        var existing = AssetDatabase.LoadAssetAtPath<FontAsset>(path);
        if (existing != null) return existing;
        var font = FontAsset.CreateFontAsset(source, 64, 8, GlyphRenderMode.SDFAA, 1024, 1024, AtlasPopulationMode.Dynamic, true);
        font.name = name;
        // Prewarm Latin, Cyrillic and the UI symbols once in Editor, not every Play.
        var chars = new StringBuilder();
        for (int c = 32; c <= 126; c++) chars.Append((char)c);
        for (int c = 0x400; c <= 0x45f; c++) chars.Append((char)c);
        chars.Append("–—‹›·×");
        font.TryAddCharacters(chars.ToString());
        AssetDatabase.CreateAsset(font, path);
        if (font.material != null)
        {
            font.material.name = name + " Material";
            AssetDatabase.AddObjectToAsset(font.material, font);
        }
        foreach (Texture2D atlas in font.atlasTextures)
        {
            if (atlas == null) continue;
            atlas.name = name + " Atlas";
            atlas.filterMode = FilterMode.Bilinear;
            AssetDatabase.AddObjectToAsset(atlas, font);
        }
        EditorUtility.SetDirty(font); changed = true;
        return font;
    }
}
#endif
