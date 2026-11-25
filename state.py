from dataclasses import dataclass, field
import numpy as np

@dataclass
class Peak:
    id: int
    x0: float
    y0: float
    # Overall FWHM. 0 means "not set yet" (no curve is drawn until the FWHM is given).
    # PV profile: fitted parameter.  TCH profile: derived from fwhm_g and fwhm_l.
    fwhm: float = 0.0
    # Fit Parameters
    a: float = 0.0
    g_ratio: float = 0.8      # Gaussian fraction (L fraction = 1 - g_ratio). TCH: derived.
    fwhm_g: float = 0.0       # TCH only: Gaussian FWHM
    fwhm_l: float = 0.0       # TCH only: Lorentzian FWHM
    area: float = 0.0         # derived (exact area of the profile)
    has_k_alpha2: bool = False
    show_gl_curves: bool = False

    # Locks for UI
    lock_x0: bool = False
    lock_a: bool = False
    lock_g_ratio: bool = False   # PV
    lock_fwhm: bool = False      # PV
    lock_fwhm_g: bool = False    # TCH
    lock_fwhm_l: bool = False    # TCH
    lock_all: bool = False

class AppState:
    def __init__(self):
        self.filename: str = ""
        
        # Raw Data
        self.raw_x: np.ndarray = np.array([])
        self.raw_y: np.ndarray = np.array([])
        
        # Working Data (filtered/smoothed)
        self.x: np.ndarray = np.array([])
        self.y: np.ndarray = np.array([])
        
        self.is_smoothed: bool = False
        
        # Baseline limits
        self.baseline_min_x: float = None
        self.baseline_max_x: float = None
        
        # Peaks
        self.peaks = []

        # Peak profile: "pv" (common FWHM, default) or "tch" (separate G/L widths, advanced)
        self.profile: str = "pv"
        
    def load_data(self, filename: str, x: np.ndarray, y: np.ndarray):
        self.filename = filename
        self.raw_x = x
        self.raw_y = y
        self.x = x.copy()
        self.y = y.copy()
        self.is_smoothed = False
        self.baseline_min_x = x.min()
        self.baseline_max_x = x.max()
        self.peaks = []
        
    def reorder_and_renumber_peaks(self):
        self.peaks.sort(key=lambda p: p.x0)
        for i, peak in enumerate(self.peaks, start=1):
            peak.id = i
            
    def add_peak(self, x0: float, y0: float) -> Peak:
        peak = Peak(id=max([p.id for p in self.peaks] + [0]) + 1, x0=x0, y0=y0)  # FWHM is set by the FWHM drag
        self.peaks.append(peak)
        self.reorder_and_renumber_peaks()
        return peak
        
    def get_clipped_data(self):
        if self.baseline_min_x is None or self.baseline_max_x is None:
            return self.x, self.y
            
        mask = (self.x >= self.baseline_min_x) & (self.x <= self.baseline_max_x)
        return self.x[mask], self.y[mask]

