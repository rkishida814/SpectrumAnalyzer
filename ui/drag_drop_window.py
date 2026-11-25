import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, 
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from core.parser import parse_xrd_file
from state import AppState

class DragDropWindow(QWidget):
    # Signal emitted when data is successfully loaded
    data_loaded = Signal()

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.main_window_instance = None  # Reference to the main window
        
        self.setWindowTitle("SpectrumAnalyzer - Data Loader")
        self.resize(400, 300)
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel("Drag & Drop \nXRD data here (.xy, .txt, .csv, ...)")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                font-size: 16px;
                color: #555;
            }
        """)
        layout.addWidget(self.label)
        
        self.forward_btn = QPushButton("Forward to Plot \u2192")
        self.forward_btn.setVisible(False)
        self.forward_btn.clicked.connect(self.go_forward)
        layout.addWidget(self.forward_btn)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                filepath = urls[0].toLocalFile()
                # Any two-column text file is accepted (.xy, .txt, .csv, .dat, ...);
                # the parser reports an error if no numeric data is found.
                if filepath and os.path.isfile(filepath):
                    event.acceptProposedAction()
                    self.label.setStyleSheet("""
                        QLabel {
                            border: 2px dashed #4CAF50;
                            border-radius: 10px;
                            font-size: 16px;
                            color: #4CAF50;
                            background-color: #e8f5e9;
                        }
                    """)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._reset_label_style()

    def dropEvent(self, event: QDropEvent):
        self._reset_label_style()
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            self._process_file(filepath)

    def _reset_label_style(self):
        self.label.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                font-size: 16px;
                color: #555;
                background-color: transparent;
            }
        """)

    def _process_file(self, filepath: str):
        try:
            x, y = parse_xrd_file(filepath)
            if len(x) == 0:
                raise ValueError("No valid numerical data found in the file.")
                
            filename = os.path.basename(filepath)
            self.app_state.load_data(filename, x, y)
            self.data_loaded.emit()
            
            # Show forward button for subsequent visits
            filename = os.path.basename(filepath)
            self.forward_btn.setText(f"Forward to {filename} \u2192")
            self.forward_btn.setVisible(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error Loading File", f"Failed to parse file:\n{str(e)}")
            
    def go_forward(self):
        if self.main_window_instance:
            self.main_window_instance.show()
            self.hide()
