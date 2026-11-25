import numpy as np
import math

x = np.linspace(30, 35, 1000)
a = 28088.6833
x0 = 32.0205
sigma = 0.4
gamma = 0.4
g_ratio = 0.5

gaussian = a * np.exp(-((x - x0)**2) / (2 * sigma**2))
lorentzian = a / (1 + ((x - x0) / gamma)**2)

print("x\t\tGaussian\tLorentzian")
pts = [32.0205, 32.22, 32.42, 32.82] # center, 0.5 sigma, 1 sigma, 2 sigma
for pt in pts:
    g = a * math.exp(-((pt - x0)**2) / (2 * sigma**2))
    l = a / (1 + ((pt - x0) / gamma)**2)
    print(f"{pt:.4f}\t{g*0.5:.2f}\t\t{l*0.5:.2f}")

