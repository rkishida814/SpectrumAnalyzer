import numpy as np
from scipy.optimize import root_scalar

def find_numerical_fwhm(sigma, gamma, g_ratio):
    def pseudo_voigt_baseline0(x, sigma, gamma, g_ratio):
        a = 1.0; x0 = 0.0
        gaussian = a * np.exp(-((x - x0)**2) / (2 * sigma**2))
        lorentzian = a / (1 + ((x - x0) / gamma)**2)
        return g_ratio * gaussian + (1.0 - g_ratio) * lorentzian
        
    x0 = 0.0
    max_val = pseudo_voigt_baseline0(x0, sigma, gamma, g_ratio)
    half_max = max_val / 2.0
    
    def target(x):
        return pseudo_voigt_baseline0(x, sigma, gamma, g_ratio) - half_max
        
    res = root_scalar(target, bracket=[0, 100])
    return 2.0 * res.root

print("Testing TCH width combination:")
fwhm_g_vals = [0.1, 1.0, 5.0]
fwhm_l_vals = [0.1, 1.0, 5.0]

for fwhm_g in fwhm_g_vals:
    for fwhm_l in fwhm_l_vals:
        sigma = fwhm_g / 2.3548
        gamma = fwhm_l / 2.0
        
        # TCH Equation:
        fg5 = fwhm_g**5
        fg4_l = fwhm_g**4 * fwhm_l
        fg3_l2 = fwhm_g**3 * fwhm_l**2
        fg2_l3 = fwhm_g**2 * fwhm_l**3
        fg_l4 = fwhm_g * fwhm_l**4
        fl5 = fwhm_l**5
        tch_fwhm = (fg5 + 2.69269 * fg4_l + 2.42843 * fg3_l2 + 4.47163 * fg2_l3 + 0.07842 * fg_l4 + fl5)**0.2
        
        # Approximate mix factor eta for true Voigt:
        # TCH gives the *total* FWHM of a convolution, but our pseudo_voigt is a *linear combination*.
        
        # In our pseudo_voigt combination, g_ratio determines the mix.
        # Let's see what numerical gives for g_ratio=0.5
        num_5 = find_numerical_fwhm(sigma, gamma, 0.5)
        
        print(f"FWHM_G={fwhm_g:.1f}, FWHM_L={fwhm_l:.1f} | TCH={tch_fwhm:.4f} | Num(g=0.5)={num_5:.4f}")

