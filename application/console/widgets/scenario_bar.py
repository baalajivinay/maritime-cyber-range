"""
Scenario Control Bar — multi-stage cyber campaign transport controls.

Provides Load Scenario / Play / Pause / Scrub Timeline / Reset for the
schema-driven campaigns in ``attacks/scenarios`` and shows the live stage,
narrative and rolling resilience score (TTD / max XTE / CPA margin).

Conforms to the Task 1 deliverable; the heavy lifting lives in the Qt-free
``attacks/scenario_runner.ScenarioRunner`` so it is independently testable.
"""
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal

from application.console.theme import (
    PANEL_BG, PANEL_BORDER, TEXT_WHITE, TEXT_MUTED,
    COLOR_BLUE, COLOR_GREEN, COLOR_RED, COLOR_AMBER,
)

from scenario_runner import list_scenarios, load_scenario, ScenarioRunner


class ScenarioControlBar(QFrame):
    # Emitted when the operator loads / plays / resets a campaign
    scenario_loaded = pyqtSignal(str)       # scenario id
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    seek_requested = pyqtSignal(float)      # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel")
        self.setFixedHeight(70)
        self._slider_grabbed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 6)
        root.setSpacing(4)

        # ---- Row 1: transport controls -------------------------------------
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Cyber Campaign")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {TEXT_WHITE};")
        row.addWidget(lbl)

        self.combo = QComboBox()
        self.combo.setFixedWidth(330)
        self._scenarios = list_scenarios()
        for meta in self._scenarios:
            self.combo.addItem(meta["name"], meta["id"])
        row.addWidget(self.combo)

        self.btn_load = QPushButton("Load Scenario")
        self.btn_load.clicked.connect(self._on_load)
        row.addWidget(self.btn_load)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setStyleSheet(
            f"QPushButton{{background-color:{COLOR_GREEN};color:#fff;font-weight:600;"
            f"border:none;border-radius:4px;padding:5px 12px;}}")
        self.btn_play.clicked.connect(self.play_requested.emit)
        self.btn_play.setEnabled(False)
        row.addWidget(self.btn_play)

        self.btn_pause = QPushButton("❚❚ Pause")
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_pause.setEnabled(False)
        row.addWidget(self.btn_pause)

        self.btn_reset = QPushButton("⟲ Reset")
        self.btn_reset.clicked.connect(self.reset_requested.emit)
        self.btn_reset.setEnabled(False)
        row.addWidget(self.btn_reset)

        row.addSpacing(8)
        self.lbl_clock = QLabel("00.0 / 00.0 s")
        self.lbl_clock.setStyleSheet(
            f"font-family: monospace; font-weight: bold; color: {TEXT_WHITE};")
        row.addWidget(self.lbl_clock)

        row.addStretch()

        self.lbl_score = QLabel("Resilience: —")
        self.lbl_score.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {TEXT_MUTED};")
        row.addWidget(self.lbl_score)

        root.addLayout(row)

        # ---- Row 2: scrub timeline + stage/metric readout ------------------
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_slider_grabbed", True))
        self.slider.sliderReleased.connect(self._on_slider_release)
        self.slider.setFixedWidth(360)
        row2.addWidget(self.slider)

        self.lbl_stage = QLabel("No campaign loaded")
        self.lbl_stage.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        row2.addWidget(self.lbl_stage, 1)

        self.lbl_metrics = QLabel("TTD: --  |  Max XTE: --  |  CPA: --")
        self.lbl_metrics.setStyleSheet(
            f"font-size: 11px; font-family: monospace; color: {TEXT_MUTED};")
        row2.addWidget(self.lbl_metrics)

        root.addLayout(row2)

    # ---------------------------------------------------------------- handlers
    def _on_load(self):
        sid = self.combo.currentData()
        if sid:
            self.scenario_loaded.emit(sid)

    def _on_slider_release(self):
        self._slider_grabbed = False
        frac = self.slider.value() / 1000.0
        self.seek_requested.emit(frac)  # fraction 0..1; app scales to duration

    def set_loaded(self, loaded: bool):
        self.btn_play.setEnabled(loaded)
        self.btn_pause.setEnabled(loaded)
        self.btn_reset.setEnabled(loaded)
        self.slider.setEnabled(loaded)

    # --------------------------------------------------------------- live view
    def update_view(self, status: dict, score: dict):
        """Refresh clock, scrub position, stage text and resilience readout."""
        elapsed = status.get("elapsed_s", 0.0)
        duration = status.get("duration_s", 0.0) or 1.0
        self.lbl_clock.setText(f"{elapsed:04.1f} / {duration:04.1f} s")

        if not self._slider_grabbed:
            self.slider.blockSignals(True)
            self.slider.setValue(int(1000 * status.get("progress", 0.0)))
            self.slider.blockSignals(False)

        state = status.get("state", "idle")
        sidx = status.get("stage_index")
        sname = status.get("stage_name", "")
        if sidx is None:
            stage_txt = f"[{state.upper()}] {sname}"
        else:
            stage_txt = f"[{state.upper()}] Stage {sidx}: {sname}"
        self.lbl_stage.setText(stage_txt)
        narrative = status.get("stage_narrative", "")
        if narrative:
            self.lbl_stage.setToolTip(narrative)

        # Metrics
        ttd = score.get("mean_ttd_s")
        xte = score.get("max_xte_m")
        cpa = score.get("min_cpa_m")
        ttd_s = f"{ttd:.1f}s" if ttd is not None else "--"
        xte_s = f"{xte:.1f}m" if xte is not None else "--"
        cpa_s = f"{cpa:.0f}m" if cpa is not None else "--"
        self.lbl_metrics.setText(f"TTD: {ttd_s}  |  Max XTE: {xte_s}  |  CPA: {cpa_s}")

        grade = score.get("grade", "—")
        band = grade.split(" ")[0] if grade else ""
        colour = {
            "A": COLOR_GREEN, "B": COLOR_GREEN, "C": COLOR_AMBER, "D": COLOR_RED,
        }.get(band, TEXT_MUTED)
        self.lbl_score.setText(f"Resilience: {grade}")
        self.lbl_score.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {colour};")
