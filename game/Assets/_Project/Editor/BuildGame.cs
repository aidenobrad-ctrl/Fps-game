using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Recoil.Client.Online;

namespace Recoil.EditorTools
{
    /// <summary>
    /// Builds the game as a Windows program, Builds/Recoil/Recoil.exe in the repository's top
    /// folder (beside the Unity project), with backend.txt (where it finds its backend) and a
    /// script that starts a dedicated server for matchmaking beside it.
    ///
    /// From the menu, Recoil ▸ Build ▸ Windows Game (.exe); or with Unity closed, from
    /// build.bat in the top folder, which runs <see cref="BuildWindowsFromCommandLine"/>.
    /// </summary>
    public static class BuildGame
    {
        const string DuelScene = "Assets/_Project/Scenes/Duel.unity";
        const string RangeScene = "Assets/_Project/Scenes/FiringRange.unity";
        public const string ExeName = "Recoil.exe";

        // The development keys from the backend's appsettings.Development.json: fine on your own PC, never anywhere real.
        const string DevFleetKey = "development-only-fleet-key-do-not-use-anywhere-real";
        const string DevTicketKey = "development-only-ticket-key-do-not-use-anywhere-real";

        /// <summary>Where the build goes: Builds/Recoil in the folder that holds the Unity project.</summary>
        public static string OutputFolder => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "Builds", "Recoil"));

        [MenuItem("Recoil/Build/Windows Game (.exe)", priority = 0)]
        static void BuildFromMenu()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            string exe = BuildWindows(out string why);
            if (exe != null)
            {
                EditorUtility.RevealInFinder(exe);
                EditorUtility.DisplayDialog("Recoil", "Built " + exe + "\n\nDouble-click Recoil.exe to play. Copy the whole Recoil folder to give the game to someone.", "OK");
            }
            else
            {
                EditorUtility.DisplayDialog("Recoil", "The build did not finish:\n\n" + why + "\n\nThe Console has the details.", "OK");
            }
        }

        [MenuItem("Recoil/Build/Open Builds Folder", priority = 1)]
        static void OpenBuildsFolder()
        {
            Directory.CreateDirectory(OutputFolder);
            EditorUtility.RevealInFinder(OutputFolder);
        }

        /// <summary>
        /// For build.bat: Unity.exe -batchmode -quit -projectPath game -executeMethod
        /// Recoil.EditorTools.BuildGame.BuildWindowsFromCommandLine. Quits Unity with 0 when the
        /// build worked and 1 when it did not, with the reason in the log.
        /// </summary>
        public static void BuildWindowsFromCommandLine()
        {
            string exe = null, why;
            try
            {
                exe = BuildWindows(out why);
            }
            catch (Exception e)
            {
                why = e.ToString();
            }
            if (exe != null) Debug.Log("RECOIL BUILD SUCCEEDED: " + exe);
            else Debug.LogError("RECOIL BUILD FAILED: " + why);
            EditorApplication.Exit(exe != null ? 0 : 1);
        }

        /// <summary>Builds the game for 64-bit Windows. Returns the .exe's path, or null and why not.</summary>
        public static string BuildWindows(out string why)
        {
            // The same checks as opening the project: above all the render pipeline, without which
            // every model and effect in the built game would be drawn wrong.
            ProjectDoctor.Run(firstOpen: false);
            if (GraphicsSettings.defaultRenderPipeline == null)
            {
                why = "no render pipeline is set (Edit > Project Settings > Graphics > Default Render Pipeline should be " +
                      "Assets/_Project/Rendering/PB_URP_Asset). Run Recoil > Run Project Doctor and build again.";
                return null;
            }
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Standalone, BuildTarget.StandaloneWindows64))
            {
                why = "this Unity has no Windows Build Support. In Unity Hub: Installs, the cog by 6000.3.29f1, Add modules, " +
                      "tick Windows Build Support (Mono), Install, then build again.";
                return null;
            }

            var scenes = new List<string>();
            foreach (string scene in new[] { DuelScene, RangeScene })
            {
                if (File.Exists(scene)) scenes.Add(scene);
            }
            if (!scenes.Contains(DuelScene))
            {
                why = DuelScene + " is missing, and the game starts in it. Run Recoil > Rebuild Duel Scene and build again.";
                return null;
            }

            string folder = OutputFolder;
            Directory.CreateDirectory(folder);
            string exe = Path.Combine(folder, ExeName);
            Debug.Log("Recoil: building " + exe + " from " + string.Join(", ", scenes) + "...");
            BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = scenes.ToArray(),
                locationPathName = exe,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None,
            });
            BuildSummary summary = report.summary;
            if (summary.result != BuildResult.Succeeded)
            {
                why = Reason(report);
                return null;
            }

            WriteBeside(folder);
            Debug.Log("Recoil: built " + exe + " (" + summary.totalSize / (1024 * 1024) + " MB) in " + summary.totalTime.TotalSeconds.ToString("0") + " s.");
            why = null;
            return exe;
        }

        /// <summary>The build's own error messages, or its result if it gave none.</summary>
        static string Reason(BuildReport report)
        {
            var errors = new StringBuilder();
            int count = 0;
            foreach (BuildStep step in report.steps)
            {
                foreach (BuildStepMessage message in step.messages)
                {
                    if (message.type != LogType.Error && message.type != LogType.Exception) continue;
                    if (count++ < 8) errors.AppendLine(message.content);
                }
            }
            return count > 0 ? errors.ToString().Trim() : "the build ended as " + report.summary.result + ".";
        }

        /// <summary>The files that go with the .exe: where the backend is, and how to start a dedicated server.</summary>
        static void WriteBeside(string folder)
        {
            // Never overwritten: whoever edited it to point at a backend online keeps their address.
            string backend = Path.Combine(folder, GameServices.BackendFileName);
            if (!File.Exists(backend))
            {
                File.WriteAllText(backend,
                    GameServices.DefaultBackendUrl + "\r\n" +
                    "# Where this copy of the game finds its backend: accounts, matchmaking, friends and parties.\r\n" +
                    "# The first line is the address. http://localhost:5080 is the backend on this PC\r\n" +
                    "# (start-backend.bat in the recoil folder starts it). To play through a backend online,\r\n" +
                    "# put its address on the first line instead, for example https://recoil.example.com\r\n");
            }

            File.WriteAllText(Path.Combine(folder, "Start matchmaking server.bat"),
                "@echo off\r\n" +
                "rem A dedicated game server for Find Match, offered to the backend on this PC.\r\n" +
                "rem Start the backend first: start-backend.bat in the recoil folder.\r\n" +
                "cd /d \"%~dp0\"\r\n" +
                "set RECOIL_FLEET_KEY=" + DevFleetKey + "\r\n" +
                "set RECOIL_TICKET_KEY=" + DevTicketKey + "\r\n" +
                "echo A matchmaking server is running, with no window of its own. Its log is server.log in this folder.\r\n" +
                "echo Close this window to stop it; if it keeps running, end Recoil.exe in Task Manager.\r\n" +
                "\"" + ExeName + "\" -batchmode -nographics -server -fleet " + GameServices.DefaultBackendUrl + " -public-address 127.0.0.1 -logFile server.log\r\n");
        }
    }
}
