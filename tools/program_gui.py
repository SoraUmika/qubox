from __future__ import annotations

import importlib
import inspect
import numbers
import sys
from collections.abc import Callable

import numpy as np
from PyQt5 import QtCore, QtWidgets

try:
    pg = importlib.import_module("pyqtgraph")
except ImportError:  # pragma: no cover - optional GUI dependency
    pg = None


class ProgramRunnerGUI(QtWidgets.QMainWindow):
    """Live-update GUI for repeatedly running a callable and plotting one output key."""

    def __init__(self, program_dict: dict[str, Callable], timer_ms: int = 500):
        super().__init__()

        if pg is None:
            raise RuntimeError("pyqtgraph is required to use tools/program_gui.py")

        self.setWindowTitle("Live Experiment Runner")
        self.program_dict = program_dict
        self.current_program_name: str | None = None
        self.current_program: Callable | None = None
        self._last_keys: list[str] = []

        self.timer = QtCore.QTimer(self, interval=timer_ms)
        self.timer.timeout.connect(self._acquire)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        top_bar = QtWidgets.QHBoxLayout()
        layout.addLayout(top_bar)
        top_bar.addWidget(QtWidgets.QLabel("Program:"))
        self.program_combo = QtWidgets.QComboBox()
        self.program_combo.addItems(self.program_dict.keys())
        self.program_combo.currentTextChanged.connect(self._program_changed)
        top_bar.addWidget(self.program_combo)
        top_bar.addStretch(1)

        self.param_scroll = QtWidgets.QScrollArea()
        self.param_container = QtWidgets.QWidget()
        self.param_form = QtWidgets.QFormLayout(self.param_container)
        self.param_scroll.setWidget(self.param_container)
        self.param_scroll.setWidgetResizable(True)
        layout.addWidget(self.param_scroll, stretch=0)

        self.plot_widget = pg.PlotWidget()
        self.curve = self.plot_widget.plot(pen="y")
        layout.addWidget(self.plot_widget, stretch=1)

        bottom_bar = QtWidgets.QHBoxLayout()
        layout.addLayout(bottom_bar)
        bottom_bar.addWidget(QtWidgets.QLabel("Plot:"))
        self.key_combo = QtWidgets.QComboBox()
        bottom_bar.addWidget(self.key_combo)
        bottom_bar.addStretch(1)
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        bottom_bar.addWidget(self.start_btn)
        bottom_bar.addWidget(self.stop_btn)
        self.start_btn.clicked.connect(self.timer.start)
        self.stop_btn.clicked.connect(self.timer.stop)

        self._program_changed(self.program_combo.currentText())

    def _program_changed(self, name: str) -> None:
        if not name:
            return
        self.current_program_name = name
        self.current_program = self.program_dict[name]
        self.timer.stop()

        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.param_widgets: dict[str, QtWidgets.QWidget] = {}

        sig = inspect.signature(self.current_program)
        for param in sig.parameters.values():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            widget = self._widget_for_param(param)
            self.param_form.addRow(param.name, widget)
            self.param_widgets[param.name] = widget

        self.key_combo.clear()
        self._last_keys.clear()

    def _widget_for_param(self, param: inspect.Parameter) -> QtWidgets.QWidget:
        default = None if param.default is inspect._empty else param.default

        if isinstance(default, bool):
            widget = QtWidgets.QCheckBox()
            widget.setChecked(default)
            return widget

        if isinstance(default, numbers.Integral):
            widget = QtWidgets.QSpinBox()
            widget.setRange(-1_000_000_000, 1_000_000_000)
            widget.setValue(int(default))
            return widget

        if isinstance(default, numbers.Real):
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(6)
            widget.setRange(-1e12, 1e12)
            widget.setSingleStep(max(abs(float(default)) / 1000, 0.1))
            widget.setValue(float(default))
            return widget

        return QtWidgets.QLineEdit(str(default or ""))

    def _current_params(self) -> dict[str, object]:
        params: dict[str, object] = {}
        for name, widget in self.param_widgets.items():
            if isinstance(widget, QtWidgets.QSpinBox):
                params[name] = widget.value()
            elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                params[name] = widget.value()
            elif isinstance(widget, QtWidgets.QCheckBox):
                params[name] = widget.isChecked()
            else:
                text = widget.text()
                try:
                    params[name] = float(text) if "." in text else int(text)
                except ValueError:
                    params[name] = text
        return params

    def _acquire(self) -> None:
        if self.current_program is None:
            return

        params = self._current_params()
        try:
            result = self.current_program(**params).output
        except Exception as exc:  # pragma: no cover - GUI feedback path
            print(f"Program error: {exc}")
            return

        result = self._coerce_result(result)
        if result is None:
            return

        if not self._last_keys or set(result.keys()) != set(self._last_keys):
            self.key_combo.blockSignals(True)
            self.key_combo.clear()
            for key in result.keys():
                self.key_combo.addItem(key)
            self.key_combo.blockSignals(False)
            self._last_keys = list(result.keys())

        ykey = self.key_combo.currentText() or next(iter(result.keys()))
        y = np.asarray(result[ykey])
        xkey = "frequencies" if "frequencies" in result else None
        x = np.asarray(result.get(xkey, np.arange(len(y))))
        if y.dtype.kind == "c":
            y = np.abs(y)

        self.curve.setData(x, y)
        self.plot_widget.enableAutoRange()

    def _coerce_result(self, result):
        if isinstance(result, dict):
            return result

        if isinstance(result, (tuple, list)):
            return {f"col_{index}": value for index, value in enumerate(result)}

        if hasattr(result, "extract") and callable(result.extract):
            try:
                extracted = result.extract()
            except TypeError:  # pragma: no cover - GUI feedback path
                print("extract() requires arguments; wrap your program to return a dict instead.")
                return None

            if isinstance(extracted, dict):
                return extracted
            if (
                isinstance(extracted, (tuple, list))
                and len(extracted) == 2
                and isinstance(extracted[0], (list, tuple))
                and isinstance(extracted[1], (list, tuple))
            ):
                return dict(zip(extracted[0], extracted[1]))
            print("Do not know how to interpret result.extract() output; wrap your program.")
            return None

        print("Unsupported return type:", type(result))
        return None


def _normalise_programs(programs: dict[str, Callable] | Callable) -> dict[str, Callable]:
    if isinstance(programs, dict):
        return programs
    if callable(programs):
        name = getattr(programs, "__name__", "Program")
        return {name: programs}
    raise TypeError("programs must be a callable or a mapping of str to callable")


def run_gui(programs: dict[str, Callable] | Callable, *, timer_ms: int = 500) -> None:
    program_map = _normalise_programs(programs)
    app = QtWidgets.QApplication(sys.argv)
    gui = ProgramRunnerGUI(program_map, timer_ms=timer_ms)
    gui.resize(1000, 600)
    gui.show()
    sys.exit(app.exec_())
