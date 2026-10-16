#pragma once

#include "Common.h"

namespace ar
{
    // _generate_theremin_np as a real-time oscillator:
    //  - frequency glides linearly between random targets (THEREMIN_FREQ_RANGE)
    //    over THEREMIN_SWEEP_SEC_RANGE seconds, or follows held MIDI notes
    //  - vibrato (+-2% at THEREMIN_VIBRATO_HZ) and slow FM wobble (vib_hz * 0.33)
    //  - right channel detuned by 0.3%, mid/side width control
    //  - slow tremolo 0.85 + 0.15*sin(2*pi*THEREMIN_AM_HZ*t)
    class Theremin
    {
    public:
        struct Settings
        {
            float lowHz = 160.0f, highHz = 880.0f;
            float sweepMinSec = 5.0f, sweepMaxSec = 12.0f;
            float vibHz = 5.0f, vibDepth = 0.02f;
            float fmDepth = 0.015f;
            float amHz = 0.7f;
            float width = 0.35f;
            bool followMidi = false;
            float glideMs = 150.0f;
        };

        void prepare (double sr) noexcept
        {
            sampleRate = sr;
            invSr = 1.0f / (float) sr;
            ampCoefUp = onePoleCoef (sr, 0.010);
            ampCoefDown = onePoleCoef (sr, 0.250);
            reset();
        }

        void reset() noexcept
        {
            phaseL = phaseR = vibPhase = wobPhase = amPhase = 0.0f;
            fromHz = toHz = curHz = 0.5f * (settings.lowHz + settings.highHz);
            glidePos = glideLen = 0;
            numHeld = 0;
            amp = 0.0f;
            startupFade = 0.0f;
        }

        void setSettings (const Settings& s) noexcept
        {
            if (s.followMidi != settings.followMidi)
                numHeld = 0;
            settings = s;
        }

        void noteOn (int note) noexcept
        {
            removeNote (note);
            if (numHeld < maxHeld)
                held[numHeld++] = note;
            glideTo (midiToHz (note), settings.glideMs * 0.001f);
        }

        void noteOff (int note) noexcept
        {
            const bool wasTop = numHeld > 0 && held[numHeld - 1] == note;
            removeNote (note);
            if (wasTop && numHeld > 0)
                glideTo (midiToHz (held[numHeld - 1]), settings.glideMs * 0.001f);
        }

        void allNotesOff() noexcept { numHeld = 0; }

        // Adds the theremin into L/R, scaled by per-sample gain.
        void render (float* L, float* R, int n, float gain) noexcept
        {
            const float startupInc = 1.0f / (1.5f * (float) sampleRate); // 1.5 s fade-in like the script

            for (int i = 0; i < n; ++i)
            {
                // Pitch: glide engine
                if (glidePos < glideLen)
                {
                    const float t = (float) glidePos / (float) glideLen;
                    curHz = fromHz + (toHz - fromHz) * t;
                    ++glidePos;
                }
                else
                {
                    curHz = toHz;
                    if (! settings.followMidi)
                        newRandomTarget();
                }

                const float vib = settings.vibDepth * std::sin (vibPhase);
                const float wob = settings.fmDepth * std::sin (wobPhase);
                const float f = curHz * (1.0f + vib + wob);

                const float left  = std::sin (phaseL);
                const float right = std::sin (phaseR);

                phaseL += twoPi * f * invSr;
                phaseR += twoPi * f * 1.003f * invSr;
                vibPhase += twoPi * settings.vibHz * invSr;
                wobPhase += twoPi * settings.vibHz * 0.33f * invSr;
                amPhase += twoPi * settings.amHz * invSr;
                wrap (phaseL); wrap (phaseR); wrap (vibPhase); wrap (wobPhase); wrap (amPhase);

                const float am = 0.85f + 0.15f * std::sin (amPhase);

                const float targetAmp = (! settings.followMidi || numHeld > 0) ? 1.0f : 0.0f;
                amp += (targetAmp > amp ? ampCoefUp : ampCoefDown) * (targetAmp - amp);
                startupFade = std::min (1.0f, startupFade + startupInc);

                const float mid = 0.5f * (left + right);
                const float side = 0.5f * (left - right);
                const float g = am * amp * startupFade * gain;

                L[i] += (mid + settings.width * side) * g;
                R[i] += (mid - settings.width * side) * g;
            }
        }

        // Approximate RMS of the raw oscillator (sine * average tremolo).
        static constexpr float nominalRms = 0.60f;

    private:
        static float midiToHz (int note) noexcept { return 440.0f * std::pow (2.0f, (float) (note - 69) / 12.0f); }

        static void wrap (float& p) noexcept
        {
            if (p >= twoPi) p -= twoPi;
        }

        void glideTo (float hz, float seconds) noexcept
        {
            fromHz = curHz;
            toHz = hz;
            glidePos = 0;
            glideLen = std::max (1, (int) (seconds * (float) sampleRate));
        }

        void newRandomTarget() noexcept
        {
            const float lo = std::min (settings.lowHz, settings.highHz);
            const float hi = std::max (settings.lowHz, settings.highHz);
            const float smin = std::min (settings.sweepMinSec, settings.sweepMaxSec);
            const float smax = std::max (settings.sweepMinSec, settings.sweepMaxSec);
            glideTo (rng.range (lo, hi), rng.range (smin, smax));
        }

        void removeNote (int note) noexcept
        {
            int w = 0;
            for (int r = 0; r < numHeld; ++r)
                if (held[r] != note)
                    held[w++] = held[r];
            numHeld = w;
        }

        Settings settings;
        double sampleRate = 44100.0;
        float invSr = 1.0f / 44100.0f;
        float phaseL = 0, phaseR = 0, vibPhase = 0, wobPhase = 0, amPhase = 0;
        float fromHz = 440, toHz = 440, curHz = 440;
        int glidePos = 0, glideLen = 0;
        float amp = 0.0f, startupFade = 0.0f;
        float ampCoefUp = 0.01f, ampCoefDown = 0.001f;

        static constexpr int maxHeld = 16;
        int held[maxHeld] {};
        int numHeld = 0;

        Rng rng { 0xC0FFEEu };
    };
}
