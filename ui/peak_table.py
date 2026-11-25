from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, QHBoxLayout, QWidget, QHeaderView
from PySide6.QtCore import Qt, Signal, QTimer

from state import AppState, Peak
from core.fitter import TCH, refresh_peak

LOCK = "🔒"

# Column specs: (kind, header, field)
#   num  : editable number      ro   : read-only number (derived)
#   lock : lock checkbox        others: special widgets
_HEAD = [("del", "Del", None), ("lock_all", "Lock All", None), ("id", "Peak #", None),
         ("num", "X (x0)", "x0"), ("lock", LOCK, "lock_x0"),
         ("num", "A", "a"), ("lock", LOCK, "lock_a")]
_TAIL = [("ro", "Area", "area"), ("ka2", "K-a2", None), ("fit", "Fit", None), ("gl", "G/L", None)]

COLUMNS_PV = _HEAD + [
    ("num", "G Frac", "g_ratio"), ("num", "L Frac", "l_ratio"), ("lock", LOCK, "lock_g_ratio"),
    ("num", "FWHM", "fwhm"), ("lock", LOCK, "lock_fwhm"),
] + _TAIL

COLUMNS_TCH = _HEAD + [
    ("num", "FWHM_G", "fwhm_g"), ("lock", LOCK, "lock_fwhm_g"),
    ("num", "FWHM_L", "fwhm_l"), ("lock", LOCK, "lock_fwhm_l"),
    ("ro", "G Frac", "g_ratio"), ("ro", "L Frac", "l_ratio"), ("ro", "FWHM", "fwhm"),
] + _TAIL


def _value(peak: Peak, field: str) -> float:
    return 1.0 - peak.g_ratio if field == "l_ratio" else getattr(peak, field)


class PeakTable(QTableWidget):
    peak_deleted = Signal(object)
    individual_fit_requested = Signal(object)
    curve_redraw_requested = Signal()

    def __init__(self, app_state: AppState):
        super().__init__(0, 0)
        self.app_state = app_state
        self.columns = []

        # Custom delegate to clear text upon editing to prevent visual overlap bugs
        from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit
        class ClearEditorDelegate(QStyledItemDelegate):
            def createEditor(self, parent, option, index):
                return QLineEdit(parent)  # left blank so the user types fresh

        self.setItemDelegate(ClearEditorDelegate(self))
        self.itemChanged.connect(self.on_item_changed)
        self.rebuild_table()

    def rebuild_table(self):
        self.blockSignals(True)
        self.columns = COLUMNS_TCH if self.app_state.profile == TCH else COLUMNS_PV
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels([c[1] for c in self.columns])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setRowCount(len(self.app_state.peaks))
        for row, peak in enumerate(self.app_state.peaks):
            self._populate_row(row, peak)
        self.blockSignals(False)

    def _centered(self, w):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.addWidget(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(0, 0, 0, 0)
        return box

    def _checkbox(self, peak: Peak, prop: str, label: str = ""):
        cb = QCheckBox(label)
        cb.setChecked(getattr(peak, prop))
        cb.toggled.connect(lambda checked, p=peak: self._update_peak_prop(p, prop, checked))
        return self._centered(cb)

    def _populate_row(self, row: int, peak: Peak):
        for col, (kind, _, field) in enumerate(self.columns):
            if kind == "del":
                btn = QPushButton("🗑️")
                btn.clicked.connect(lambda _, p=peak: self.peak_deleted.emit(p))
                self.setCellWidget(row, col, btn)
            elif kind == "lock_all":
                self.setCellWidget(row, col, self._checkbox(peak, "lock_all", LOCK))
            elif kind == "id":
                item = QTableWidgetItem(f"Peak #{peak.id}")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.setItem(row, col, item)
            elif kind in ("num", "ro"):
                item = QTableWidgetItem(f"{_value(peak, field):.4f}")
                if kind == "ro":
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.setItem(row, col, item)
            elif kind == "lock":
                self.setCellWidget(row, col, self._checkbox(peak, field))
            elif kind == "ka2":
                self.setCellWidget(row, col, self._checkbox(peak, "has_k_alpha2", "K-α2"))
            elif kind == "fit":
                btn = QPushButton("Fit")
                btn.clicked.connect(lambda _, p=peak: self.individual_fit_requested.emit(p))
                self.setCellWidget(row, col, btn)
            elif kind == "gl":
                self.setCellWidget(row, col, self._checkbox(peak, "show_gl_curves", "G/L"))

    def _update_peak_prop(self, peak: Peak, prop: str, value):
        setattr(peak, prop, value)
        self.curve_redraw_requested.emit()

    def on_item_changed(self, item):
        row, col = item.row(), item.column()
        if row >= len(self.app_state.peaks) or col >= len(self.columns):
            return
        kind, _, field = self.columns[col]
        if kind != "num":
            return
        peak = self.app_state.peaks[row]
        try:
            val = float(item.text())
        except ValueError:
            QTimer.singleShot(0, self.rebuild_table)  # revert the cell
            return
        if field == "g_ratio":
            peak.g_ratio = max(0.0, min(1.0, val))
        elif field == "l_ratio":
            peak.g_ratio = 1.0 - max(0.0, min(1.0, val))
        elif field in ("fwhm", "fwhm_g", "fwhm_l"):
            setattr(peak, field, max(0.0, val))
        else:
            setattr(peak, field, val)
        refresh_peak(peak, self.app_state.profile)
        # Update derived cells (Area, FWHM, ...) after the edit has finished
        QTimer.singleShot(0, self.rebuild_table)
        self.curve_redraw_requested.emit()
