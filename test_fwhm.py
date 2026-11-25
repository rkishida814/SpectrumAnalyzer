import numpy as np
from scipy.optimize import root_scalar

def pseudo_voigt_baseline0(x, a, x0, sigma, gamma, g_ratio):
    gaussian = a * np.exp(-((x - x0)**2) / (2 * sigma**2))
    lorentzian = a / (1 + ((x - x0) / gamma)**2)
    return g_ratio * gaussian + (1.0 - g_ratio) * lorentzian

def find_numerical_fwhm(a, sigma, gamma, g_ratio):
    x0 = 0.0
    max_val = pseudo_voigt_baseline0(x0, a, x0, sigma, gamma, g_ratio)
    half_max = max_val / 2.0
    
    def target(x):
        return pseudo_voigt_baseline0(x, a, x0, sigma, gamma, g_ratio) - half_max
        
    res = root_scalar(target, bracket=[0, 100])
    return 2.0 * res.root # symmetry around 0

def calc_tch_fwhm(sigma, gamma):
    fwhm_g = 2.3548 * sigma
    fwhm_l = 2.0 * gamma
    fg5 = fwhm_g**5
    fg4_l = fwhm_g**4 * fwhm_l
    fg3_l2 = fwhm_g**3 * fwhm_l**2
    fg2_l3 = fwhm_g**2 * fwhm_l**3
    fg_l4 = fwhm_g * fwhm_l**4
    fl5 = fwhm_l**5
    
    fwhm_v5 = fg5 + 2.69269 * fg4_l + 2.42843 * fg3_l2 + 4.47163 * fg2_l3 + 0.07842 * fg_l4 + fl5
    return fwhm_v5 ** 0.2

print("Testing g_ratio dependency:")
for g in [0.0, 0.2, 0.5, 0.8, 1.0]:
    num = find_numerical_fwhm(100, 1.5, 1.5, g)
    tch = calc_tch_fwhm(1.5, 1.5) # Notice TCH here doesn't take g_ratio!
    print(f"g={g:.1f} | Num={num:.4f} | TCH={tch:.4f}")

