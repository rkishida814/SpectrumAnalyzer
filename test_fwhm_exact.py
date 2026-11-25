import numpy as np
from scipy.optimize import root_scalar

def exact_fwhm(sigma, gamma, g_ratio):
    def pv(x):
        gaussian = np.exp(-(x**2) / (2 * sigma**2))
        lorentzian = 1.0 / (1 + (x / gamma)**2)
        return g_ratio * gaussian + (1.0 - g_ratio) * lorentzian
        
    half_max = pv(0.0) / 2.0
    
    def target(x):
        return pv(x) - half_max
        
    max_w = max(2.3548 * sigma, 2.0 * gamma) * 2.0
    if max_w == 0: return 0.0
    res = root_scalar(target, bracket=[0, max_w])
    return 2.0 * res.root

print("Exact FWHM for 1.0/5.0 parameters:")
print("g_ratio 0.0:", exact_fwhm(1.0/2.3548, 5.0/2.0, 0.0))
print("g_ratio 0.2:", exact_fwhm(1.0/2.3548, 5.0/2.0, 0.2))
print("g_ratio 0.5:", exact_fwhm(1.0/2.3548, 5.0/2.0, 0.5))
print("g_ratio 0.8:", exact_fwhm(1.0/2.3548, 5.0/2.0, 0.8))
print("g_ratio 1.0:", exact_fwhm(1.0/2.3548, 5.0/2.0, 1.0))

