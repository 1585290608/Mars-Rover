import sys
from PyQt6.QtWidgets import QApplication
from gui_main import RoverGUI


def main():
    app = QApplication(sys.argv)
    window = RoverGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
