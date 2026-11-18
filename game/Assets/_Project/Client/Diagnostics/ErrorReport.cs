using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Recoil.Client.Diagnostics
{
    /// <summary>
    /// Keeps the first errors of a session, each with where it came from, in a file:
    /// Logs/Recoil-errors.txt in the project folder when playing in the editor, or
    /// Recoil-errors.txt in the game's data folder in a built game. Each different error is
    /// written once, so a fault that repeats every frame cannot bury the one that caused it.
    ///
    /// While there are any, a small note in the corner of the screen (in the editor and in
    /// development builds) gives the first one and where the file is.
    /// </summary>
    public static class ErrorReport
    {
        const int MaxKept = 40;

        static readonly HashSet<string> Seen = new HashSet<string>();
        static readonly List<string> Kept = new List<string>();
        static string _path = "";
        static string _first = "";
        static int _total;

        /// <summary>Where the errors are written.</summary>
        public static string FilePath => _path;
        /// <summary>How many different errors there have been this session.</summary>
        public static int Distinct => Kept.Count;
        /// <summary>How many errors there have been this session, repeats included.</summary>
        public static int Total => _total;
        /// <summary>The first error's message, or empty.</summary>
        public static string First => _first;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Begin()
        {
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
            Seen.Clear();
            Kept.Clear();
            _first = "";
            _total = 0;
            try
            {
                string folder = Application.isEditor
                    ? Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Logs"))
                    : Application.persistentDataPath;
                Directory.CreateDirectory(folder);
                _path = Path.Combine(folder, "Recoil-errors.txt");
                File.WriteAllText(_path, "Recoil errors, " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
                                         " (each different error once, in the order they happened)\n\n");
            }
            catch (Exception)
            {
                _path = "";
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void ShowNote()
        {
            if (!Application.isEditor && !Debug.isDebugBuild) return;
            var go = new GameObject("Error Report") { hideFlags = HideFlags.HideInHierarchy };
            UnityEngine.Object.DontDestroyOnLoad(go);
            go.AddComponent<ErrorNote>();
        }

        static void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type != LogType.Error && type != LogType.Exception && type != LogType.Assert) return;
            _total++;
            string key = condition + "\n" + FirstLine(stackTrace);
            if (Kept.Count >= MaxKept || !Seen.Add(key)) return;

            string entry = "[" + DateTime.Now.ToString("HH:mm:ss") + "] " + type + ": " + condition + "\n" + stackTrace.TrimEnd() + "\n";
            Kept.Add(entry);
            if (Kept.Count == 1) _first = condition;
            if (_path.Length == 0) return;
            try
            {
                File.AppendAllText(_path, entry + "\n");
            }
            catch (Exception)
            {
                // Nowhere to write it: the console still has it.
            }
        }

        static string FirstLine(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            int end = text.IndexOf('\n');
            return end < 0 ? text : text.Substring(0, end);
        }
    }

    /// <summary>The note in the corner while there are errors.</summary>
    sealed class ErrorNote : MonoBehaviour
    {
        GUIStyle _style;

        void OnGUI()
        {
            if (ErrorReport.Distinct == 0) return;
            if (_style == null)
            {
                _style = new GUIStyle(GUI.skin.box)
                {
                    alignment = TextAnchor.UpperLeft,
                    wordWrap = true,
                    fontSize = 12,
                };
                _style.normal.textColor = new Color(1f, 0.85f, 0.8f);
            }
            string first = ErrorReport.First;
            if (first.Length > 220) first = first.Substring(0, 220) + "...";
            string text = ErrorReport.Total + " error(s), " + ErrorReport.Distinct + " different. First: " + first +
                          (ErrorReport.FilePath.Length > 0 ? "\nAll of them, with where they came from: " + ErrorReport.FilePath : "");
            GUI.Box(new Rect(8f, Screen.height - 74f, Mathf.Min(760f, Screen.width - 16f), 66f), text, _style);
        }
    }
}
