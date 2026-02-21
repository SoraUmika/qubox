"""Generate qubox_v2 usage notebook."""
import json

def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}

def code(source):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(True)}

cells = []

# ── Title ──
cells.append(md("""\
# qubox_v2 v3 — Spectroscopy & Basic Qubit Characterization

This notebook demonstrates the **qubox_v2 v3** modular experiment API for basic
superconducting qubit characterization on the QM OPX+ platform.

**Experiments covered:**
1. Resonator spectroscopy (`ResonatorSpectroscopy`)
2. Qubit spectroscopy (`QubitSpectroscopy`)
3. Power Rabi — pi pulse calibration
4. IQ blob — readout discrimination
5. T1 relaxation
6. T2 Ramsey

**Device:** `seq_1_device` | **Resonator:** ~8.596 GHz | **Qubit:** ~6.150 GHz | **Storage:** ~5.241 GHz
"""))

# ── Imports ──
cells.append(code("""\
import sys
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, r"E:\\qubox")

from qualang_tools.units import unit

# --- qubox_v2 v3 imports ---
from qubox_v2.experiments.legacy_experiment import cQED_Experiment
from qubox_v2.experiments import (
    ResonatorSpectroscopy,
    ResonatorPowerSpectroscopy,
    QubitSpectroscopy,
    PowerRabi,
    IQBlob,
    T1Relaxation,
    T2Ramsey,
)
from qubox_v2.analysis import fitting, cQED_models, cQED_plottings
from qubox_v2.analysis import algorithms
from qubox_v2.analysis.analysis_tools import two_state_discriminator
from qubox_v2.programs.macros.measure import measureMacro

u = unit()
"""))

# ── Section 1: Initialization ──
cells.append(md("""\
## 1. Initialization

Connect to the OPX+ and load device configuration. The `cQED_Experiment` context
wires up hardware, pulse management, and calibration. Modular experiment classes
accept it as their execution context.

> **v3 alternative:** Use `SessionManager` from `qubox_v2.experiments.session` for
> a lighter initialization. Both styles work with the experiment classes.
"""))

cells.append(code("""\
experiment_path = r"E:\\qubox\\seq_1_device"

experiment = cQED_Experiment(
    experiment_path,
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
    oct_cal_path="./",
    override_octave_json_mode="on",
    output_mode="on",
)

# Load readout discrimination / measurement configuration
experiment.load_measureMacro_state()

# Convenience aliases
pom  = experiment.pulseOpMngr
attr = experiment.attributes

print(f"Resonator: {attr.ro_fq / 1e9:.4f} GHz")
print(f"Qubit:     {attr.qb_fq / 1e9:.4f} GHz")
print(f"Storage:   {attr.st_fq / 1e9:.4f} GHz")

# Uncomment to run in simulation mode (no hardware required):
# experiment.quaProgMngr.set_exec_mode("simulate")
"""))

# ── Section 2: Resonator Spectroscopy ──
cells.append(md("""\
## 2. Resonator Spectroscopy

Sweep the readout frequency to find the resonator resonance. Uses the v3
`ResonatorSpectroscopy` modular class.

**Workflow:**
1. (Optional) Create a custom readout pulse with desired length/amplitude
2. Run the frequency sweep
3. Fit a Lorentzian to extract the resonance frequency
"""))

cells.append(code("""\
# --- (Optional) Define a custom readout pulse ---
# The default "readout" operation from pulses.json works for most cases.
# Uncomment below to create a custom one:

# readout_op = "readout_test"
# pom.create_measurement_pulse(
#     element=attr.ro_el,
#     op=readout_op,
#     length=1000,
#     pulse_name=f"{readout_op}_pulse",
#     I_samples=0.005,
#     digital_marker="ON",
#     int_weights_mapping=None,
#     int_weights_defs=None,
#     persist=False,
#     override=True,
# )
# experiment.burn_pulses()

# Use the existing readout operation
readout_op = "readout"
"""))

cells.append(code("""\
# --- Run resonator spectroscopy (v3 modular class) ---
n_avg      = 10000
freq_start = 8560 * u.MHz
freq_end   = 8640 * u.MHz
df         = 200 * u.kHz

spec = ResonatorSpectroscopy(experiment)
result = spec.run(readout_op, rf_begin=freq_start, rf_end=freq_end, df=df, n_avg=n_avg)

if result.mode == "simulate":
    print("Simulation run, no data to analyze.")
else:
    frequencies, magnitude = result.output.extract("frequencies", "magnitude")
    f_mhz = frequencies * 1e-6

    # --- Fit Lorentzian ---
    p0 = [np.mean(f_mhz), 1, -1e-4, 0]
    fit_result = fitting.generalized_fit(
        f_mhz, magnitude,
        cQED_models.resonator_spec_model,
        p0,
        plotting=True,
        plot_options={
            "figsize": (10, 6),
            "xlabel": "Frequency (MHz)",
            "ylabel": "R",
            "title": "Resonator Spectroscopy",
            "legend_fontsize": 14,
        },
        param_format="{:.4f}",
    )
    f0_MHz = fit_result[0][0]
    kappa_MHz = abs(fit_result[0][1])
    print(f"Resonator frequency: {f0_MHz:.4f} MHz")
    print(f"Linewidth (kappa):   {kappa_MHz:.4f} MHz")
"""))

cells.append(code("""\
# --- Update resonator frequency in attributes ---
# Uncomment after verifying the fit:
# attr.ro_fq = fit_result[0][0] * 1e6  # Hz
# experiment.save_attributes()
# measureMacro.set_drive_frequency(attr.ro_fq)
# print(f"Updated ro_fq = {attr.ro_fq / 1e9:.6f} GHz")
"""))

# ── Section 3: Qubit Spectroscopy ──
cells.append(md("""\
## 3. Qubit Spectroscopy

Drive the qubit element at varying frequencies while monitoring readout to find
the qubit transition. Uses the v3 `QubitSpectroscopy` modular class.
"""))

cells.append(code("""\
# --- Run qubit spectroscopy (v3 modular class) ---
n_avg      = 10000
freq_start = 6130 * u.MHz
freq_end   = 6170 * u.MHz
df         = 500 * u.kHz
qb_gain    = 1.0
qb_len     = None   # use default pulse length
pulse      = "x180"

qb_spec = QubitSpectroscopy(experiment)
result = qb_spec.run(
    pulse, rf_begin=freq_start, rf_end=freq_end, df=df,
    qb_gain=qb_gain, qb_len=qb_len, n_avg=n_avg,
)

if result.mode == "simulate":
    print("Simulation run, no data to analyze.")
else:
    freqs, S, phases = result.output.extract("frequencies", "S", "Phases")
    f_mhz = np.asarray(freqs) * 1e-6

    # --- Dual-axis plot: magnitude + phase ---
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(f_mhz, np.abs(S), label="|S|", linewidth=1.5)
    ax1.set_xlabel("Frequency (MHz)")
    ax1.set_ylabel("Amplitude (arb.)")

    ax2 = ax1.twinx()
    ax2.plot(f_mhz, np.asarray(phases), label="Phase", linestyle="--", color="tab:orange")
    ax2.set_ylabel("Phase (rad)")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="best")
    plt.title(f"Qubit Spectroscopy | qb_gain={qb_gain}")
    fig.tight_layout()
    plt.show()

    # --- Peak detection on phase dip ---
    peak_results = algorithms.find_peaks(f_mhz, -np.asarray(phases), 3, min_distance=5)
    print("Detected peaks (MHz):", peak_results)
"""))

cells.append(code("""\
# --- Update qubit frequency ---
# Uncomment after identifying the correct peak:
# attr.qb_fq = <peak_freq_Hz>
# experiment.save_attributes()
# print(f"Updated qb_fq = {attr.qb_fq / 1e9:.6f} GHz")
"""))

# ── Section 4: Power Rabi ──
cells.append(md("""\
## 4. Power Rabi

Sweep qubit drive amplitude to calibrate the pi pulse. The oscillation period
gives the gain corresponding to a pi rotation.
"""))

cells.append(code("""\
# --- Power Rabi (legacy method) ---
max_gain = 1.2
dg       = 0.04
n_avg    = 5000

rr = experiment.power_rabi(max_gain, dg, op="x180", n_avg=n_avg)

if rr.mode == "simulate":
    print("Simulation run, skipping fit.")
else:
    gains, S = rr.output.extract("gains", "S")

    # --- Fit sinusoidal model ---
    C0, V0, eta, phi = -1, max(S.real) - min(S.real), np.pi, 0
    p0 = (C0, V0, eta, phi)
    fit_params = fitting.generalized_fit(
        gains, S.real,
        cQED_models.sinusoid_pe_model,
        p0,
        plotting=True,
        plot_options={
            "figsize": (12, 5),
            "xlabel": "Qubit amplitude",
            "ylabel": "Signal (arb.)",
            "title": "Power Rabi",
            "legend_fontsize": 14,
        },
        param_format="{:.4f}",
    )

    C, V, eta, phi = fit_params[0]
    a_pi   = (np.pi - phi) / eta
    a_pi_2 = (np.pi / 2 - phi) / eta
    print(f"Pi pulse amplitude:   {a_pi:.4f}")
    print(f"Pi/2 pulse amplitude: {a_pi_2:.4f}")
"""))

# ── Section 5: IQ Blob ──
cells.append(md("""\
## 5. IQ Blob / Readout Discrimination

Acquire IQ data for ground (`|g>`) and excited (`|e>`) states, then run the
two-state discriminator to extract readout fidelity.
"""))

cells.append(code("""\
# --- IQ blob measurement ---
n_runs = 50000

rr = experiment.iq_blob("x180", n_runs=n_runs)

if rr.mode == "simulate":
    print("Simulation run, skipping discriminator.")
else:
    S_g, S_e = rr.output.extract("S_g", "S_e")
    out = two_state_discriminator(S_g, S_e, b_plot=True)
    print(f"Readout fidelity: {out[2]:.2%}")
"""))

# ── Section 6: T1 ──
cells.append(md("""\
## 6. T1 Relaxation

After a pi pulse, sweep the wait time and fit an exponential decay to extract T1.
"""))

cells.append(code("""\
# --- T1 relaxation ---
delay_end = 40 * u.us
dt        = 200   # ns
n_avg     = 2000

rr = experiment.T1_relaxation(delay_end, dt, n_avg=n_avg)

if rr.mode == "simulate":
    print("Simulation run, skipping T1 fit.")
else:
    delays, S = rr.output.extract("delays", "S")

    fit_result = fitting.generalized_fit(
        delays * 1e-3,   # ns -> us
        S.real,
        cQED_models.T1_relaxation_model,
        [0, 10, 0],
        plotting=True,
        plot_options={
            "figsize": (10, 6),
            "xlabel": r"Delay ($\\mu$s)",
            "ylabel": "Signal (arb.)",
            "title": "T1 Relaxation",
            "legend_fontsize": 14,
        },
        param_format="{:.4f}",
    )
    A, T1_us, offset = fit_result[0]
    print(f"T1 = {T1_us:.2f} us")

    # Uncomment to save:
    # attr.qb_T1_relax = T1_us * 1e3  # store in ns
    # experiment.save_attributes()
"""))

# ── Section 7: T2 Ramsey ──
cells.append(md("""\
## 7. T2 Ramsey

Two pi/2 pulses separated by a variable delay, with an intentional detuning.
The oscillation envelope gives T2*.
"""))

cells.append(code("""\
# --- T2 Ramsey ---
qb_detune = 0.2 * u.MHz
delay_end = 40 * u.us
dt        = 100   # ns
n_avg     = 4000

rr = experiment.T2_ramsey(qb_detune, delay_end, dt, r90="x90", n_avg=n_avg)

if rr.mode == "simulate":
    print("Simulation run, skipping T2 Ramsey fit.")
else:
    delays, S = rr.output.extract("delays", "S")
    delays_us = delays * 1e-3  # ns -> us

    fit_p0 = [0, 20, 1, qb_detune * 1e-6, 0, 0]
    fit_result = fitting.generalized_fit(
        delays_us, S.real,
        cQED_models.T2_ramsey_model,
        fit_p0,
        plotting=True,
        plot_options={
            "figsize": (12, 6),
            "xlabel": r"Delay ($\\mu$s)",
            "ylabel": "Signal (arb.)",
            "title": "T2 Ramsey",
            "legend_fontsize": 14,
        },
        param_format="{:.6f}",
    )
    A, T2_us, n, fitted_det_MHz, phi, offset = fit_result[0]
    print(f"T2* = {T2_us:.2f} us")
    print(f"Fitted detuning = {fitted_det_MHz:.6f} MHz")

    # Uncomment to correct qubit frequency and save:
    # freq_correction = qb_detune - fitted_det_MHz * 1e6
    # attr.qb_fq += freq_correction
    # attr.qb_T2_ramsey = int(T2_us * u.us)
    # experiment.save_attributes()
"""))

# ── Build notebook ──
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11.0",
        },
    },
    "cells": cells,
}

out_path = r"E:\qubox\notebooks\qubox_v2_usage.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Notebook written to {out_path}")
print(f"Total cells: {len(cells)}")
