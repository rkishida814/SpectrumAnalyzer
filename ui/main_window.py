import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QSplitter, QLineEdit, QToolBar, QMessageBox,
    QProgressBar, QComboBox
)
from PySide6.QtCore import Qt, Signal, QCoreApplication

from state import AppState, Peak
from ui.plot_canvas import PlotCanvas
from ui.peak_table import PeakTable

class MainWindow(QMainWindow):
    peak_added_signal = Signal(object)
    fwhm_drawn_signal = Signal(object)
    baseline_drawn_signal = Signal()
    
    def __init__(self, app_state: AppState, drag_drop_window):
        super().__init__()
        self.app_state = app_state
        self.drag_drop_window = drag_drop_window
        
        self.setWindowTitle("SpectrumAnalyzer")
        self.resize(1200, 800)
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        # Toolbar
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        back_btn = QPushButton("\u2190 Back")
        back_btn.clicked.connect(self.go_back)
        toolbar.addWidget(back_btn)
        toolbar.addSeparator()
        
        toolbar.addWidget(QLabel(" X Min: "))
        self.xmin_input = QLineEdit()
        self.xmin_input.setFixedWidth(80)
        self.xmin_input.returnPressed.connect(self.on_zoom_changed)
        toolbar.addWidget(self.xmin_input)
        
        toolbar.addWidget(QLabel(" X Max: "))
        self.xmax_input = QLineEdit()
        self.xmax_input.setFixedWidth(80)
        self.xmax_input.returnPressed.connect(self.on_zoom_changed)
        toolbar.addWidget(self.xmax_input)
        
        toolbar.addSeparator()
        
        self.btn_orig_view = QPushButton("Original View")
        toolbar.addWidget(self.btn_orig_view)
        
        self.btn_baseline = QPushButton("Baseline")
        self.btn_baseline.setCheckable(True)
        toolbar.addWidget(self.btn_baseline)
        
        self.btn_integral = QPushButton("Integral")
        toolbar.addWidget(self.btn_integral)
        
        self.btn_smooth = QPushButton("Smooth")
        self.btn_smooth.setCheckable(True)
        toolbar.addWidget(self.btn_smooth)
        
        toolbar.addSeparator()
        
        self.btn_peak_sel = QPushButton("Select Peak")
        self.btn_peak_sel.setCheckable(True)
        toolbar.addWidget(self.btn_peak_sel)
        
        self.btn_fwhm = QPushButton("Est. FWHM")
        self.btn_fwhm.setCheckable(True)
        toolbar.addWidget(self.btn_fwhm)
        
        self.btn_show_fit = QPushButton("Show Fit")
        self.btn_show_fit.setCheckable(True)
        self.btn_show_fit.setChecked(True)
        toolbar.addWidget(self.btn_show_fit)
        
        toolbar.addSeparator()
        self.lbl_error = QLabel(" MSE: N/A ")
        toolbar.addWidget(self.lbl_error)
        
        # Second Toolbar for Peak Management and Fitting
        self.addToolBarBreak()
        toolbar2 = QToolBar("Fit & Peaks Toolbar")
        self.addToolBar(toolbar2)
        
        self.btn_clear_peaks = QPushButton("Clear All Peaks")
        toolbar2.addWidget(self.btn_clear_peaks)
        toolbar2.addSeparator()
        
        self.btn_global_fit = QPushButton("ALL Fit \u2699")
        toolbar2.addWidget(self.btn_global_fit)
        
        toolbar2.addWidget(QLabel(" Profile: "))
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Pseudo-Voigt (common FWHM)", "pv")
        self.profile_combo.addItem("TCH pseudo-Voigt (separate G/L widths, advanced)", "tch")
        toolbar2.addWidget(self.profile_combo)

        toolbar2.addWidget(QLabel(" Algorithm: "))
        self.fit_algo_combo = QComboBox()
        self.fit_algo_combo.addItems(["trf", "dogbox"])
        toolbar2.addWidget(self.fit_algo_combo)
        
        toolbar2.addWidget(QLabel(" Progress: "))
        self.fit_progress = QProgressBar()
        self.fit_progress.setFixedWidth(200)
        self.fit_progress.setFixedHeight(15)
        self.fit_progress.setFormat("%v / %m")
        self.fit_progress.setValue(0)
        toolbar2.addWidget(self.fit_progress)
        
        # Central Layout with Splitter
        splitter = QSplitter(Qt.Vertical)
        
        # Top: Plot
        plot_wrapper = QWidget()
        plot_layout = QVBoxLayout(plot_wrapper)
        # Import mpl toolbar safely
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
        
        self.canvas = PlotCanvas(self.app_state, self)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        plot_layout.addWidget(self.mpl_toolbar)
        plot_layout.addWidget(self.canvas)
        
        # Bottom: Table and Controls
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        
        global_gl_layout = QHBoxLayout()
        global_gl_layout.addWidget(QLabel("Global G Fraction (0-1):"))
        self.global_g_input = QLineEdit("0.8")
        self.global_g_input.setFixedWidth(60)
        self.global_g_input.textEdited.connect(self._sync_global_l)
        global_gl_layout.addWidget(self.global_g_input)
        
        global_gl_layout.addWidget(QLabel("Global L Fraction (0-1):"))
        self.global_l_input = QLineEdit("0.2")
        self.global_l_input.setFixedWidth(60)
        self.global_l_input.textEdited.connect(self._sync_global_g)
        global_gl_layout.addWidget(self.global_l_input)
        
        self.btn_apply_gl = QPushButton("Apply to All Peaks")
        global_gl_layout.addWidget(self.btn_apply_gl)
        global_gl_layout.addStretch()
        table_layout.addLayout(global_gl_layout)
        
        self.table = PeakTable(self.app_state)
        table_layout.addWidget(self.table)
        
        splitter.addWidget(plot_wrapper)
        splitter.addWidget(table_container)
        splitter.setSizes([500, 300]) # Example size split
        
        self.setCentralWidget(splitter)

    def _connect_signals(self):
        self.peak_added_signal.connect(self.on_peak_added)
        self.fwhm_drawn_signal.connect(self.on_fwhm_drawn)
        self.baseline_drawn_signal.connect(self.on_baseline_drawn)
        self.table.peak_deleted.connect(self.on_peak_deleted)
        self.table.individual_fit_requested.connect(self.on_individual_fit)
        self.table.curve_redraw_requested.connect(self.canvas.draw_trial_curves)
        self.btn_global_fit.clicked.connect(self.on_global_fit)
        self.btn_clear_peaks.clicked.connect(self.on_clear_peaks)
        self.btn_show_fit.toggled.connect(self.on_show_fit_toggled)
        self.btn_apply_gl.clicked.connect(self.on_apply_global_gl)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        
        # Button groups for interaction modes
        self.btn_baseline.clicked.connect(lambda: self.set_interaction_mode('baseline', self.btn_baseline))
        self.btn_peak_sel.clicked.connect(lambda: self.set_interaction_mode('peak_select', self.btn_peak_sel))
        self.btn_fwhm.clicked.connect(lambda: self.set_interaction_mode('fwhm', self.btn_fwhm))
        
        self.btn_orig_view.clicked.connect(self.on_orig_view_clicked)
        
        # Preprocessing buttons
        self.btn_integral.clicked.connect(self.on_integral_clicked)
        self.btn_smooth.toggled.connect(self.on_smooth_toggled)

    def on_smooth_toggled(self, checked: bool):
        from core.math_utils import apply_sg_filter
        if checked:
            self.app_state.y = apply_sg_filter(self.app_state.raw_y)
        else:
            self.app_state.y = self.app_state.raw_y.copy()
            
        self.app_state.is_smoothed = checked
        self.canvas.update_data_y()
        
    def on_integral_clicked(self):
        self.canvas.draw_integral()

    def on_show_fit_toggled(self, checked: bool):
        self.canvas.show_global_fit = checked
        self.canvas.draw_trial_curves()

    def _sync_global_l(self, text):
        try:
            val = float(text)
            self.global_l_input.setText(f"{(1.0 - val):.2f}")
        except ValueError: pass

    def _sync_global_g(self, text):
        try:
            val = float(text)
            self.global_g_input.setText(f"{(1.0 - val):.2f}")
        except ValueError: pass

    def on_apply_global_gl(self):
        from core.fitter import set_width
        try:
            g = float(self.global_g_input.text())
        except ValueError:
            return
        g = max(0.0, min(1.0, g))
        for peak in self.app_state.peaks:
            # TCH: keeps the overall FWHM and recomputes the G/L widths for this fraction
            set_width(peak, peak.fwhm, g, self.app_state.profile)
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()

    def on_profile_changed(self, _index):
        from core.fitter import convert_profile
        profile = self.profile_combo.currentData()
        if profile == self.app_state.profile:
            return
        # Keep each peak's current shape (overall FWHM and G fraction) when switching
        for peak in self.app_state.peaks:
            convert_profile(peak, profile)
        self.app_state.profile = profile
        self.lbl_error.setText(" MSE: N/A ")
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()

    def set_interaction_mode(self, mode: str, btn: QPushButton):
        # Mutual exclusion
        for b in [self.btn_baseline, self.btn_peak_sel, self.btn_fwhm]:
            if b != btn:
                b.setChecked(False)
                
        if btn.isChecked():
            self.canvas.interaction_mode = mode
        else:
            self.canvas.interaction_mode = 'none'

    def showEvent(self, event):
        super().showEvent(event)
        if self.app_state.filename:
            self.setWindowTitle(f"SpectrumAnalyzer - {self.app_state.filename}")
        self.canvas.draw_initial_data()
        self.table.rebuild_table()
        
    def on_clear_peaks(self):
        self.app_state.peaks.clear()
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()

    def go_back(self):
        self.btn_baseline.setChecked(False)
        self.btn_peak_sel.setChecked(False)
        self.btn_fwhm.setChecked(False)
        self.btn_smooth.setChecked(False)
        self.btn_show_fit.setChecked(True)
        self.lbl_error.setText(" MSE: N/A ")
        if getattr(self, 'canvas', None):
            self.canvas.reset_state()
            self.canvas.interaction_mode = 'none'
            self.canvas.show_global_fit = True
            
        self.hide()
        self.drag_drop_window.show()

    def on_orig_view_clicked(self):
        self.canvas.reset_view()
        self.btn_baseline.setChecked(False)
        self.btn_peak_sel.setChecked(False)
        self.btn_fwhm.setChecked(False)
        self.canvas.interaction_mode = 'none'

    def on_zoom_changed(self):
        try:
            xmin = float(self.xmin_input.text())
            xmax = float(self.xmax_input.text())
            self.canvas.set_x_zoom(xmin, xmax)
            self.btn_baseline.setChecked(True)
            self.set_interaction_mode('baseline', self.btn_baseline)
        except ValueError:
            pass
            
    def on_baseline_drawn(self):
        self.btn_baseline.setChecked(False)
        self.btn_peak_sel.setChecked(True)
        self.canvas.interaction_mode = 'peak_select'
        
    def on_peak_added(self, peak: Peak):
        self.table.rebuild_table()
        # Ensure the newly added peak is selected so FWHM drawing applies to it
        row = len(self.app_state.peaks) - 1
        if row >= 0:
            self.table.selectRow(row)
            
        self.btn_peak_sel.setChecked(False)
        self.btn_fwhm.setChecked(True)
        self.canvas.interaction_mode = 'fwhm'

    def on_fwhm_drawn(self, data):
        from core.fitter import set_width
        peak, fwhm = data
        # Common FWHM: the drawn width is the FWHM itself.
        # TCH: the G/L widths are derived so that the overall FWHM equals the drawn width.
        set_width(peak, fwhm, peak.g_ratio, self.app_state.profile)
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()
        
        self.btn_fwhm.setChecked(False)
        self.btn_peak_sel.setChecked(True)
        self.canvas.interaction_mode = 'peak_select'

    def on_individual_fit(self, peak: Peak):
        from core.fitter import fit_individual_peak
        from core.math_utils import calculate_baseline_y
        import numpy as np
        
        x_data, y_data = self.app_state.get_clipped_data()
        if len(x_data) == 0:
            return
            
        base_y = np.zeros_like(x_data)
        if self.canvas.baseline_pts:
            base_y = calculate_baseline_y(x_data, *self.canvas.baseline_pts)
            
        self.fit_progress.setMaximum(0)
        self.fit_progress.setValue(0)
            
        def update_ui(step=None, max_nfev=None):
            if step is not None:
                if max_nfev is not None and self.fit_progress.maximum() != max_nfev:
                    self.fit_progress.setMaximum(max_nfev)
                self.fit_progress.setValue(step)
            # Remove redraws from here to fix UI freeze and timeout errors!
            QCoreApplication.processEvents()
            
        algo = self.fit_algo_combo.currentText()
        is_timeout = False
        try:
            mse = fit_individual_peak(x_data, y_data, base_y, peak, max_nfev=1500, method=algo, timeout=45.0,
                                      callback_fn=update_ui, profile=self.app_state.profile)
            self.lbl_error.setText(f" MSE: {mse:.4f} ")
            if self.fit_progress.maximum() > 0:
                self.fit_progress.setValue(self.fit_progress.maximum())
        except TimeoutError:
            is_timeout = True
            
        # Draw exactly once at the end
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()
        
        if is_timeout:
            QMessageBox.warning(self, "Timeout", "Fitting exceeded 45 seconds and was aborted. Results may be incomplete.")
            self.fit_progress.setValue(0)

    def on_global_fit(self):
        from core.fitter import fit_global_peaks
        from core.math_utils import calculate_baseline_y
        import numpy as np
        
        x_data, y_data = self.app_state.get_clipped_data()
        if len(x_data) == 0 or len(self.app_state.peaks) == 0:
            return
            
        base_y = np.zeros_like(x_data)
        if self.canvas.baseline_pts:
            base_y = calculate_baseline_y(x_data, *self.canvas.baseline_pts)
            
        self.fit_progress.setMaximum(0)
        self.fit_progress.setValue(0)
            
        def update_ui(step=None, max_nfev=None):
            if step is not None:
                if max_nfev is not None and self.fit_progress.maximum() != max_nfev:
                    self.fit_progress.setMaximum(max_nfev)
                self.fit_progress.setValue(step)
            # Remove redraws from here to fix UI freeze and timeout errors!
            QCoreApplication.processEvents()
            
        algo = self.fit_algo_combo.currentText()
        is_timeout = False
        try:
            # Allow more iterations per peak for global fitting
            max_evals = max(1500, 500 * len(self.app_state.peaks))
            mse = fit_global_peaks(x_data, y_data, base_y, self.app_state.peaks, max_nfev=max_evals, method=algo,
                                   timeout=45.0, callback_fn=update_ui, profile=self.app_state.profile)
            self.lbl_error.setText(f" G-MSE: {mse:.4f} ")
            if self.fit_progress.maximum() > 0:
                self.fit_progress.setValue(self.fit_progress.maximum())
        except TimeoutError:
            is_timeout = True
            
        # Draw exactly once at the end
        self.canvas.draw_trial_curves()
        self.table.rebuild_table()
        
        if is_timeout:
            QMessageBox.warning(self, "Timeout", "Global fitting exceeded 45 seconds and was aborted. Results may be incomplete.")
            self.fit_progress.setValue(0)

    def on_peak_deleted(self, peak: Peak):
        self.app_state.peaks.remove(peak)
        self.app_state.reorder_and_renumber_peaks()
        self.table.rebuild_table()
        self.canvas.draw_trial_curves()


