using UnityEngine;
using UnityEngine.Rendering;

namespace Recoil.Client.FiringRange
{
    /// <summary>
    /// Lighting and atmosphere for the range, set from code so the level looks the same
    /// whatever the scene's own lighting settings are and needs no light bake.
    /// </summary>
    public static class RangeEnvironment
    {
        static readonly Color Sky = new Color(0.56f, 0.7f, 0.86f);
        static readonly Color Horizon = new Color(0.66f, 0.74f, 0.82f);
        static readonly Color Ground = new Color(0.24f, 0.25f, 0.28f);

        public static void Apply(bool createSunLight)
        {
            RenderSettings.ambientMode = AmbientMode.Trilight;
            // Softer fill from the sky than before, so the sun models faces, folds and corners
            // instead of everything reading flat; ambient occlusion (the URP renderer) darkens the creases.
            RenderSettings.ambientSkyColor = new Color(0.5f, 0.57f, 0.68f);
            RenderSettings.ambientEquatorColor = new Color(0.4f, 0.41f, 0.44f);
            RenderSettings.ambientGroundColor = Ground;

            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = Horizon;
            RenderSettings.fogStartDistance = 70f;
            RenderSettings.fogEndDistance = 320f;

            if (!createSunLight) return;

            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            // A warm, strong sun a little lower in the sky: longer, clearer shadows.
            sun.color = new Color(1f, 0.94f, 0.84f);
            sun.intensity = 1.6f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(40f, -35f, 0f);
            RenderSettings.sun = sun;
        }

        public static void ConfigureCamera(Camera camera)
        {
            // Use the scene's skybox when it has one, otherwise a flat sky colour.
            camera.clearFlags = RenderSettings.skybox != null ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
            camera.backgroundColor = Sky;
            Visuals.GraphicsSetup.ConfigureCamera(camera);
        }
    }
}
