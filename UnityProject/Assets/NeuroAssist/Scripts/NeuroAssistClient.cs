using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Concurrent;
using System.Collections.Generic;
using UnityEngine;

public class NeuroAssistClient : MonoBehaviour
{
    [Serializable]
    private class WireMessage
    {
        public string schema, type, source, recording, predicted_condition, experimental_condition, meaning;
        public float p_task, duration_s, replay_time_s, rms_microvolts;
        public int window_index;
        public bool is_replay;
    }

    public string url = "ws://127.0.0.1:8765";
    public float enterThreshold = 0.68f;
    public float exitThreshold = 0.42f;
    public int consecutiveWindows = 2;

    private ClientWebSocket socket;
    private CancellationTokenSource cancellation;
    private readonly ConcurrentQueue<string> incoming = new ConcurrentQueue<string>();
    private readonly Queue<string> journal = new Queue<string>();

    private string status = "Ожидание сервера Python";
    private string recording = "—", experimentalCondition = "—", lastPrediction = "—";
    private float probability, signalRms;
    private int highCount, lowCount, windows, correctWindows, labelledWindows;
    private bool suggestedFocus, manualOverride, manualFocus, showDiagnostics;
    private string lastAction = "Экран загружен";


    private readonly Color bg = new Color(0.965f, 0.972f, 0.985f);
    private readonly Color ink = new Color(0.08f, 0.11f, 0.19f);
    private readonly Color muted = new Color(0.46f, 0.52f, 0.63f);
    private readonly Color white = new Color(1f, 1f, 1f);
    private readonly Color panel = new Color(0.985f, 0.989f, 0.995f);
    private readonly Color border = new Color(0.85f, 0.89f, 0.94f);
    private readonly Color accent = new Color(0.14f, 0.44f, 0.98f);
    private readonly Color accentSoft = new Color(0.90f, 0.95f, 1.0f);
    private readonly Color success = new Color(0.25f, 0.79f, 0.58f);
    private readonly Color successSoft = new Color(0.90f, 0.98f, 0.94f);
    private readonly Color chip = new Color(0.95f, 0.97f, 1.0f);
    private readonly Color shadow = new Color(0f, 0f, 0f, 0.10f);

    private bool FocusMode { get { return manualOverride ? manualFocus : suggestedFocus; } }

    void Awake()
    {
        if (GetComponent<NeuroAssistUI>() == null) gameObject.AddComponent<NeuroAssistUI>();
    }

    async void Start()
    {
        cancellation = new CancellationTokenSource();
        await ConnectLoop(cancellation.Token);
    }

    async Task ConnectLoop(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            ClientWebSocket current = null;
            try
            {
                current = new ClientWebSocket();
                socket = current;
                await current.ConnectAsync(new Uri(url), token);
                incoming.Enqueue("{\"type\":\"status_connected\"}");
                byte[] buffer = new byte[4096];
                var builder = new StringBuilder();
                while (current.State == WebSocketState.Open && !token.IsCancellationRequested)
                {
                    var result = await current.ReceiveAsync(new ArraySegment<byte>(buffer), token);
                    if (result.MessageType == WebSocketMessageType.Close) break;
                    builder.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                    if (builder.Length > 100000) { builder.Clear(); continue; }
                    if (result.EndOfMessage)
                    {
                        incoming.Enqueue(builder.ToString());
                        builder.Clear();
                    }
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception e) { if (!token.IsCancellationRequested) incoming.Enqueue("ERROR: " + e.Message); }
            finally { if (ReferenceEquals(socket, current)) socket = null; if (current != null) current.Dispose(); }
            try { await Task.Delay(1500, token); } catch (OperationCanceledException) { break; }
        }
    }

    void Update()
    {
        int n = 0; string json;
        while (n++ < 12 && incoming.TryDequeue(out json))
        {
            if (json.StartsWith("ERROR:")) { status = "Нет связи (повторное подключение)"; continue; }
            try
            {
                var msg = JsonUtility.FromJson<WireMessage>(json);
                if (msg.type == "status_connected") { status = "Подключено"; continue; }
                if (msg.type == "connected" || msg.type == "recording")
                {
                    recording = msg.recording;
                    experimentalCondition = msg.experimental_condition;
                    status = "Воспроизведение ЭЭГ";
                    if (msg.type == "recording") { highCount = 0; lowCount = 0; }
                    continue;
                }
                if (msg.type != "prediction" || msg.schema != "neuroassist.v1") continue;
                probability = Mathf.Clamp01(msg.p_task);
                windows++;
                lastPrediction = msg.predicted_condition;
                experimentalCondition = msg.experimental_condition;
                signalRms = msg.rms_microvolts;
                if (experimentalCondition == "rest" || experimentalCondition == "arithmetic")
                {
                    labelledWindows++;
                    if (lastPrediction == experimentalCondition) correctWindows++;
                }
                if (probability >= enterThreshold) { highCount++; lowCount = 0; }
                else if (probability <= exitThreshold) { lowCount++; highCount = 0; }
                else { highCount = 0; lowCount = 0; }
                if (!suggestedFocus && highCount >= consecutiveWindows) suggestedFocus = true;
                if (suggestedFocus && lowCount >= consecutiveWindows) suggestedFocus = false;
                journal.Enqueue(string.Format("{0:F0} c | p={1:F2} | {2}", msg.replay_time_s, probability, FocusMode ? "концентрация" : "полный"));
                while (journal.Count > 5) journal.Dequeue();
            }
            catch (Exception e) { status = "Ошибка сообщения: " + e.Message; }
        }
    }

    // UI Toolkit reads model state; network operations are independent of presentation.
    public float Probability { get { return probability; } }
    public string Status { get { return status; } }
    public string Recording { get { return recording; } }
    public string ExperimentalCondition { get { return experimentalCondition; } }
    public string Prediction { get { return lastPrediction; } }
    public float SignalRms { get { return signalRms; } }
    public int Windows { get { return windows; } }
    public int CorrectWindows { get { return correctWindows; } }
    public int LabelledWindows { get { return labelledWindows; } }
    public bool IsFocus { get { return FocusMode; } }
    public bool IsManual { get { return manualOverride; } }

    public void SetFocusManually(bool focus)
    {
        manualFocus = focus;
        manualOverride = true;
    }

    public void RestoreAutomaticMode()
    {
        manualOverride = false;
    }

    public void HoldCurrentModeManually()
    {
        manualFocus = FocusMode;
        manualOverride = true;
    }

    void OnDestroy()
    {
        if (cancellation != null) cancellation.Cancel();
        try { if (socket != null) { socket.Abort(); socket.Dispose(); } } catch { }
        if (cancellation != null) cancellation.Dispose();
    }
}
