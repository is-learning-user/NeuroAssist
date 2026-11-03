#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class CreateNeuroAssistScene
{
    [MenuItem("NeuroAssist/Create demo scene")]
    public static void Create()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var cameraObject = new GameObject("Main Camera");
        cameraObject.tag = "MainCamera";
        var cam = cameraObject.AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(.96f,.96f,.97f);
        var manager = new GameObject("NeuroAssist Smartphone System");
        manager.AddComponent<NeuroAssistClient>();
        EditorSceneManager.SaveScene(scene, "Assets/NeuroAssist_Demo.unity");
        EditorUtility.DisplayDialog("NeuroAssist", "Smartphone UI scene created. Start RUN_DEMO_WINDOWS.bat and press Play. No 3D shaders.", "OK");
    }
}
#endif
