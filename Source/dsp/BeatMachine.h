#pragma once

#include "Common.h"

namespace ar
{
    // _generate_beat_block_np + _apply_rotating_beats_63_27 as a real-time drum synth.
    //
    // Pattern (per bar of 16 sixteenths):
    //   kick  on 0, 2, 8, 14 (+6 with 35%)    - pitch-drop sine 56 -> 38 Hz
    //   snare on 4, 12 (+ghost on 11 at 40%)  - noise + 180 Hz body
    //   hats  on every 16th, open on 15 (50%) - enveloped noise
    // The song is divided into alternating 63 s / 27 s blocks; every block gets a
    // fresh deterministic random seed (block*7919 + bpm*97) and, in "Rotate" mode,
    // a new BPM from {86, 88, 90, 92, 96, 72}. Fills hit at 0/21/42 s of each 63 s block.
    class BeatMachine
    {
    public:
        enum class TempoMode { hostSync = 0, rotate = 1 };

        struct Settings
        {
            TempoMode tempo = TempoMode::hostSync;
            float swing = 0.56f;
            bool structure = true;
            bool fills = true;
            float kickHz = 56.0f, kickDropHz = 38.0f, kickMs = 120.0f;
            float snareHz = 180.0f, snareNoiseMs = 130.0f, snareBodyMs = 70.0f;
            float hatClosedMs = 40.0f, hatOpenMs = 120.0f;
        };

        struct Clock
        {
            double songSeconds = 0.0;   // at first sample of the block
            bool hasHostPpq = false;
            double hostPpq = 0.0;       // at first sample of the block
            double hostBpm = 120.0;
        };

        void prepare (double sr) noexcept
        {
            sampleRate = sr;
            hatHpCoef = 1.0f - std::exp (-twoPi * 7000.0f / (float) sr);
            reset();
        }

        void reset() noexcept
        {
            kick.active = false;
            for (auto& s : snares) s.active = false;
            for (auto& h : hats) h.active = false;
            internalPpq = 0.0;
            lastStep = INT64_MIN;
            lastBar = INT64_MIN;
            blockIndex = -1;
            prevBlockPos = -1.0;
            rotBpm = 90.0;
            prevRotBpm = 0;
        }

        void setSettings (const Settings& s) noexcept { settings = s; }

        // Adds the drum bus into L/R scaled by gain.
        void render (float* L, float* R, int n, const Clock& clock, float gain) noexcept
        {
            const double invSr = 1.0 / sampleRate;
            const bool useHost = settings.tempo == TempoMode::hostSync && clock.hasHostPpq;

            for (int i = 0; i < n; ++i)
            {
                const double sec = clock.songSeconds + i * invSr;
                updateBlock (sec);

                const double bpm = currentBpm (clock);
                double ppq;
                if (useHost)
                {
                    ppq = clock.hostPpq + i * invSr * bpm / 60.0;
                    internalPpq = ppq;
                }
                else
                {
                    ppq = internalPpq;
                    internalPpq += invSr * bpm / 60.0;
                }

                f16 = (float) (sampleRate * 60.0 / bpm / 4.0);
                handleStep (ppq);

                const float s = (renderKick() + renderSnares() + renderHats()) * 0.5f * gain;
                L[i] += s;
                R[i] += s;
            }
        }

        // Called when the transport (re)starts.
        void resetClock() noexcept
        {
            internalPpq = 0.0;
            lastStep = INT64_MIN;
            lastBar = INT64_MIN;
            blockIndex = -1;
            prevBlockPos = -1.0;
        }

    private:
        // ---------------- voices ----------------
        struct Kick
        {
            bool active = false;
            int n = 0, length = 0, envLen = 0;
            float phase = 0, freq = 0, freqMul = 1, env = 1, envCoef = 1;
        };

        struct Snare
        {
            bool active = false;
            int n = 0, length = 0, noiseLen = 0, bodyLen = 0;
            float amp = 1, phase = 0, freq = 180;
            float noiseEnv = 1, noiseCoef = 1, bodyEnv = 1, bodyCoef = 1;
        };

        struct Hat
        {
            bool active = false;
            int n = 0, length = 0, envLen = 0;
            float amp = 1, env = 1, envCoef = 1, lp = 0;
        };

        // exp(-linspace(0, 6, n)) -> per-sample decay, zero after n samples
        static float decayCoef (int len) noexcept { return std::exp (-6.0f / (float) std::max (1, len)); }

        void triggerKick (int length) noexcept
        {
            kick.active = true;
            kick.n = 0;
            kick.length = std::max (1, length);
            kick.envLen = msToSamples (sampleRate, settings.kickMs);
            kick.env = 1.0f;
            kick.envCoef = decayCoef (kick.envLen);
            kick.phase = 0.0f;
            kick.freq = settings.kickHz;
            kick.freqMul = std::pow (settings.kickDropHz / settings.kickHz, 1.0f / (float) kick.length);
        }

        void triggerSnare (int length, float amp) noexcept
        {
            Snare* v = &snares[0];
            for (auto& s : snares)
                if (! s.active) { v = &s; break; }
            if (v->active)
                v = &snares[nextSnare++ % numSnares];

            v->active = true;
            v->n = 0;
            v->length = std::max (1, length);
            v->amp = amp;
            v->phase = 0.0f;
            v->freq = settings.snareHz;
            v->noiseLen = msToSamples (sampleRate, settings.snareNoiseMs);
            v->bodyLen = msToSamples (sampleRate, settings.snareBodyMs);
            v->noiseEnv = v->bodyEnv = 1.0f;
            v->noiseCoef = decayCoef (v->noiseLen);
            v->bodyCoef = decayCoef (v->bodyLen);
        }

        void triggerHat (int length, bool open, float amp) noexcept
        {
            Hat* v = &hats[0];
            for (auto& h : hats)
                if (! h.active) { v = &h; break; }
            if (v->active)
                v = &hats[nextHat++ % numHats];

            v->active = true;
            v->n = 0;
            v->length = std::max (1, length);
            v->amp = amp;
            v->envLen = msToSamples (sampleRate, open ? settings.hatOpenMs : settings.hatClosedMs);
            v->env = 1.0f;
            v->envCoef = decayCoef (v->envLen);
        }

        float renderKick() noexcept
        {
            if (! kick.active)
                return 0.0f;
            const float s = std::sin (kick.phase) * (kick.n < kick.envLen ? kick.env : 0.0f);
            kick.phase += twoPi * kick.freq / (float) sampleRate;
            if (kick.phase >= twoPi) kick.phase -= twoPi;
            kick.freq *= kick.freqMul;
            kick.env *= kick.envCoef;
            if (++kick.n >= kick.length) kick.active = false;
            return s;
        }

        float renderSnares() noexcept
        {
            float sum = 0.0f;
            for (auto& v : snares)
            {
                if (! v.active)
                    continue;
                const float noise = noiseRng.bipolar() * (v.n < v.noiseLen ? v.noiseEnv : 0.0f);
                const float tone = std::sin (v.phase) * (v.n < v.bodyLen ? v.bodyEnv : 0.0f) * 0.6f;
                sum += (noise * 0.8f + tone * 0.6f) * v.amp;
                v.phase += twoPi * v.freq / (float) sampleRate;
                if (v.phase >= twoPi) v.phase -= twoPi;
                v.noiseEnv *= v.noiseCoef;
                v.bodyEnv *= v.bodyCoef;
                if (++v.n >= v.length) v.active = false;
            }
            return sum;
        }

        float renderHats() noexcept
        {
            float sum = 0.0f;
            for (auto& v : hats)
            {
                if (! v.active)
                    continue;
                const float x = noiseRng.bipolar();
                v.lp += hatHpCoef * (x - v.lp);   // high-pass = x - lowpass(x): brighter hats
                const float hp = x - v.lp;
                sum += hp * (v.n < v.envLen ? v.env : 0.0f) * 0.6f * v.amp;
                v.env *= v.envCoef;
                if (++v.n >= v.length) v.active = false;
            }
            return sum;
        }

        // ---------------- sequencing ----------------
        double currentBpm (const Clock& clock) const noexcept
        {
            if (settings.tempo == TempoMode::rotate)
                return rotBpm;
            return std::clamp (clock.hostBpm, 30.0, 300.0);
        }

        void updateBlock (double sec) noexcept
        {
            constexpr double longS = 63.0, shortS = 27.0, cycle = longS + shortS;

            int64_t idx = 0;
            double posInBlock = sec;
            bool isLong = true;

            if (settings.structure)
            {
                const double c = std::floor (sec / cycle);
                const double within = sec - c * cycle;
                isLong = within < longS;
                idx = (int64_t) c * 2 + (isLong ? 0 : 1);
                posInBlock = isLong ? within : within - longS;
            }

            if (idx != blockIndex)
            {
                blockIndex = idx;
                startBlock (idx);
                prevBlockPos = -1.0;
            }

            if (settings.fills && settings.structure && isLong)
            {
                for (double off : { 0.0, 21.0, 42.0 })
                    if (prevBlockPos < off && posInBlock >= off && posInBlock - off < 0.05)
                        triggerFill();
            }

            prevBlockPos = posInBlock;
        }

        void startBlock (int64_t idx) noexcept
        {
            static constexpr int bpmChoices[] = { 86, 88, 90, 92, 96, 72 };
            int pick;
            do
            {
                pick = bpmChoices[patternRng.rangeInt (0, 5)];
            } while (pick == prevRotBpm);
            prevRotBpm = pick;
            rotBpm = pick;

            patternRng.setSeed ((uint32_t) (idx * 7919 + (int64_t) pick * 97 + 1));
            lastBar = INT64_MIN; // re-roll bar decisions with the new seed
        }

        void triggerFill() noexcept
        {
            triggerSnare ((int) (f16 * 6.0f), 1.1f);
            triggerHat ((int) (f16 * 8.0f), true, 0.8f);
        }

        void handleStep (double ppq) noexcept
        {
            const double pairs = ppq * 2.0;              // eighth notes
            const double pairIdx = std::floor (pairs);
            const double within = pairs - pairIdx;
            const int64_t step = (int64_t) pairIdx * 2 + (within >= settings.swing ? 1 : 0);

            if (step == lastStep)
                return;
            lastStep = step;

            const int64_t bar = (step >= 0 ? step : step - 15) / 16;
            if (bar != lastBar)
            {
                lastBar = bar;
                barKick6 = patternRng.chance (0.35f);
                barGhost = patternRng.chance (0.40f);
                barOpenHat = patternRng.chance (0.50f);
            }

            const int s = (int) (((step % 16) + 16) % 16);

            if (s == 0 || s == 2 || s == 8 || s == 14 || (s == 6 && barKick6))
                triggerKick ((int) (f16 * 3.2f));

            if (s == 4 || s == 12)
                triggerSnare ((int) (f16 * 3.0f), 1.0f);
            if (s == 11 && barGhost)
                triggerSnare ((int) (f16 * 1.2f), 0.35f);

            const bool open = s == 15 && barOpenHat;
            triggerHat ((int) (f16 * (open ? 2.0f : 1.0f)), open, 1.0f);
        }

        Settings settings;
        double sampleRate = 44100.0;
        float f16 = 5000.0f;
        float hatHpCoef = 0.5f;

        Kick kick;
        static constexpr int numSnares = 4, numHats = 3;
        Snare snares[numSnares];
        Hat hats[numHats];
        int nextSnare = 0, nextHat = 0;

        double internalPpq = 0.0;
        int64_t lastStep = INT64_MIN, lastBar = INT64_MIN, blockIndex = -1;
        double prevBlockPos = -1.0;
        double rotBpm = 90.0;
        int prevRotBpm = 0;
        bool barKick6 = false, barGhost = false, barOpenHat = false;

        Rng patternRng { 7919u };
        Rng noiseRng { 0xBEEFu };
    };
}
