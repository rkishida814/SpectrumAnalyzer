import numpy as np
from scipy.optimize import root_scalar

def exact_fwhm(sigma, gamma, g_ratio):
    def pv(x):
        gaussian = np.exp(-(x**2) / (2 * sigma**2))
        lorentzian = 1.0 / (1 + (x / gamma)**2)
        return g_ratio * gaussian + (1.0 - g_ratio) * lorentzian
    max_w = max(2.3548 * sigma, 2.0 * gamma) * 2.0
    if max_w == 0: return 0.0
    res = root_scalar(lambda x: pv(x) - 0.5, bracket=[0, max_w])
    return 2.0 * res.root

def exact_inverse(target_fwhm, g_ratio):
    # W is our base width parameter such that sigma=W/2.3548 and gamma=W/2.0
    # Because pv(x) is linearly scaled by x/width, FWHM simply scales linearly with W.
    # W_base = 1.0 -> FWHM_base.  Therefore W_target = target_fwhm / FWHM_base * W_base
    fwhm_base = exact_fwhm(1.0/2.3548, 1.0/2.0, g_ratio)
    scaling_factor = target_fwhm / fwhm_base
    # Meaning sigma = (1.0/2.3548) * scaling_factor, gamma = (1.0/2.0) * scaling_factor
    return scaling_factor / 2.3548, scaling_factor / 2.0
    
print("Inverse for 10.0 at g=0.5:", exact_inverse(10.0, 0.5))
print("Forward check:", exact_fwhm(exact_inverse(10.0, 0.5)[0], exact_inverse(10.0, 0.5)[1], 0.5))
