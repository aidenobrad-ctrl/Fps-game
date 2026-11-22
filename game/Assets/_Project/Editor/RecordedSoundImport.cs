using UnityEditor;
using UnityEngine;

namespace Recoil.EditorTools
{
    /// <summary>
    /// Import settings for the recorded sounds under Resources/Audio: decompressed when loaded, so
    /// the game can read their samples (to pitch each gun's recording, muffle it through a
    /// suppressor and so on: see RecordedSounds), one channel, Vorbis on disk. Applied whatever a
    /// clip's .meta says, so a fresh copy of the project, or one opened in another Unity version,
    /// imports them right.
    /// </summary>
    public sealed class RecordedSoundImport : AssetPostprocessor
    {
        // Raised whenever the settings below change, so Unity imports the clips again.
        public override uint GetVersion() => 2;

        void OnPreprocessAudio()
        {
            if (!assetPath.Replace('\\', '/').Contains("/Resources/Audio/")) return;
            var importer = (AudioImporter)assetImporter;
            AudioImporterSampleSettings settings = importer.defaultSampleSettings;
            settings.loadType = AudioClipLoadType.DecompressOnLoad;
            settings.compressionFormat = AudioCompressionFormat.Vorbis;
            settings.quality = 0.8f;
            importer.defaultSampleSettings = settings;
            importer.forceToMono = true;
            importer.loadInBackground = false;
        }
    }
}
