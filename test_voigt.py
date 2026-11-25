import numpy as np
import matplotlib.pyplot as plt
from core.math_utils import pseudo_voigt

x = np.linspace(30, 35, 1000)
a = 28088.6833
x0 = 32.0205
sigma = 0.4
gamma = 0.4
g_ratio = 0.5

y_curve, comp_g, comp_l = pseudo_voigt(x, a, x0, sigma, gamma, g_ratio, return_components=True)

plt.figure()
plt.plot(x, comp_g, 'r:', label='Gaussian')
plt.plot(x, comp_l, 'darkred', linestyle=':', label='Lorentzian')
plt.plot(x, y_curve, 'r-', label='Total')
plt.legend()
plt.savefig('test_plot.png')
print("Image saved.")
