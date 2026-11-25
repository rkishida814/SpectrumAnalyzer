import numpy as np
from scipy.optimize import root_scalar

def find_numerical_fwhm(x0, a, sigma, gamma, g_ratio):
    def pv(x):
        gaussian = a * np.exp(-((x - x0)**2) / (2 * sigma**2))
        lorentzian = a / (1 + ((x - x0) / gamma)**2)
        return g_ratio * gaussian + (1.0 - g_ratio) * lorentzian
        
    max_val = pv(x0)
    target_val = max_val / 2.0
    
    def target(x):
        return pv(x) - target_val
        
    try:
        res = root_scalar(target, bracket=[x0, x0 + 100])
        return 2.0 * (res.root - x0)
    except:
        return np.nan

print("Linear Combination FWHMs:")
a = 1.0; x0 = 0.0

for g_ratio in [0.0, 0.2, 0.5, 0.8, 1.0]:
    for base_w in [0.5, 2.0]:
        sigma = base_w / 2.3548
        gamma = base_w / 2.0
        # If G and L are exactly the SAME width, then combining them should have THAT exact same width
        num = find_numerical_fwhm(x0, a, sigma, gamma, g_ratio)
        linear = g_ratio * base_w + (1.0 - g_ratio) * base_w
        print(f"w={base_w:.1f}, g={g_ratio:.1f} | Num={num:.4f} | Linear={linear:.4f}")

print("\nMixed Combination FWHMs:")
sigma = 1.0 / 2.3548
gamma = 5.0 / 2.0
for g_ratio in [0.0, 0.2, 0.5, 0.8, 1.0]:
    num = find_numerical_fwhm(x0, a, sigma, gamma, g_ratio)
    linear = g_ratio * 1.0 + (1.0 - g_ratio) * 5.0
    print(f"g={g_ratio:.1f} | Num={num:.4f} | Linear={linear:.4f}")
    
