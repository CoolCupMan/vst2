#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace ar
{
    constexpr float twoPi = 6.283185307179586f;

    inline float dbToGain (float db) noexcept { return std::pow (10.0f, db / 20.0f); }

    inline int msToSamples (double sampleRate, double ms) noexcept
    {
        return std::max (1, (int) std::lround (sampleRate * ms / 1000.0));
    }

    // One-pole smoothing coefficient for a given time constant.
    inline float onePoleCoef (double sampleRate, double seconds) noexcept
    {
        if (seconds <= 0.0)
            return 1.0f;
        return (float) (1.0 - std::exp (-1.0 / (seconds * sampleRate)));
    }

    // Fast, allocation-free PRNG for the audio thread (xorshift32).
    class Rng
    {
    public:
        explicit Rng (uint32_t seed = 0x9E3779B9u) noexcept { setSeed (seed); }

        void setSeed (uint32_t seed) noexcept { state = seed != 0 ? seed : 0x9E3779B9u; }

        uint32_t next() noexcept
        {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            return state;
        }

        // [0, 1)
        float uniform() noexcept { return (float) (next() >> 8) * (1.0f / 16777216.0f); }

        // [-1, 1)
        float bipolar() noexcept { return uniform() * 2.0f - 1.0f; }

        float range (float lo, float hi) noexcept { return lo + (hi - lo) * uniform(); }

        // [lo, hi] inclusive
        int rangeInt (int lo, int hi) noexcept
        {
            if (hi <= lo)
                return lo;
            return lo + (int) (next() % (uint32_t) (hi - lo + 1));
        }

        bool chance (float p) noexcept { return uniform() < p; }

    private:
        uint32_t state;
    };

    // RBJ biquad, transposed direct form II.
    class Biquad
    {
    public:
        void setLowpass (double sampleRate, double freq, double q = 0.70710678) noexcept
        {
            freq = std::clamp (freq, 10.0, sampleRate * 0.45);
            const double w0 = 2.0 * 3.14159265358979323846 * freq / sampleRate;
            const double cw = std::cos (w0), sw = std::sin (w0);
            const double alpha = sw / (2.0 * q);
            const double a0 = 1.0 + alpha;
            b0 = (float) ((1.0 - cw) * 0.5 / a0);
            b1 = (float) ((1.0 - cw) / a0);
            b2 = b0;
            a1 = (float) (-2.0 * cw / a0);
            a2 = (float) ((1.0 - alpha) / a0);
        }

        void reset() noexcept { z1 = z2 = 0.0f; }

        float process (float x) noexcept
        {
            const float y = b0 * x + z1;
            z1 = b1 * x - a1 * y + z2;
            z2 = b2 * x - a2 * y;
            return y;
        }

    private:
        float b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
        float z1 = 0, z2 = 0;
    };
}
