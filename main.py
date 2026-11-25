import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
import traceback

def exception_hook(exctype, value, tb):
    print("".join(traceback.format_exception(exctype, value, tb)))
    QMessageBox.critical(None, "Unhandled Exception", str(value))
    sys.exit(1)

sys.excepthook = exception_hook

def main():
    app = QApplication(sys.argv)
    
    from state import AppState
    from ui.drag_drop_window import DragDropWindow
    from ui.main_window import MainWindow
    
    app_state = AppState()
    
    drag_window = DragDropWindow(app_state)
    
    def on_data_loaded():
        # Instantiate or update MainWindow
        if drag_window.main_window_instance is None:
            drag_window.main_window_instance = MainWindow(app_state, drag_window)
        else:
            # Maybe update plot if same instance reused
            pass
            
        drag_window.main_window_instance.show()
        drag_window.hide()
        
    drag_window.data_loaded.connect(on_data_loaded)
    drag_window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
