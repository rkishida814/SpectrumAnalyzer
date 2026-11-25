from PySide6.QtWidgets import QSizePolicy
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
import numpy as np
from state import AppState

class PlotCanvas(FigureCanvasQTAgg):
    def __init__(self, app_state: AppState, parent=None):
        self.app_state = app_state
        self.main_window = parent
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # Sizing and policies
        super().setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        super().updateGeometry()
        
        # References for drawn artists
        self.scatter_plot = None
        self.baseline_line = None
        self.baseline_pts = None
        self.trial_curves = []
        self.peak_markers = []
        self.integration_lines = []
        self.fwhm_lines = []
        self.integration_text = None
        
        self.show_global_fit = True
        self.global_fit_curve = None
        
        # Colors for trial curves
        self.colors = ['#fb756c', '#a7a923', '#0eba72', '#21b4fa', '#e96bf5', '#9977cc', '#5300ed']

        
        # Interactivity state
        self.interaction_mode = 'none' # 'none', 'baseline', 'peak_select', 'fwhm'
        self.drag_start = None
        self.temp_artist = None
        
        self.cid_press = self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_release = self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_motion = self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def draw_initial_data(self):
        self.ax.clear()
        
        x, y = self.app_state.x, self.app_state.y
        if len(x) > 0:
            # Scatter plot, empty circles (default) or just dot markers, no line
            self.scatter_plot, = self.ax.plot(x, y, 'o', markersize=3, 
                                              markerfacecolor='none', 
                                              markeredgecolor='black', alpha=0.7)
            
            # Set initial zoom to min/max
            self.ax.set_xlim(x.min(), x.max())
            self._auto_y_zoom(x.min(), x.max())
            self.fig.tight_layout()
            self.draw_idle()

    def update_data_y(self):
        if self.scatter_plot:
            self.scatter_plot.set_ydata(self.app_state.y)
            self.draw_trial_curves()
            self.draw_idle()
            
    def set_x_zoom(self, x_min: float, x_max: float):
        self.ax.set_xlim(x_min, x_max)
        self._auto_y_zoom(x_min, x_max)
        self.draw_idle()

    def reset_view(self):
        if len(self.app_state.x) > 0:
            x_min, x_max = self.app_state.x.min(), self.app_state.x.max()
            self.ax.set_xlim(x_min, x_max)
            self._auto_y_zoom(x_min, x_max)
            if self.main_window:
                self.main_window.xmin_input.setText(f"{x_min:.3f}")
                self.main_window.xmax_input.setText(f"{x_max:.3f}")
            self.draw_idle()
            
    def reset_state(self):
        self.interaction_mode = 'none'
        self.drag_start = None
        if self.temp_artist:
            self.temp_artist.remove()
            self.temp_artist = None
        if self.baseline_line:
            self.baseline_line.remove()
            self.baseline_line = None
        self.baseline_pts = None
        self.clear_integral_visuals()
        for c in self.trial_curves:
            c.remove() # type: ignore
        self.trial_curves.clear()
        for m in self.peak_markers:
            m.remove() # type: ignore
        self.peak_markers.clear()
        if self.global_fit_curve:
            self.global_fit_curve.remove() # type: ignore
            self.global_fit_curve = None
        self.ax.clear()
        self.draw_idle()

    def _auto_y_zoom(self, x_min: float, x_max: float):
        # Auto y zoom given x limits
        x, y = self.app_state.x, self.app_state.y
        if len(x) == 0:
            return
            
        mask = (x >= x_min) & (x <= x_max)
        if not np.any(mask):
            return
            
        y_visible = y[mask]
        y_min, y_max = y_visible.min(), y_visible.max()
        margin = (y_max - y_min) * 0.1
        if margin == 0:
            margin = 1.0
        self.ax.set_ylim(y_min - margin, y_max + margin)

    # Mouse Event Handlers for Preprocessing / UI
    def on_press(self, event):
        if event.inaxes != self.ax:
            return
        if self.interaction_mode in ['none', 'baseline', 'peak_select', 'fwhm']:
            self.drag_start = (event.xdata, event.ydata)

    def on_motion(self, event):
        if self.drag_start is None or event.inaxes != self.ax:
            return
            
        x0, y0 = self.drag_start
        x1, y1 = event.xdata, event.ydata
        
        if self.interaction_mode == 'baseline':
            if self.temp_artist:
                self.temp_artist.remove()
            self.temp_artist, = self.ax.plot([x0, x1], [y0, y1], 'r-', lw=2)
            self.draw_idle()
            
        elif self.interaction_mode in ['peak_select', 'none']:
            if self.temp_artist:
                self.temp_artist.remove()
            # Draw semi-transparent blue rectangle horizontally
            width = x1 - x0
            # From axes min y to max y conceptually
            ymin, ymax = self.ax.get_ylim()
            from matplotlib.patches import Rectangle
            rect = Rectangle((min(x0, x1), ymin), abs(width), ymax-ymin, 
                             color='blue', alpha=0.2)
            self.ax.add_patch(rect)
            self.temp_artist = rect
            self.draw_idle()
            
        elif self.interaction_mode == 'fwhm':
            if self.temp_artist:
                self.temp_artist.remove()
            # Draw green horizontal line
            self.temp_artist, = self.ax.plot([x0, x1], [y0, y0], 'g-', lw=2)
            self.draw_idle()

    def on_release(self, event):
        if self.drag_start is None or event.inaxes != self.ax:
            self.drag_start = None
            if self.temp_artist:
                self.temp_artist.remove()
                self.temp_artist = None
                self.draw_idle()
            return
            
        x0, y0 = self.drag_start
        x1, y1 = event.xdata, event.ydata
        self.drag_start = None
        
        if self.temp_artist:
            self.temp_artist.remove()
            self.temp_artist = None
            
        if self.interaction_mode == 'baseline':
            self._finalize_baseline(x0, y0, x1, y1)
        elif self.interaction_mode == 'peak_select':
            self._finalize_peak_select(x0, x1)
        elif self.interaction_mode == 'fwhm':
            self._finalize_fwhm(x0, x1, y0)
        elif self.interaction_mode == 'none':
            self._finalize_zoom_drag(x0, x1)
            
    def _finalize_zoom_drag(self, x0, x1):
        x_min, x_max = min(x0, x1), max(x0, x1)
        if abs(x_max - x_min) > 1e-4:
            self.set_x_zoom(x_min, x_max)
            if self.main_window:
                self.main_window.xmin_input.setText(f"{x_min:.3f}")
                self.main_window.xmax_input.setText(f"{x_max:.3f}")
                self.main_window.btn_baseline.setChecked(True)
                self.main_window.set_interaction_mode('baseline', self.main_window.btn_baseline)

    def _finalize_baseline(self, x0, y0, x1, y1):
        if self.baseline_line:
            self.baseline_line.remove()
            
        # Ensure x0 <= x1
        if x0 > x1:
            x0, x1 = x1, x0
            y0, y1 = y1, y0
            
        self.baseline_pts = (x0, y0, x1, y1)
        self.baseline_line, = self.ax.plot([x0, x1], [y0, y1], 'r-', lw=2)
        self.app_state.baseline_min_x = x0
        self.app_state.baseline_max_x = x1
        self.draw_idle()
        if self.main_window:
            self.main_window.baseline_drawn_signal.emit()

    def draw_integral(self):
        from core.math_utils import calculate_baseline_y, calculate_integral
        from PySide6.QtWidgets import QApplication
        
        if not self.baseline_pts:
            return
            
        x0, y0, x1, y1 = self.baseline_pts
        x_data, y_data = self.app_state.get_clipped_data()
        
        base_y = calculate_baseline_y(x_data, x0, y0, x1, y1)
        area = calculate_integral(x_data, y_data, base_y)
        
        # Draw vertical red lines
        for l in self.integration_lines:
            l.remove()
        self.integration_lines.clear()
        
        # For visual clarity, draw red lines densely
        step = max(1, len(x_data) // 1000)
        from matplotlib.collections import LineCollection
        segments = [[[float(x_data[i]), float(base_y[i])], [float(x_data[i]), float(y_data[i])]] for i in range(0, len(x_data), step)]
        lc = LineCollection(segments, colors='red', linewidths=0.5, alpha=0.5)
        self.ax.add_collection(lc)
        self.integration_lines.append(lc)
        
        if self.integration_text:
            self.integration_text.remove() # type: ignore
            
        text_str = f"Area = {area:.2f}"
        self.integration_text = self.ax.text(0.5, 0.95, text_str, transform=self.ax.transAxes, 
                                             ha='center', va='top', bbox={"facecolor": "white", "alpha": 0.8})
        self.draw_idle()
        
        # Copy to clipboard
        QApplication.clipboard().setText(str(area))
        
        # Timer to clear visual after a short time
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self.clear_integral_visuals)

    def clear_integral_visuals(self):
        for l in self.integration_lines:
            l.remove() # type: ignore
        self.integration_lines.clear()
        if self.integration_text:
            self.integration_text.remove() # type: ignore
            self.integration_text = None
        self.draw_idle()
        
    def draw_trial_curves(self):
        from core.math_utils import pseudo_voigt, calculate_baseline_y
        for c in self.trial_curves:
            c.remove() # type: ignore
        self.trial_curves.clear()
        
        if self.global_fit_curve:
            self.global_fit_curve.remove() # type: ignore
            self.global_fit_curve = None
            
        # Draw peak markers
        for m in self.peak_markers:
            m.remove() # type: ignore
        self.peak_markers.clear()
        
        x_data, y_data = self.app_state.get_clipped_data()
        if len(x_data) == 0:
            return
            
        x_plot = np.linspace(x_data.min(), x_data.max(), max(len(x_data) * 2, 1000))
        base_y_plot = np.zeros_like(x_plot)
        if self.baseline_pts:
            x0, y0, x1, y1 = self.baseline_pts
            base_y_plot = calculate_baseline_y(x_plot, x0, y0, x1, y1)
            
        for i, peak in enumerate(self.app_state.peaks):
            color = self.colors[i % len(self.colors)]
            
            # Reconstruct peak marker
            m, = self.ax.plot([peak.x0, peak.x0], [peak.y0, peak.y0 + (self.ax.get_ylim()[1]*0.05)], 
                              color=color, lw=2)
            self.peak_markers.append(m)
            
            # If FWHM is set
            if peak.fwhm > 0:
                y_curve, comp_g, comp_l = pseudo_voigt(x_plot, peak.a, peak.x0, peak.fwhm, peak.g_ratio, return_components=True)
                c, = self.ax.plot(x_plot, y_curve + base_y_plot, color=color, lw=2)
                self.trial_curves.append(c)
                
                if peak.show_gl_curves:
                    from matplotlib.colors import to_rgb
                    import colorsys
                    
                    def adjust_lightness(c_hex, amount=1.0):
                        c = colorsys.rgb_to_hls(*to_rgb(c_hex))
                        if amount > 1.0:
                            factor = min(1.0, amount - 1.0)
                            new_l = c[1] + (1.0 - c[1]) * factor
                        else:
                            new_l = c[1] * amount
                        return colorsys.hls_to_rgb(c[0], max(0.0, min(1.0, new_l)), c[2])
                        
                    color_bright = adjust_lightness(color, 1.4)
                    color_dark = adjust_lightness(color, 0.6)
                    
                    # Gaussian (brighter)
                    c_g, = self.ax.plot(x_plot, comp_g + base_y_plot, color=color_bright, lw=1.5, linestyle=':')
                    self.trial_curves.append(c_g)
                    
                    # Lorentzian (darker)
                    c_l, = self.ax.plot(x_plot, comp_l + base_y_plot, color=color_dark, lw=1.5, linestyle=':')
                    self.trial_curves.append(c_l)
                
                if peak.has_k_alpha2:
                    from core.math_utils import calc_k_alpha2_shift
                    shift = calc_k_alpha2_shift(peak.x0)
                    ka2_x0 = peak.x0 + shift
                    ka2_y = pseudo_voigt(x_plot, peak.a * 0.5, ka2_x0, peak.fwhm, peak.g_ratio)
                    c2, = self.ax.plot(x_plot, ka2_y + base_y_plot, color=color, lw=2, linestyle='--')
                    self.trial_curves.append(c2)
                    
        # Render total global fit curve
        if self.show_global_fit and len(self.app_state.peaks) > 0:
            total_y = base_y_plot.copy()
            for peak in self.app_state.peaks:
                if peak.fwhm > 0:
                    total_y += pseudo_voigt(x_plot, peak.a, peak.x0, peak.fwhm, peak.g_ratio)
                    if peak.has_k_alpha2:
                        from core.math_utils import calc_k_alpha2_shift
                        shift = calc_k_alpha2_shift(peak.x0)
                        ka2_x0 = peak.x0 + shift
                        total_y += pseudo_voigt(x_plot, peak.a * 0.5, ka2_x0, peak.fwhm, peak.g_ratio)
            
            self.global_fit_curve, = self.ax.plot(x_plot, total_y, color='black', lw=2)
                    
        self.draw_idle()

    def _finalize_peak_select(self, x0, x1):
        x_min, x_max = min(x0, x1), max(x0, x1)
        x_data, y_data = self.app_state.get_clipped_data()
        
        mask = (x_data >= x_min) & (x_data <= x_max)
        if not np.any(mask):
            return
            
        x_roi = x_data[mask]
        y_roi = y_data[mask]
        
        # Compute baseline subtracted y internally to find peak
        base_y_roi = np.zeros_like(y_roi)
        if self.baseline_pts:
            from core.math_utils import calculate_baseline_y
            base_y_roi = calculate_baseline_y(x_roi, *self.baseline_pts)
            
        y_subbed = y_roi - base_y_roi
        max_idx = np.argmax(y_subbed)
        peak_x = x_roi[max_idx]
        peak_y = y_roi[max_idx]
        peak_a = y_subbed[max_idx]
        
        # Add to state
        new_peak = self.app_state.add_peak(peak_x, peak_y)
        new_peak.a = peak_a
        
        self.draw_trial_curves()
        
        # Emit signal to update table
        if self.main_window:
            self.main_window.peak_added_signal.emit(new_peak)

    def _finalize_fwhm(self, x0, x1, y):
        width = abs(x1 - x0)
        center_x = (x0 + x1) / 2.0
        
        # Don't rely on the table selection. Find the nearest peak in the state.
        if len(self.app_state.peaks) == 0:
            return
            
        # Find peak closest to the center_x of the drawn line
        closest_peak = None
        min_dist = float('inf')
        for peak in self.app_state.peaks:
            dist = abs(peak.x0 - center_x)
            if dist < min_dist:
                min_dist = dist
                closest_peak = peak
                
        if closest_peak and self.main_window:
            # Emit the drawn width along with the specific peak we intend to modify
            self.main_window.fwhm_drawn_signal.emit((closest_peak, width))
