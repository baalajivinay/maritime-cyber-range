"""Scale-up: mission scenario engine (additive, default-off).

Composes the project's existing attacks into timed missions and grades them by
OPERATIONAL consequence (divergence / no-go breach / grounding / CPA), then maps
findings to IACS UR E26/E27 & IMO MSC.428(98). Nothing in the shipped package
imports this; it runs only via tools/run_scenario.py.
"""
from .model import load_scenario, Scenario, TimelineStep, Hazard, Contact, Consequence
from .engine import run_scenario, ScenarioResult
from .executors import Executor, SimExecutor, LiveExecutor
from . import consequences, geo, report, report_html, standards

__all__ = [
    "load_scenario", "Scenario", "TimelineStep", "Hazard", "Contact", "Consequence",
    "run_scenario", "ScenarioResult",
    "Executor", "SimExecutor", "LiveExecutor",
    "consequences", "geo", "report", "standards",
]
