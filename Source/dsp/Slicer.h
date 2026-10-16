#pragma once

#include "Common.h"
#include <vector>

namespace ar
{
    // Real-time take on build_remix(): the incoming audio is recorded into a
    // history buffer and played back as a stream of random segments
    // (SEG_MIN_MS..SEG_MAX_MS), each optionally reversed (SEG_REVERSE_PROB) and/or
    // finished with a stuttered tail (SEG_STUTTER_PROB, STUTTER_MS x 2..N repeats),
    // linked by CROSSFADE_MS linear crossfades and scaled by MAIN_SEG_GAIN.
    class Slicer
    {
    public:
        static constexpr double maxLookbackSec = 8.0;
        static constexpr double maxSegmentSec  = 6.0;
        static constexpr double maxStutterSec  = 0.5 * 8.0;

        struct Settings
        {
            float minMs = 800.0f, maxMs = 4000.0f;
            float reverseProb = 0.15f, stutterProb = 0.10f;
            float stutterMs = 120.0f;
            int stutterRepsMax = 4;
            float xfadeMs = 80.0f;
            float lookbackSec = 8.0f;
            float gain = 0.95f;
        };

        void prepare (double sr)
        {
            sampleRate = sr;
            size = (int) std::ceil (sr * (maxLookbackSec + maxSegmentSec + maxStutterSec + 1.0));
            hist[0].assign ((size_t) size, 0.0f);
            hist[1].assign ((size_t) size, 0.0f);
            microFade = msToSamples (sr, 2.0);
            reset();
        }

        // Cheap: no memset needed, `filled` keeps segments inside freshly written audio.
        void reset() noexcept
        {
            writePos = 0;
            filled = 0;
            for (auto& g : grains)
                g.active = false;
        }

        void setSettings (const Settings& s) noexcept { settings = s; }

        void setSeed (uint32_t seed) noexcept { rng.setSeed (seed); }

        // In-place: input is recorded, output is the remixed stream.
        void process (float* L, float* R, int n) noexcept
        {
            for (int i = 0; i < n; ++i)
            {
                const float inL = L[i], inR = R[i];
                hist[0][(size_t) writePos] = inL;
                hist[1][(size_t) writePos] = inR;
                if (++writePos >= size) writePos = 0;
                if (filled < size) ++filled;

                scheduleIfNeeded();

                float outL = 0.0f, outR = 0.0f, envSum = 0.0f;
                for (auto& g : grains)
                {
                    if (! g.active)
                        continue;

                    const float env = g.envelope();
                    const int idx = g.bufferIndex (size);
                    outL += hist[0][(size_t) idx] * env;
                    outR += hist[1][(size_t) idx] * env;
                    envSum += g.fadeEnv();

                    if (++g.age >= g.total)
                        g.active = false;
                }

                // Where no segment is sounding yet (start-up), let the input through.
                const float dry = std::max (0.0f, 1.0f - envSum);
                L[i] = outL * settings.gain + inL * dry;
                R[i] = outR * settings.gain + inR * dry;
            }
        }

    private:
        struct Grain
        {
            bool active = false;
            bool reverse = false;
            bool handedOff = false;
            int start = 0;      // buffer index of logical sample 0 (before reverse)
            int bodyLen = 0;
            int stLen = 0;
            int reps = 0;
            int total = 0;
            int age = 0;
            int fade = 1;
            int micro = 1;

            int logicalIndex() const noexcept
            {
                if (age < bodyLen)
                    return age;
                return bodyLen - stLen + (age - bodyLen) % stLen;
            }

            int bufferIndex (int size) const noexcept
            {
                const int k = logicalIndex();
                int idx = reverse ? start + bodyLen - 1 - k : start + k;
                idx %= size;
                if (idx < 0) idx += size;
                return idx;
            }

            float fadeEnv() const noexcept
            {
                const float in  = (float) (age + 1) / (float) fade;
                const float out = (float) (total - age) / (float) fade;
                return std::min (1.0f, std::min (in, out));
            }

            float envelope() const noexcept
            {
                float e = fadeEnv();
                if (reps > 0 && age >= bodyLen - stLen)
                {
                    // Tiny fades at every stutter loop boundary to avoid clicks.
                    const int p = age < bodyLen ? age - (bodyLen - stLen) : (age - bodyLen) % stLen;
                    const float m = std::min ((float) (p + 1) / (float) micro,
                                              (float) (stLen - p) / (float) micro);
                    e *= std::min (1.0f, m);
                }
                return e;
            }
        };

        void scheduleIfNeeded() noexcept
        {
            Grain* current = nullptr;
            for (auto& g : grains)
                if (g.active && ! g.handedOff)
                    current = &g;

            if (current != nullptr)
            {
                if (current->total - current->age > current->fade)
                    return;
                current->handedOff = true;
            }

            startGrain();
        }

        void startGrain() noexcept
        {
            Grain* slot = nullptr;
            for (auto& g : grains)
                if (! g.active) { slot = &g; break; }
            if (slot == nullptr)
                return;

            const int lookback = std::min ((int) (settings.lookbackSec * sampleRate), filled - 1);
            const int xfade = msToSamples (sampleRate, settings.xfadeMs);
            const int minLen = std::max (msToSamples (sampleRate, std::min (settings.minMs, settings.maxMs)), 2 * xfade + 16);
            const int maxLen = std::max (msToSamples (sampleRate, std::max (settings.minMs, settings.maxMs)), minLen);

            if (lookback < 4 * microFade + 32)
                return; // not enough history yet, input passes through

            int len = rng.rangeInt (minLen, maxLen);
            len = std::min (len, lookback);

            Grain g;
            g.active = true;
            g.bodyLen = len;
            g.fade = std::max (1, std::min (xfade, len / 2));
            g.micro = microFade;
            g.reverse = rng.chance (settings.reverseProb);

            if (rng.chance (settings.stutterProb))
            {
                g.stLen = std::min (msToSamples (sampleRate, settings.stutterMs), len);
                g.reps = rng.rangeInt (2, std::max (2, settings.stutterRepsMax));
                g.micro = std::max (1, std::min (microFade, g.stLen / 4));
            }

            g.total = g.bodyLen + g.reps * g.stLen;

            // Segment must lie entirely in the past so playback never overtakes the write head.
            const int back = len + rng.rangeInt (0, lookback - len);
            g.start = writePos - back;
            if (g.start < 0) g.start += size;

            *slot = g;
        }

        Settings settings;
        double sampleRate = 44100.0;
        std::vector<float> hist[2];
        int size = 1, writePos = 0, filled = 0, microFade = 88;
        Grain grains[3];
        Rng rng { 0x1234567u };
    };
}
