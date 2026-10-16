#pragma once

#include "Common.h"
#include <vector>

namespace ar
{
    // _apply_periodic_stutter_glitch_np in real time.
    // Every PERIODIC_STUTTER_SEC a short slice (STUTTER_OVERLAY_MS) of what was just
    // heard is repeated (1 + STUTTER_OVERLAY_REPEATS times); every PERIODIC_GLITCH_SEC a
    // GLITCH_OVERLAY_MS slice is bit-crushed by sample-and-hold (GLITCH_BITCRUSH_FACTOR)
    // and reversed half of the time. Events of the same type never fire back to back
    // when they collide, and they are blended in with CLEAN_FX_CROSSFADE_MS fades.
    class PeriodicFx
    {
    public:
        static constexpr double maxSliceSec = 0.5;
        static constexpr int maxReps = 8;

        struct Settings
        {
            float stutterEverySec = 33.0f, glitchEverySec = 67.0f;
            float stutterMs = 140.0f;
            int stutterReps = 2;
            float glitchMs = 90.0f;
            int crush = 6;
            float xfadeMs = 40.0f;
        };

        void prepare (double sr)
        {
            sampleRate = sr;
            histSize = (int) std::ceil (sr * maxSliceSec) + 1;
            hist[0].assign ((size_t) histSize, 0.0f);
            hist[1].assign ((size_t) histSize, 0.0f);
            const auto playCap = (size_t) (std::ceil (sr * maxSliceSec) * (maxReps + 1) + 1);
            play[0].assign (playCap, 0.0f);
            play[1].assign (playCap, 0.0f);
            microFade = msToSamples (sr, 2.0);
            reset();
        }

        void reset() noexcept
        {
            std::fill (hist[0].begin(), hist[0].end(), 0.0f);
            std::fill (hist[1].begin(), hist[1].end(), 0.0f);
            histPos = 0;
            playLen = playPos = 0;
            lastStutterK = lastGlitchK = -1;
            lastType = Type::none;
        }

        void setSettings (const Settings& s) noexcept { settings = s; }

        void process (float* L, float* R, int n, double songSecondsAtStart) noexcept
        {
            const double invSr = 1.0 / sampleRate;

            for (int i = 0; i < n; ++i)
            {
                hist[0][(size_t) histPos] = L[i];
                hist[1][(size_t) histPos] = R[i];
                if (++histPos >= histSize) histPos = 0;

                const double t = songSecondsAtStart + i * invSr;
                const bool stutterDue = isDue (t, settings.stutterEverySec, lastStutterK);
                const bool glitchDue  = isDue (t, settings.glitchEverySec, lastGlitchK);

                if (playPos >= playLen && (stutterDue || glitchDue))
                {
                    Type type = stutterDue ? Type::stutter : Type::glitch;
                    if (stutterDue && glitchDue && lastType == Type::stutter)
                        type = Type::glitch;
                    trigger (type);
                }

                if (playPos < playLen)
                {
                    const float in  = (float) (playPos + 1) / (float) fade;
                    const float out = (float) (playLen - playPos) / (float) fade;
                    const float env = std::min (1.0f, std::min (in, out));
                    L[i] = L[i] * (1.0f - env) + play[0][(size_t) playPos] * env;
                    R[i] = R[i] * (1.0f - env) + play[1][(size_t) playPos] * env;
                    ++playPos;
                }
            }
        }

    private:
        enum class Type { none, stutter, glitch };

        static bool isDue (double t, float period, int64_t& lastK) noexcept
        {
            if (period <= 0.0f || t < 0.0)
                return false;
            const auto k = (int64_t) std::floor (t / period);
            const bool due = k > lastK && k >= 1 && lastK >= 0 && (t - (double) k * period) < 0.05;
            lastK = k;
            return due;
        }

        // Copies the most recent `len` samples of history into the play buffer at `dst`.
        void capture (int len, int dst) noexcept
        {
            int src = histPos - len;
            if (src < 0) src += histSize;
            for (int j = 0; j < len; ++j)
            {
                play[0][(size_t) (dst + j)] = hist[0][(size_t) src];
                play[1][(size_t) (dst + j)] = hist[1][(size_t) src];
                if (++src >= histSize) src = 0;
            }
        }

        void trigger (Type type) noexcept
        {
            const int maxSlice = histSize - 1;

            if (type == Type::stutter)
            {
                const int slice = std::clamp (msToSamples (sampleRate, settings.stutterMs), 8, maxSlice);
                const int copies = 1 + std::clamp (settings.stutterReps, 0, maxReps);
                capture (slice, 0);

                // micro fades at the slice edges so the loop seams don't click
                const int mf = std::min (microFade, slice / 4);
                for (int j = 0; j < mf; ++j)
                {
                    const float g = (float) (j + 1) / (float) (mf + 1);
                    for (int c = 0; c < 2; ++c)
                    {
                        play[c][(size_t) j] *= g;
                        play[c][(size_t) (slice - 1 - j)] *= g;
                    }
                }

                for (int k = 1; k < copies; ++k)
                    for (int c = 0; c < 2; ++c)
                        std::copy (play[c].begin(), play[c].begin() + slice, play[c].begin() + k * slice);

                playLen = slice * copies;
            }
            else
            {
                const int slice = std::clamp (msToSamples (sampleRate, settings.glitchMs), 8, maxSlice);
                capture (slice, 0);

                const int factor = std::max (1, settings.crush);
                const bool reversed = rng.chance (0.5f);
                for (int c = 0; c < 2; ++c)
                {
                    float held = 0.0f;
                    for (int j = 0; j < slice; ++j)
                    {
                        if (j % factor == 0) held = play[c][(size_t) j];
                        play[c][(size_t) j] = held;
                    }
                    if (reversed)
                        std::reverse (play[c].begin(), play[c].begin() + slice);
                }
                playLen = slice;
            }

            fade = std::max (1, std::min (msToSamples (sampleRate, settings.xfadeMs), playLen / 2));
            playPos = 0;
            lastType = type;
        }

        Settings settings;
        double sampleRate = 44100.0;
        std::vector<float> hist[2], play[2];
        int histSize = 1, histPos = 0;
        int playLen = 0, playPos = 0, fade = 1, microFade = 88;
        int64_t lastStutterK = -1, lastGlitchK = -1;
        Type lastType = Type::none;
        Rng rng { 0xFACEu };
    };
}
