import time
import numpy as np
from scipy.optimize import least_squares
from core.math_utils import (pseudo_voigt, pv_area, calc_k_alpha2_shift,
                             tch_fwhm_eta, tch_widths_from)
from state import Peak

# Peak profiles
#   PV : pseudo-Voigt with a common FWHM for G and L (default).
#        Fitted per peak: g_ratio, a, x0, fwhm
#   TCH: Thompson-Cox-Hastings pseudo-Voigt (advanced).
#        Fitted per peak: a, x0, fwhm_g, fwhm_l. fwhm and g_ratio are derived.
PV = "pv"
TCH = "tch"

FWHM_MIN, FWHM_MAX = 0.02, 40.0      # PV: overall FWHM
TCH_WIDTH_MIN = 1e-4                  # TCH: each width may approach 0 (pure G or pure L)


def refresh_peak(peak: Peak, profile: str = PV):
    """Recalculate derived values (TCH: fwhm and g_ratio; both: area)."""
    if profile == TCH:
        fwhm, eta = tch_fwhm_eta(peak.fwhm_g, peak.fwhm_l)
        peak.fwhm = fwhm
        peak.g_ratio = 1.0 - eta
    peak.area = float(pv_area(peak.a, peak.fwhm, peak.g_ratio)) if peak.fwhm > 0 else 0.0


def set_width(peak: Peak, fwhm: float, g_ratio: float, profile: str = PV):
    """Set the overall FWHM and G fraction (e.g. from the FWHM drag). TCH widths are derived."""
    g_ratio = min(max(g_ratio, 0.0), 1.0)
    if profile == TCH:
        peak.fwhm_g, peak.fwhm_l = tch_widths_from(fwhm, 1.0 - g_ratio)
    else:
        peak.fwhm = fwhm
        peak.g_ratio = g_ratio
    refresh_peak(peak, profile)


def convert_profile(peak: Peak, new_profile: str):
    """Keep the current shape (overall FWHM and G fraction) when switching profiles."""
    if new_profile == TCH:
        peak.fwhm_g, peak.fwhm_l = tch_widths_from(peak.fwhm, 1.0 - peak.g_ratio)
    refresh_peak(peak, new_profile)


def _param_specs(peak: Peak, profile: str):
    """(attribute, lower bound, upper bound) for each free parameter, in packing order."""
    if peak.lock_all:
        return []
    if profile == TCH:
        cand = [("a", 0.0, np.inf, peak.lock_a),
                ("x0", -np.inf, np.inf, peak.lock_x0),
                ("fwhm_g", TCH_WIDTH_MIN, FWHM_MAX, peak.lock_fwhm_g),
                ("fwhm_l", TCH_WIDTH_MIN, FWHM_MAX, peak.lock_fwhm_l)]
    else:
        cand = [("g_ratio", 0.0, 1.0, peak.lock_g_ratio),
                ("a", 0.0, np.inf, peak.lock_a),
                ("x0", -np.inf, np.inf, peak.lock_x0),
                ("fwhm", FWHM_MIN, FWHM_MAX, peak.lock_fwhm)]
    return [(name, lo, hi) for name, lo, hi, locked in cand if not locked]


def _pack_params_and_bounds(peak: Peak, profile: str):
    params, lb, ub = [], [], []
    for name, lo, hi in _param_specs(peak, profile):
        # least_squares requires the initial value to lie within the bounds
        params.append(min(max(getattr(peak, name), lo), hi))
        lb.append(lo)
        ub.append(hi)
    return params, lb, ub


def _unpack_params(p_array, peak: Peak, profile: str):
    """Writes optimized parameters back into the peak in-place."""
    for value, (name, lo, hi) in zip(p_array, _param_specs(peak, profile)):
        setattr(peak, name, float(min(max(value, lo), hi)))
    refresh_peak(peak, profile)


def _build_model(x: np.ndarray, peak: Peak, base_y: np.ndarray) -> np.ndarray:
    y_model = base_y.copy()
    y_model += pseudo_voigt(x, peak.a, peak.x0, peak.fwhm, peak.g_ratio)

    if peak.has_k_alpha2:
        ka2_x0 = peak.x0 + calc_k_alpha2_shift(peak.x0)
        # Ka2 strength fixed to 0.5 of Ka1, same shape
        y_model += pseudo_voigt(x, peak.a * 0.5, ka2_x0, peak.fwhm, peak.g_ratio)

    return y_model


def fit_individual_peak(x_data: np.ndarray, y_data: np.ndarray, base_y: np.ndarray, peak: Peak,
                        max_nfev: int = 50, method: str = 'trf', timeout: float = 45.0,
                        callback_fn=None, profile: str = PV):
    """
    Fits a single peak (with the baseline only) using least squares.
    """
    refresh_peak(peak, profile)
    if peak.lock_all:
        return 0.0

    start_time = time.time()
    step_count = [0]

    def residual(p):
        if time.time() - start_time > timeout:
            raise TimeoutError("Fitting timeout reached")
        _unpack_params(p, peak, profile)
        step_count[0] += 1
        if callback_fn:
            callback_fn(step=step_count[0], max_nfev=max_nfev)
        return _build_model(x_data, peak, base_y) - y_data

    params_list, lb_list, ub_list = _pack_params_and_bounds(peak, profile)
    if len(params_list) == 0:
        return 0.0

    res = least_squares(residual, np.array(params_list),
                        bounds=(lb_list, ub_list),
                        max_nfev=max_nfev,
                        method=method)

    _unpack_params(res.x, peak, profile)

    final_model = _build_model(x_data, peak, base_y)
    return float(np.mean((final_model - y_data)**2))


def fit_global_peaks(x_data: np.ndarray, y_data: np.ndarray, base_y: np.ndarray, peaks,
                     max_nfev: int = 50, method: str = 'trf', timeout: float = 45.0,
                     callback_fn=None, profile: str = PV):
    for p in peaks:
        refresh_peak(p, profile)

    initial_params_list, lower_bounds_list, upper_bounds_list = [], [], []
    active = []  # (peak, number of free parameters)
    for p in peaks:
        packed, lb, ub = _pack_params_and_bounds(p, profile)
        if packed:
            initial_params_list.extend(packed)
            lower_bounds_list.extend(lb)
            upper_bounds_list.extend(ub)
            active.append((p, len(packed)))

    if not initial_params_list:
        return 0.0

    start_time = time.time()
    step_count = [0]
    zeros = np.zeros_like(x_data)

    def residual(p_array):
        if time.time() - start_time > timeout:
            raise TimeoutError("Fitting timeout reached")
        idx = 0
        for p, num in active:
            _unpack_params(p_array[idx:idx + num], p, profile)
            idx += num

        y_model = base_y.copy()
        for p in peaks:
            y_model += _build_model(x_data, p, zeros)

        step_count[0] += 1
        if callback_fn:
            callback_fn(step=step_count[0], max_nfev=max_nfev)
        return y_model - y_data

    res = least_squares(residual, initial_params_list,
                        bounds=(lower_bounds_list, upper_bounds_list),
                        max_nfev=max_nfev,
                        method=method)

    # Final unpack (also refreshes fwhm / g_ratio / area)
    residual(res.x)

    y_model = base_y.copy()
    for p in peaks:
        y_model += _build_model(x_data, p, zeros)
    return float(np.mean((y_model - y_data)**2))
