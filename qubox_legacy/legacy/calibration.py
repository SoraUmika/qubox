from qm.quantum_machine import QuantumMachine
from qubox.optimization.smooth_opt import scipy_minimize
from qm.api.v2.job_api.job_api import JobApi
from time import sleep
import matplotlib.pyplot as plt
import numpy as np 
from qubox.analysis_tools import argmin_general
from tqdm import tqdm
from qm import qua
from configuration import *
from sadevice.SA124B import SA124B


SCAN_SAMPLE_NUM = 20
SA_BANDWIDTH = 5e3
SA_POINT_SPAN = 50e3
def dB_to_factor(dB_value):
    return 10**(dB_value/10)

def calibrate_IQ_dc_offset(qm_obj: QuantumMachine, element, target_LO, target_IF, sa_device: SA124B,
                           average_num=25,
                           optimizer=None,
                           optimizer_kwargs=None):
    """
    Calibrate I/Q DC offsets by:
      1) Coarse 2D scan over I/Q
      2) Fine optimization (defaults to Nelder-Mead, or user-supplied).

    Parameters
    ----------
    qm_obj : QuantumMachine
    element : str
    target_LO : float
    target_IF : float
    sa_device : SA124B
    average_num : int
        How many averages in the cost function measurement.
    optimizer : callable or None
        A function of signature:
          optimizer(cost_func, x0, bounds=..., **kwargs) -> result
        from which we can extract the final .x.
        If None, uses a default that calls scipy_minimize with Nelder-Mead.
    optimizer_kwargs : dict or None
        Additional keyword arguments to pass into `optimizer`.
    """
    # ------------------------------------------------------------------
    # Coarse scan
    # ------------------------------------------------------------------
    sa_device.set_config_center_span(target_LO, SA_POINT_SPAN)
    sample_num = SCAN_SAMPLE_NUM
    power_matrix = np.zeros((sample_num, sample_num))
    max_dc_offset = 0.1
    dc_offset_list = np.linspace(-max_dc_offset, max_dc_offset, sample_num)

    print("Performing IQ dc offset coarse sweep")
    for i, I_offset in tqdm(enumerate(dc_offset_list)):
        for j, Q_offset in enumerate(dc_offset_list):
            qm_obj.set_output_dc_offset_by_element(element, ('I', 'Q'), (I_offset, Q_offset))
            power = max(sa_device.sweep(plotting=False)["max"])
            power_matrix[i, j] = power

    plt.title("IQ offset scan for LO")
    plt.imshow(power_matrix,
               extent=[-max_dc_offset, max_dc_offset, -max_dc_offset, max_dc_offset],
               aspect='auto')
    plt.xlabel("Q offset")
    plt.ylabel("I offset")
    plt.colorbar()
    plt.show()

    # Argmin from the coarse scan
    min_indices = np.unravel_index(np.argmin(power_matrix), power_matrix.shape)
    coarse_opt_I = dc_offset_list[min_indices[0]]
    coarse_opt_Q = dc_offset_list[min_indices[1]]
    qm_obj.set_output_dc_offset_by_element(element, ('I', 'Q'), (coarse_opt_I, coarse_opt_Q))
    print(f"Coarse opt I, Q offset = {coarse_opt_I}, {coarse_opt_Q}")

    coarse_LO_power, coarse_rf_power = sa_device.discrete_points_sweep([target_LO, target_LO+target_IF])
    print(f"Coarse LO power, Coarse_rf_power, factor = {coarse_LO_power, coarse_rf_power} dBm, "
          f"{dB_to_factor(coarse_rf_power - coarse_LO_power)}\n")

    # ------------------------------------------------------------------
    # Fine optimization
    # ------------------------------------------------------------------
    # Cost function
    sa_device.set_config_center_span(target_LO, SA_POINT_SPAN)
    def lo_cost_function(IQ_dc_offsets):
        I_dc_offset, Q_dc_offset = IQ_dc_offsets
        qm_obj.set_output_dc_offset_by_element(element, ('I', 'Q'), (I_dc_offset, Q_dc_offset))
        # Measure the LO feedthrough level
        sleep(0.01)
        power = max(sa_device.sweep(plotting=False, average_num=average_num)["max"])
        print(I_dc_offset, Q_dc_offset, power)
        return power

    # If user did not supply an optimizer, define a default using scipy_minimize:
    if optimizer is None:
        from scipy.optimize import minimize as scipy_minimize

        def default_optimizer(fun, x0, bounds=None, **kwargs):
            return scipy_minimize(fun,
                                  x0=x0,
                                  bounds=bounds,
                                  method="Nelder-Mead",
                                  options={'maxiter': 25,
                                            "xatol": 1e-5,     # tolerance for parameter changes
                                            "fatol": 1e-3,     # tolerance for cost changes
                                            "disp": True,},
                                  **kwargs)
        optimizer = default_optimizer

    if optimizer_kwargs is None:
        optimizer_kwargs = {}

    # Set narrower bounds around the coarse optimum (± one step from the coarse grid)
    d_offset = abs(dc_offset_list[1] - dc_offset_list[0])
    print("differential offset:" ,d_offset)
    fine_bounds = [(coarse_opt_I - d_offset, coarse_opt_I + d_offset),
                   (coarse_opt_Q - d_offset, coarse_opt_Q + d_offset)]
    print("bounds", fine_bounds)
    print(f"Performing IQ dc offset fine sweep using custom optimizer: {optimizer}")
    result = optimizer(lo_cost_function,
                       x0=[coarse_opt_I, coarse_opt_Q],
                       bounds=fine_bounds,
                       **optimizer_kwargs)
    # We assume 'result' has an attribute '.x' with the solution:
    opt_I, opt_Q = result.x

    qm_obj.set_output_dc_offset_by_element(element, ('I', 'Q'), (opt_I, opt_Q))
    print(f"fine opt I, Q offset = {opt_I}, {opt_Q}")

    fine_LO_power, fine_rf_power = sa_device.discrete_points_sweep([target_LO, target_LO+target_IF])
    print(f"fine LO power, fine_rf_power, factor = = {fine_LO_power, fine_rf_power} dBm, "
          f"{dB_to_factor(fine_rf_power - fine_LO_power)} \n")

    return opt_I, opt_Q


def calibrate_gp_correction(job, element, target_LO, target_IF, sa_device,
                            average_num=50,
                            optimizer=None,
                            optimizer_kwargs=None):
    """
    Calibrate gain/phase correction by:
      1) Coarse 2D scan (grid of g, phi)
      2) Fine optimization (defaults to Nelder-Mead, or user-supplied).

    Parameters
    ----------
    job : JobApi
    element : str
    target_LO : float
    target_IF : float
    sa_device : SA124B
    average_num : int
        Averages in the cost function measurement.
    optimizer : callable or None
        A function (cost_func, x0, bounds=..., **kwargs) -> result
        returning a .x for the optimum.
    optimizer_kwargs : dict or None
        Additional arguments passed to the optimizer.
    """
    sa_device.set_config_center_span(target_LO - target_IF, SA_POINT_SPAN)
    sample_num = SCAN_SAMPLE_NUM

    gain = np.linspace(-0.2, 0.2, sample_num)
    phase = np.linspace(-0.3, 0.3, sample_num)

    image_power = np.zeros((sample_num, sample_num))
    print("Performing gp correction coarse sweep")
    for i, g_val in tqdm(enumerate(gain)):
        for j, p_val in enumerate(phase):
            correction_matrix = IQ_imbalance(g_val, p_val)
            job.set_element_correction(element, correction_matrix)
            # Wait to settle:
            sleep(0.01)
            result = sa_device.sweep(plotting=False, average_num=10)
            image_power[i, j] = max(result["max"])

    plt.title("gain, phase correction scan for LO+IF power")
    plt.xlabel("phase")
    plt.ylabel("gain")
    # Note that imshow expects: extent=[left, right, bottom, top]
    plt.imshow(image_power,
               aspect='auto',
               extent=[phase[0], phase[-1], gain[-1], gain[0]])
    plt.colorbar()
    plt.show()

    # Argmin from the coarse scan
    min_indices = np.unravel_index(np.argmin(image_power), image_power.shape)
    coarse_opt_g = gain[min_indices[0]]
    coarse_opt_p = phase[min_indices[1]]
    job.set_element_correction(element, IQ_imbalance(coarse_opt_g, coarse_opt_p))
    print(f"Coarse opt g, p correction = {coarse_opt_g}, {coarse_opt_p}")

    coarse_image_power, coarse_rf_power = sa_device.discrete_points_sweep([target_LO - target_IF, target_LO + target_IF])
    print(f"coarse image power, coarse_rf_power, factor = {coarse_image_power, coarse_rf_power} dBm, "
          f"{dB_to_factor(coarse_rf_power - coarse_image_power)}\n")

    # ------------------
    # Fine optimization
    # ------------------
    sa_device.set_config_center_span(target_LO - target_IF, SA_POINT_SPAN)
    def sideband_cost_function(g_phi):
        g, phi = g_phi
        correction_matrix = IQ_imbalance(g, phi)
        job.set_element_correction(element, correction_matrix)
        power = max(sa_device.sweep(plotting=False, average_num=average_num)["max"])
        print(g,phi, power)
        return power

    # Default optimizer is again Nelder-Mead via scipy
    if optimizer is None:
        from scipy.optimize import minimize as scipy_minimize
        def default_optimizer(fun, x0, bounds=None, **kwargs):
            return scipy_minimize(fun,
                                  x0=x0,
                                  bounds=bounds,
                                  method="Nelder-Mead",
                                  options={'maxiter': 25,
                                            "xatol": 1e-5,     # tolerance for parameter changes
                                            "fatol": 1e-3,     # tolerance for cost changes
                                            "disp": True,},
                                  **kwargs)
        optimizer = default_optimizer

    if optimizer_kwargs is None:
        optimizer_kwargs = {}

    dg = abs(gain[1] - gain[0])
    dp = abs(phase[1] - phase[0])
    fine_bounds = [(coarse_opt_g - dg, coarse_opt_g + dg),
                   (coarse_opt_p - dp, coarse_opt_p + dp)]

    print("Performing gp correction fine sweep with custom optimizer:", optimizer)
    result = optimizer(sideband_cost_function,
                       x0=[coarse_opt_g, coarse_opt_p],
                       bounds=fine_bounds,
                       **optimizer_kwargs)

    opt_g, opt_p = result.x
    print(f"fine opt g, p correction = {opt_g}, {opt_p}")
    job.set_element_correction(element, IQ_imbalance(opt_g, opt_p))

    fine_image_power, fine_rf_power = sa_device.discrete_points_sweep([target_LO - target_IF, target_LO + target_IF])
    print(f"fine image power, fine rf power, factor = {fine_image_power, fine_rf_power} dBm, "
          f"{dB_to_factor(fine_rf_power - fine_image_power)}\n")

    return opt_g, opt_p


def calibrate_element_output(qm_obj: QuantumMachine, element, target_LO, target_IF, target_gain,
                             sa_device: SA124B, sc_device,
                             dc_optimizer=None,
                             dc_optimizer_kwargs=None,
                             gp_optimizer=None,
                             gp_optimizer_kwargs=None,
                             halt_job_when_done = True
                             ):
    """
    Wrapper to run both calibrations.
    - 'dc_optimizer' is the method used for calibrate_IQ_dc_offset
    - 'gp_optimizer' is the method used for calibrate_gp_correction
    """
    

    #sc_device.update_frequency(target_LO)

    with qua.program() as continous_wave:
        qua.update_frequency(element, target_IF)
        with qua.infinite_loop_():
            qua.play("const" * qua.amp(target_gain), element)
    job = qm_obj.execute(continous_wave)

    print("Performing manual calibration for DC offsets (I/Q).")
    opt_I, opt_Q = calibrate_IQ_dc_offset(qm_obj, element, target_LO, target_IF, sa_device,
                                          optimizer=dc_optimizer,
                                          optimizer_kwargs=dc_optimizer_kwargs)

    print("Now calibrating gain/phase correction.")
    opt_g, opt_p = calibrate_gp_correction(job, element, target_LO, target_IF, sa_device,
                                           optimizer=gp_optimizer,
                                           optimizer_kwargs=gp_optimizer_kwargs)

    target_IF_pow, LO_pow, image_IF_pow = sa_device.discrete_points_sweep([target_LO+target_IF,
                                                                           target_LO,
                                                                           target_LO-target_IF])
    print(f"Final power (dBm):")
    print(f"target IF: {target_IF_pow}")
    print(f"LO:        {LO_pow}, opt_I={opt_I}, opt_Q={opt_Q}")
    print(f"image IF:  {image_IF_pow}, opt_g={opt_g}, opt_p={opt_p}")

    sa_device.set_config_center_span(target_LO, int(2.1*abs(target_IF)))
    sa_device.sweep(plotting=True)
    
    if halt_job_when_done:
        job.halt()
    return (opt_I, opt_Q, opt_g, opt_p)

if __name__ == "main":
    
    pass



#calibrate_element_output(experiment.qm, "resonator", SYNTH_1, -50e6, 0.1, sa_device, sc_device)


#calibrate_element_output(experiment.qm, "resonator", 4e9, -50e6, 0.1, sa_device)