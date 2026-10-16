#pragma once

#include "Common.h"

namespace ar
{
    // _center_cut_np from the scripts:
    //   M  = (L + R) / 2,   M_lp = lowpass(M)
    //   L' = L - alpha*M + bassReturn*M_lp   (same for R)
    // Removes centre-panned content (usually vocals) while returning the low end.
    // The original used a moving-average lowpass; a 2nd-order Butterworth is used here.
    class CenterCut
    {
    public:
        void prepare (double sr) noexcept
        {
            sampleRate = sr;
            lp.reset();
            lastFreq = -1.0f;
        }

        void reset() noexcept { lp.reset(); }

        void setSettings (float amount, float bassHz, float bassReturnAmt) noexcept
        {
            alpha = amount;
            bassReturn = bassReturnAmt;
            if (std::abs (bassHz - lastFreq) > 1.0e-3f)
            {
                lp.setLowpass (sampleRate, bassHz);
                lastFreq = bassHz;
            }
        }

        void process (float* L, float* R, int n) noexcept
        {
            for (int i = 0; i < n; ++i)
            {
                const float m = 0.5f * (L[i] + R[i]);
                const float mlp = lp.process (m);
                const float add = -alpha * m + bassReturn * mlp;
                L[i] += add;
                R[i] += add;
            }
        }

    private:
        double sampleRate = 44100.0;
        Biquad lp;
        float lastFreq = -1.0f;
        float alpha = 0.9f, bassReturn = 0.35f;
    };
}
