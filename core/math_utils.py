import numpy as np
from scipy.signal import savgol_filter

def apply_sg_filter(y: np.ndarray, window_length: int = 15, polyorder: int = 3) -> np.ndarray:
    """
    Applies Savitzky-Golay filter to smooth data.
    """
    if len(y) < window_length:
        window_length = len(y) // 2 * 2 + 1 # make odd
        if window_length < 3:
            return y.copy()
    
    return savgol_filter(y, window_length, polyorder)

def calculate_baseline_y(x: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """
    Calculates the Y values of a linear baseline defined by two points at given X coordinates.
    """
    if x1 == x0:
        return np.full_like(x, y0)
    m = (y1 - y0) / (x1 - x0)
    c = y0 - m * x0
    return m * x + c

def calculate_integral(x: np.ndarray, y: np.ndarray, baseline_y: np.ndarray) -> float:
    """
    Calculates the trapezoidal integral of (y - baseline_y).
    """
    y_subbed = y - baseline_y
    # Optional: clip negative values if purely looking for positive area?
    # Actually, standard integration is fine.
    
    # Use np.trapezoid for numpy 2.0+ compatibility
    if hasattr(np, 'trapezoid'):
        return np.trapezoid(y_subbed, x)
    else:
        return np.trapz(y_subbed, x)

LN2 = np.log(2.0)
# 高さ a・半値全幅 fwhm の関数の面積 = a × fwhm × 係数
GAUSS_AREA_FACTOR = float(np.sqrt(np.pi / (4.0 * LN2)))   # 1.0645
LORENTZ_AREA_FACTOR = float(np.pi / 2.0)                 # 1.5708


def pseudo_voigt(x: np.ndarray, a: float, x0: float, fwhm: float, g_ratio: float, return_components: bool = False):
    """
    Pseudo-Voigt function: linear combination of a Gaussian and a Lorentzian
    that share the same FWHM (the standard form).
        pV = a * [ g_ratio * G(x; fwhm) + (1 - g_ratio) * L(x; fwhm) ]
    G and L are both normalized to height 1 at x0.
    (sigma = fwhm / 2.3548, gamma = fwhm / 2)
    """
    fwhm = max(fwhm, 1e-6)
    d2 = ((x - x0) / fwhm) ** 2
    gaussian = a * np.exp(-4.0 * LN2 * d2)
    lorentzian = a / (1.0 + 4.0 * d2)

    comp_g = g_ratio * gaussian
    comp_l = (1.0 - g_ratio) * lorentzian
    total = comp_g + comp_l

    if return_components:
        return total, comp_g, comp_l
    return total


def pv_area(a: float, fwhm: float, g_ratio: float) -> float:
    """Exact area of pseudo_voigt (common FWHM)."""
    return a * fwhm * (g_ratio * GAUSS_AREA_FACTOR + (1.0 - g_ratio) * LORENTZ_AREA_FACTOR)


# ---- Thompson-Cox-Hastings pseudo-Voigt (P. Thompson, D. E. Cox, J. B. Hastings,
#      J. Appl. Cryst. 20 (1987) 79-83) ----
# Gaussian and Lorentzian widths are fitted separately; the overall FWHM and the
# Lorentzian fraction eta of an equivalent pseudo-Voigt are derived from them.

def _tch_fwhm(fwhm_g: float, fwhm_l: float) -> float:
    g, l = max(fwhm_g, 0.0), max(fwhm_l, 0.0)
    f5 = (g**5 + 2.69269 * g**4 * l + 2.42843 * g**3 * l**2
          + 4.47163 * g**2 * l**3 + 0.07842 * g * l**4 + l**5)
    return float(f5 ** 0.2)


def _tch_eta(ratio: float) -> float:
    return 1.36603 * ratio - 0.47719 * ratio**2 + 0.11116 * ratio**3


def tch_fwhm_eta(fwhm_g: float, fwhm_l: float):
    """(fwhm_g, fwhm_l) -> (overall FWHM, Lorentzian fraction eta)."""
    f = _tch_fwhm(fwhm_g, fwhm_l)
    if f <= 0:
        return 0.0, 0.0
    eta = _tch_eta(max(fwhm_l, 0.0) / f)
    return f, float(min(max(eta, 0.0), 1.0))


def tch_widths_from(fwhm: float, eta: float):
    """Inverse of tch_fwhm_eta: (overall FWHM, eta) -> (fwhm_g, fwhm_l)."""
    from scipy.optimize import brentq
    if fwhm <= 0:
        return 0.0, 0.0
    eta = min(max(eta, 0.0), 1.0)
    if eta <= 0.0:
        return float(fwhm), 0.0
    if eta >= 1.0:
        return 0.0, float(fwhm)
    ratio = brentq(lambda r: _tch_eta(r) - eta, 0.0, 1.0)   # eta is increasing on [0, 1]
    fwhm_l = ratio * fwhm
    fwhm_g = brentq(lambda g: _tch_fwhm(g, fwhm_l) - fwhm, 0.0, fwhm)
    return float(fwhm_g), float(fwhm_l)

from typing import Union

FloatOrArray = Union[float, np.ndarray]

def calc_k_alpha2_shift(x0_k_a1: FloatOrArray) -> FloatOrArray:
    """
    Calculates the K-alpha 2 shift using formulation:
    Delta 2Theta = 2 * tan(Theta) * (0.0038 / 1.5406)
    where Theta = x0 / 2 * (pi / 180) in radians.
    Returns the shift in degrees.
    """
    # x0 is 2-theta in degrees
    theta_rad = (x0_k_a1 / 2.0) * (np.pi / 180.0)
    shift_rad = 2.0 * np.tan(theta_rad) * (0.0038 / 1.5406)
    shift_deg = shift_rad * (180.0 / np.pi)
    # The new peak is at x0 + shift
    # Note: K-a2 is at a slightly higher angle (wavelength is longer: 1.5444 vs 1.5406)
    return shift_deg

