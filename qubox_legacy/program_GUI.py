import sys
import inspect
import numbers
from collections.abc import Callable

import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg


class ProgramRunnerGUI(QtWidgets.QMainWindow):
    """Generic live‑update GUI that can run **any** callable repeatedly,
    auto‑generate parameter controls from its signature, and plot one
    key of the returned dict/tuple in real time.

    If the callable returns a custom object with an ``extract`` method
    (like Quantum‑Machines' QUA result handles), the GUI tries a few
    common patterns to coerce the output into a dict.  If it can't
    figure it out, simply wrap your program so it *already* returns
    a mapping.
    """

    def __init__(self, program_dict: dict[str, Callable], timer_ms: int = 500):
        super().__init__()

        self.setWindowTitle("Live Experiment Runner")
        self.program_dict = program_dict
        self.current_program_name: str | None = None
        self.current_program: Callable | None = None
        self._last_keys: list[str] = []  # for the plot‑key combo

        self.timer = QtCore.QTimer(self, interval=timer_ms)
        self.timer.timeout.connect(self._acquire)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # ── Top bar: program selector ──────────────────────────────────
        top_bar = QtWidgets.QHBoxLayout()
        layout.addLayout(top_bar)
        top_bar.addWidget(QtWidgets.QLabel("Program:"))
        self.program_combo = QtWidgets.QComboBox()
        self.program_combo.addItems(self.program_dict.keys())
        self.program_combo.currentTextChanged.connect(self._program_changed)
        top_bar.addWidget(self.program_combo)
        top_bar.addStretch(1)

        # ── Parameter form (auto‑generated) ────────────────────────────
        self.param_scroll = QtWidgets.QScrollArea()
        self.param_container = QtWidgets.QWidget()
        self.param_form = QtWidgets.QFormLayout(self.param_container)
        self.param_scroll.setWidget(self.param_container)
        self.param_scroll.setWidgetResizable(True)
        layout.addWidget(self.param_scroll, stretch=0)

        # ── Plot area ──────────────────────────────────────────────────
        self.plot_widget = pg.PlotWidget()
        self.curve = self.plot_widget.plot(pen="y")
        layout.addWidget(self.plot_widget, stretch=1)

        # ── Bottom bar: plot key + start/stop ──────────────────────────
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

        # Build widgets for the first program
        self._program_changed(self.program_combo.currentText())

    # ---------------------------------------------------------------- Program switching
    def _program_changed(self, name: str):
        """Called when user picks a different program from the drop‑down."""
        if not name:
            return
        self.current_program_name = name
        self.current_program = self.program_dict[name]
        self.timer.stop()  # ensure we don't call the old one mid‑change

        # Clear old form rows
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.param_widgets: dict[str, QtWidgets.QWidget] = {}

        sig = inspect.signature(self.current_program)
        for p in sig.parameters.values():
            # Ignore *args, **kwargs → you could handle them if you like
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            widget = self._widget_for_param(p)
            self.param_form.addRow(p.name, widget)
            self.param_widgets[p.name] = widget

        # Reset key combo so it will repopulate after next run
        self.key_combo.clear()
        self._last_keys.clear()

    # ---------------------------------------------------------------- Widget factory
    def _widget_for_param(self, p: inspect.Parameter) -> QtWidgets.QWidget:
        """Return an appropriate editor widget for a parameter."""
        default = None if p.default is inspect._empty else p.default

        # → Bool
        if isinstance(default, bool):
            w = QtWidgets.QCheckBox()
            w.setChecked(default)
            return w

        # → Int / float heuristics
        if isinstance(default, numbers.Integral):
            w = QtWidgets.QSpinBox()
            w.setRange(-1_000_000_000, 1_000_000_000)
            w.setValue(default)
            return w
        if isinstance(default, numbers.Real):
            w = QtWidgets.QDoubleSpinBox()
            w.setDecimals(6)
            w.setRange(-1e12, 1e12)
            w.setSingleStep(max(abs(default) / 1000, 0.1))
            w.setValue(default)
            return w

        # → Fallback text field
        w = QtWidgets.QLineEdit(str(default or ""))
        return w

    # ---------------------------------------------------------------- Helpers
    def _current_params(self) -> dict[str, object]:
        """Pull current values from the param widgets → dict."""
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
                # best‑effort numeric conversion
                try:
                    params[name] = float(text) if "." in text else int(text)
                except ValueError:
                    params[name] = text
        return params

    # ---------------------------------------------------------------- Acquisition loop
    def _acquire(self):
        if self.current_program is None:
            return

        params = self._current_params()
        try:
            result = self.current_program(**params).output
        except Exception as exc:
            print(f"Program error: {exc}")
            return

        # ---- Normalise output → dict[str, np.ndarray] ----------------
        result = self._coerce_result(result)
        if result is None:
            return  # Unsupported output type already reported

        # ---- Populate / refresh the plot‑key combo -------------------
        if not self._last_keys or set(result.keys()) != set(self._last_keys):
            self.key_combo.blockSignals(True)
            self.key_combo.clear()
            for k in result.keys():
                self.key_combo.addItem(k)
            self.key_combo.blockSignals(False)
            self._last_keys = list(result.keys())

        ykey = self.key_combo.currentText() or next(iter(result.keys()))
        y = np.asarray(result[ykey])
        xkey = "frequencies" if "frequencies" in result else None
        x = np.asarray(result.get(xkey, np.arange(len(y))))
        if y.dtype.kind == "c":  # complex → magnitude
            y = np.abs(y)

        self.curve.setData(x, y)
        self.plot_widget.enableAutoRange()

    # ---------------------------------------------------------------- Result coercion
    def _coerce_result(self, result):
        """Convert *result* into a dict or return *None* on failure."""
        # 1) Already a mapping ------------------------------------------------
        if isinstance(result, dict):
            return result

        # 2) Tuple/list → synthetic keys ------------------------------------
        if isinstance(result, (tuple, list)):
            return {f"col_{i}": v for i, v in enumerate(result)}

        # 3) Objects with an extract() method --------------------------------
        if hasattr(result, "extract") and callable(result.extract):
            try:
                extracted = result.extract()  # hope it needs no args
            except TypeError:
                print("extract() requires arguments; wrap your program to return a dict instead.")
                return None

            # Common pattern 3a: returns dict directly
            if isinstance(extracted, dict):
                return extracted
            # Pattern 3b: returns (keys, values)
            if (
                isinstance(extracted, (tuple, list)) and len(extracted) == 2
                and isinstance(extracted[0], (list, tuple))
                and isinstance(extracted[1], (list, tuple))
            ):
                return dict(zip(extracted[0], extracted[1]))
            # Otherwise can't guess
            print("Don't know how to interpret result.extract() output; wrap your program.")
            return None

        print("Unsupported return type:", type(result))
        return None


# --------------------------------------------------------------------------- Runner helper

def _normalise_programs(programs: "dict[str, Callable] | Callable") -> dict[str, Callable]:
    """Allow the user to pass a single callable OR a dict."""
    if isinstance(programs, dict):
        return programs
    if callable(programs):
        name = getattr(programs, "__name__", "Program")
        return {name: programs}
    raise TypeError("programs must be a callable or a mapping of str→callable")


def run_gui(programs: "dict[str, Callable] | Callable", *, timer_ms: int = 500):
    programs = _normalise_programs(programs)
    app = QtWidgets.QApplication(sys.argv)
    gui = ProgramRunnerGUI(programs, timer_ms=timer_ms)
    gui.resize(1000, 600)
    gui.show()
    sys.exit(app.exec_())