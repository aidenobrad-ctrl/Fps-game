using System;
using System.IO;
using UnityEngine;

namespace Recoil.Client.Online
{
    /// <summary>
    /// Unity keeps a game's saves in a folder named after its company and product. Builds made
    /// before the game was named Recoil saved under its working title, so the first time Recoil
    /// starts it copies anything from that folder that it does not have yet: loadouts, looks,
    /// and the saved sign-in. Nothing is overwritten and the old folder is left as it was.
    /// </summary>
    static class EarlierSaves
    {
        // The working title the game had while it was being built. Only the folder name matters.
        const string EarlierCompany = "Pulsebreak", EarlierProduct = "Pulsebreak";
        const string Marker = ".earlier-saves-copied";

        public static void Bring(string current)
        {
            try
            {
                if (string.IsNullOrEmpty(current) || File.Exists(Path.Combine(current, Marker))) return;
                string company = Path.GetDirectoryName(current);
                string top = company != null ? Path.GetDirectoryName(company) : null;
                if (top == null) return;
                string earlier = Path.Combine(top, EarlierCompany, EarlierProduct);
                Directory.CreateDirectory(current);
                if (Directory.Exists(earlier) && !string.Equals(Path.GetFullPath(earlier), Path.GetFullPath(current), StringComparison.OrdinalIgnoreCase))
                {
                    int copied = CopyMissing(earlier, current);
                    if (copied > 0) Debug.Log("Recoil: brought " + copied + " saved file(s) over from before the game was renamed.");
                }
                File.WriteAllText(Path.Combine(current, Marker), DateTime.UtcNow.ToString("o"));
            }
            catch (Exception error)
            {
                Debug.LogWarning("Recoil: could not bring over earlier saves (" + error.Message + "). They are still in the old folder.");
            }
        }

        static int CopyMissing(string from, string to)
        {
            int copied = 0;
            foreach (string file in Directory.GetFiles(from))
            {
                string target = Path.Combine(to, Path.GetFileName(file));
                if (File.Exists(target)) continue;
                File.Copy(file, target);
                copied++;
            }
            foreach (string folder in Directory.GetDirectories(from))
            {
                string name = Path.GetFileName(folder);
                if (name == "Unity") continue;      // the engine's own cache, not ours
                string target = Path.Combine(to, name);
                Directory.CreateDirectory(target);
                copied += CopyMissing(folder, target);
            }
            return copied;
        }
    }
}
