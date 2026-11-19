using System;

namespace Recoil.Client.Audio
{
    /// <summary>
    /// The sample work done on a recording before the game plays it: mixing to one channel,
    /// changing its rate or pitch, and making a gunshot sound suppressed or far away. Plain
    /// arrays in, plain arrays out, so it is tested without Unity.
    /// </summary>
    public static class RecordingProcessing
    {
        /// <summary>One channel from interleaved samples: the average of the channels.</summary>
        public static float[] ToMono(float[] interleaved, int channels)
        {
            if (channels <= 1) return (float[])interleaved.Clone();
            var mono = new float[interleaved.Length / channels];
            for (int i = 0; i < mono.Length; i++)
            {
                float sum = 0f;
                for (int c = 0; c < channels; c++) sum += interleaved[i * channels + c];
                mono[i] = sum / channels;
            }
            return mono;
        }

        /// <summary>
        /// Reads the input <paramref name="step"/> samples on for every sample out, with linear
        /// interpolation: 2 halves the length and raises the pitch an octave, 0.5 the reverse.
        /// Changing a clip's rate is the same thing, with step = rate in / rate out.
        /// </summary>
        public static float[] Resample(float[] input, double step)
        {
            if (input.Length < 2 || step <= 0) return (float[])input.Clone();
            int length = Math.Max(1, (int)((input.Length - 1) / step));
            var output = new float[length];
            for (int i = 0; i < length; i++)
            {
                double at = i * step;
                int k = (int)at;
                float t = (float)(at - k);
                output[i] = k + 1 < input.Length ? input[k] + (input[k + 1] - input[k]) * t : input[input.Length - 1];
            }
            return output;
        }

        /// <summary>Takes the top off a sound in place: two one-pole low passes at <paramref name="cutoff"/> Hz.</summary>
        public static void Muffle(float[] samples, float cutoff, int rate)
        {
            float a = 1f - (float)Math.Exp(-2.0 * Math.PI * cutoff / rate);
            float first = 0f, second = 0f;
            for (int i = 0; i < samples.Length; i++)
            {
                first += (samples[i] - first) * a;
                second += (first - second) * a;
                samples[i] = second;
            }
        }

        /// <summary>
        /// A recorded shot as it sounds through a suppressor: the blast muffled to a thud that
        /// dies within half a second, with the sharp click of the action left on top.
        /// </summary>
        public static float[] Suppress(float[] shot, int rate)
        {
            int length = Math.Min(shot.Length, (int)(0.55f * rate));
            var body = new float[length];
            Array.Copy(shot, body, length);
            Muffle(body, 900f, rate);

            var output = new float[length];
            float peak = 0f;
            for (int i = 0; i < length; i++)
            {
                float t = (float)i / rate;
                float decay = t < 0.03f ? 1f : (float)Math.Exp(-(t - 0.03f) / 0.09f);
                float click = shot[i] * (float)Math.Exp(-t / 0.004f) * 0.22f;
                output[i] = (body[i] * 1.8f + click) * decay;
                peak = Math.Max(peak, Math.Abs(output[i]));
            }
            FadeOut(output, 0.2f);
            if (peak > 0f)
            {
                float gain = 0.8f / peak;
                for (int i = 0; i < length; i++) output[i] *= gain;
            }
            return output;
        }

        /// <summary>Scales samples in place, keeping them inside full scale.</summary>
        public static void Gain(float[] samples, float gain)
        {
            for (int i = 0; i < samples.Length; i++) samples[i] = Math.Max(-1f, Math.Min(1f, samples[i] * gain));
        }

        /// <summary>Fades the last <paramref name="fraction"/> of a sound down to silence, in place.</summary>
        public static void FadeOut(float[] samples, float fraction)
        {
            int count = (int)(samples.Length * fraction);
            for (int i = 0; i < count; i++)
            {
                float x = (float)(i + 1) / count;
                samples[samples.Length - count + i] *= (float)Math.Pow(Math.Cos(x * Math.PI / 2), 2);
            }
        }
    }
}
