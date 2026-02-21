import numpy as np

import matplotlib.pyplot as plt

from scipy.special import factorial

###############################################################################

# Circuit QED Model Functions with Equation Strings

###############################################################################



def resonator_spec_model(freq, f0, kappa, A, offset):

    """

    Expected resonator power spectroscopy response.



    Here the frequency response of the resonator is modeled as a Lorentzian.

    Depending on your measurement you may see a dip (if A is negative) or a peak.

    

    Parameters:

        freq   : array-like

                 Probe frequency (Hz).

        f0     : float

                 Resonator center frequency.

        kappa  : float

                 Full-width at half-maximum (FWHM) linewidth.

        A      : float

                 Amplitude (depth of dip or height of peak).

        offset : float

                 Baseline offset.

                 

    Returns:

        Response value at frequency "freq".

    """

    return offset + A / (1 + (2 * (freq - f0) / kappa) ** 2)



resonator_spec_model.equation = r'$y = offset + \frac{A}{1 + \left(\frac{2\,(freq - f_0)}{\kappa}\right)^2}$'



def resonator_spec_phase_model(freq, f0, kappa, A, offset, slope):

    """

    Expected resonator phase spectroscopy response with linear background.



    The phase response is modeled using an arctan function combined with a linear term.

    The arctan function captures the rapid phase change near the resonator's center frequency,

    while the linear term accounts for systematic phase drift (e.g., due to cable delays).



    Parameters:

        freq   : array-like

                 Probe frequency (Hz).

        f0     : float

                 Resonator center frequency (Hz).

        kappa  : float

                 Full-width at half-maximum (FWHM) linewidth (Hz).

        A      : float

                 Phase scaling factor (determines total phase change from the arctan).

        offset : float

                 Baseline phase offset (radians or degrees, depending on your system).

        slope  : float

                 Linear phase drift (radians/Hz or degrees/Hz).



    Returns:

        Phase value at frequency "freq".

    """

    return offset + slope * (freq - f0) + A * np.arctan(2 * (freq - f0) / kappa)



# Equation string for documentation or plotting labels

resonator_spec_phase_model.equation = r'$\phi(f) = offset + slope\,(f - f_0) + A\,\arctan\!\left[\frac{2\,(f - f_0)}{\kappa}\right]$'





def qubit_spec_model(freq, f0, gamma, A, offset):

    """

    Expected qubit spectroscopy response.



    The qubit response is often modeled by a Lorentzian lineshape. Depending on

    your measurement, a dip or a peak may be observed.

    

    Parameters:

        freq   : array-like

                 Probe frequency (Hz).

        f0     : float

                 Qubit resonance frequency.

        gamma  : float

                 Characteristic linewidth (e.g. half width at half maximum).

        A      : float

                 Amplitude (can be positive or negative depending on readout).

        offset : float

                 Baseline offset.

                 

    Returns:

        Model value at frequency "freq".

    """

    return offset + A / (1 + ((freq - f0) / gamma) ** 2)



qubit_spec_model.equation = r'$y = offset + \frac{A}{1 + \left(\frac{(freq - f_0)}{\gamma}\right)^2}$'



def temporal_rabi_model(t, A, f_Rabi, T_decay, phi, offset):

    """

    Expected temporal Rabi oscillations.



    When you sweep the pulse length, the excited state population typically oscillates

    at the Rabi frequency while decaying due to decoherence. Here the model is a decaying cosine.

    

    Parameters:

        t       : array-like

                  Pulse length (time). (Units should match those for T_decay.)

        A       : float

                  Oscillation amplitude.

        f_Rabi  : float

                  Rabi frequency (Hz).

        T_decay : float

                  Decay time constant.

        phi     : float

                  Phase offset.

        offset  : float

                  Baseline offset.

                  

    Returns:

        Model value at time "t".

    """

    return offset + A * np.exp(-t / T_decay) * np.cos(2 * np.pi * f_Rabi * t + phi)



temporal_rabi_model.equation = r'$y = offset + A\,e^{-t/T_{decay}}\cos(2\pi\,f_{Rabi}\,t+\phi)$'



def power_rabi_model(g, A, g_pi, offset):

    """

    Expected power Rabi oscillations.



    In a power Rabi experiment the drive amplitude is varied. The excited state population

    oscillates as sinÂ²(Î¸/2) where the rotation angle Î¸ is (to first order) linear in the pulse gain.

    

    Parameters:

        g      : array-like

                 Drive amplitude (pulse gain).

        A      : float

                 Amplitude of the oscillation.

        g_pi   : float

                 Gain corresponding to a pi pulse.

        offset : float

                 Baseline level.

                 

    Returns:

        Model value at drive amplitude "g".

    """

    return offset + A * np.sin((np.pi / 2) * (g / g_pi)) ** 2



power_rabi_model.equation = r'$y = offset + A\,\sin^2\!\left(\frac{\pi}{2}\frac{g}{g_{\pi}}\right)$'



def power_rabi_model_shifted(g, A, g_pi, g0, offset):

    """

    Slightly more general:

        y = offset + A * sin^2( (pi/2) * ((g - g0) / g_pi) )

    This captures small dead-zone/offsets so g_{pi/2} != g_pi/2.

    """

    return offset + A * np.sin((np.pi / 2) * ((g - g0) / g_pi)) ** 2



power_rabi_model_shifted.equation = r'$y = offset + A\,\sin^2\!\left(\frac{\pi}{2}\frac{g - g_{0}}{g_{\pi}}\right)$'



def sinusoid_pe_model(a, C, V, eta, phi):

    """

    P_e(a) = C + V * sin^2( (eta * a + phi) / 2 )



    Params (to be fit):

      C   : baseline (0..1-ish)

      V   : visibility/amplitude (>=0)

      eta : angle-per-gain scaling [rad / gain]

      phi : phase offset [rad]

    """

    return C + V * np.sin(0.5 * (eta * a + phi))**2



# Pretty string for plots/legends

sinusoid_pe_model.equation = r"$P_e(a)=C+V\,\sin^2\!\left(\frac{\eta a+\phi}{2}\right)$"



def T1_relaxation_model(t, A, T1, offset):

    """

    Expected T1 relaxation (energy decay) response.



    After an excitation the qubit relaxes exponentially toward its ground state.

    

    Parameters:

        t      : array-like

                 Delay time.

        A      : float

                 Amplitude (difference between initial and final population).

        T1     : float

                 Relaxation time constant.

        offset : float

                 Asymptotic baseline (typically the ground state population).

                 

    Returns:

        Model value at delay time "t".

    """

    return offset + A * np.exp(-t / T1)



T1_relaxation_model.equation = r'$y = offset + A\,e^{-t/T_1}$'



def T2_ramsey_model(t, A, T2, n, f_det, phi, offset):

    """

    Expected T2 Ramsey oscillations.



    In a Ramsey experiment the qubit is prepared with a pi/2 pulse, left to evolve for time t,

    and then another pi/2 pulse is applied. The resulting signal is a decaying cosine at the detuning frequency.

    

    Parameters:

        t      : array-like

                 Delay time between pulses.

        A      : float

                 Amplitude of the oscillation.

        T2     : float

                 Dephasing (Ramsey) time.

        f_det  : float

                 Detuning frequency

        n      : float

                 characterstic decay factor

        phi    : float

                 Phase offset.

        offset : float

                 Baseline offset.

                 

    Returns:

        Model value at delay time "t".

    """

    T2 = np.abs(T2) + 1e-15          # prevent T2<=0

    x  = np.abs(t / T2)              # prevent negative base in power

    return offset + A * np.exp(-(x**n)) * np.cos(2 * np.pi * f_det * t + phi)



T2_ramsey_model.equation = r'$y = offset + A\,e^{-(t/T_2)^n}\cos(2\pi\,f_{det}\,t+\phi)$'



def T2_echo_model(t, A, T2_echo, n,offset):

    """

    Expected T2 echo decay.



    A Hahn echo experiment suppresses some dephasing and the measured signal decays

    (often exponentially) with a characteristic time T2_echo.

    

    Parameters:

        t       : array-like

                  Total echo delay time.

        A       : float

                  Amplitude.

        T2_echo : float

                  Echo coherence time.

        n      : float

                 characterstic decay factor

        offset  : float

                  Baseline level.

                  

    Returns:

        Model value at delay time "t".

    """

    return offset + A * np.exp(-(t / T2_echo)**n)



T2_echo_model.equation = r'$y = offset + A\,e^{-(t/T_{2,echo})^n}$'



def num_splitting_model(x, *params):

    """

    Models N Lorentzian peaks.



    Expects that params is a flattened list in the following order:

        [center_1, center_2, ..., center_N,

         amplitude_1, amplitude_2, ..., amplitude_N,

         fwhm, offset]

    

    Each Lorentzian peak is described by:

    

        y_i(x) = A_i / (1 + (2*(x - center_i) / fwhm)^2)

    

    and the full model is the sum of all peaks plus a baseline offset:

    

        y(x) = offset + sum_{i=1}^{N} y_i(x)

    

    Parameters:

        x      : array-like

                 Independent variable (e.g., frequency).

        *params: flattened parameters as described above.



    Returns:

        y : array-like

            The model evaluated at each value in x.

    """

    # Determine the number of peaks.

    # Total params = 2*N + 2, so:

    N = (len(params) - 2) // 2



    # Unpack parameters

    centers = params[:N]

    amplitudes = params[N:2*N]

    fwhm = params[-2]

    offset = params[-1]



    y = np.zeros_like(x, dtype=float)

    for center, A in zip(centers, amplitudes):

        y += A / (1 + (2 * (x - center) / fwhm) ** 2)

    return offset + y



num_splitting_model.equation = r'$y = offset + \sum_{i=1}^{N} \frac{A_i}{1+\left(\frac{2(x - x_{0,i})}{fwhm}\right)^2}$'



def chi_ramsey_model(t, P0, A, T2_eff, nbar, chi, t0):

    """

    Collapse-and-revival signal of a coherent state in the dispersive frame.



    Model (all inputs in *seconds* and *rad sâ»Â¹*)::



        P_e(t) = P0 + A Â· exp(-t / T2_eff)

                       Â· exp[ -2 n_bar Â· sinÂ²(chi (t + t0) / 2) ]



    Parameters

    ----------

    t        : array-like

        Evolution time (seconds).

    P0       : float

        Baseline probability.

    A        : float

        Modulation amplitude (0â€“1).

    T2_eff   : float

        Effective dephasing time constant (seconds).

    nbar     : float

        Mean photon number |alpha|Â².

    chi      : float

        Dispersive shift chi **in Hz**

    t0       : float

        Static time offset (seconds).



    Returns

    -------

    y : array-like

        Model evaluated at each t.

    """

    envelope = np.exp(-t / T2_eff)

    phase    = np.exp(-2 * nbar * np.sin(0.5 * 2 * np.pi *chi * (t + t0))**2)

    return P0 + A * envelope * phase





chi_ramsey_model.equation = (

    r'$P_e(t) = P_0 + A \exp(-t/T_{2,\mathrm{eff}})\,\exp(-2\,\bar{n}\,\sin^2(\pi\,\chi\,(t + t_0)))$'

)





def kerr_ramsey_model(t,            # time array   [s]

                      omega_c,      # cavity freq  [rad/s]

                      K,            # Kerr         [rad/s]

                      alpha,        # coherent amp (complex or real)

                      T2,           # Ramsey-envelope time constant [s]

                      A,            # overall amplitude scale

                      offset,       # baseline

                      n_max=None):  # Fock cutoff (optional)

    """

    Ramsey signal of a coherent state in a Kerr cavity, including

    a simple exponential dephasing envelope.



    Model:

        f(t) = offset + A * exp(-t/T2) *

               | âŸ¨alpha| exp[ i omega_c t aâ€ a + i K t/2 (aâ€ )^2 a^2 ] |alphaâŸ© |^2



    Parameters

    ----------

    t        : array-like

        Evolution time(s) [seconds].

    omega_c  : float

        Cavity resonance frequency omega_c [rad/s].

    K        : float

        Self-Kerr strength K [rad/s per photonÂ²].

    alpha    : complex

        Initial coherent-state amplitude alpha.

    T2       : float

        Ramsey dephasing time constant.

    A        : float

        Overall signal amplitude.

    offset   : float

        Baseline level.

    n_max    : int, optional

        Fock-space cutoff.  If None, picks a value â‰ˆ |alpha|Â² + 5âˆš|alpha|.



    Returns

    -------

    f : ndarray

        Model evaluated at each t.

    """

    t = np.atleast_1d(t).astype(float)



    # --- choose a safe Fock cutoff -----------------------------------------

    n_mean = np.abs(alpha)**2

    if n_max is None:

        n_max = int(np.ceil(n_mean + 5 * np.sqrt(max(n_mean, 1e-3))))



    n = np.arange(n_max + 1)



    # Poisson weights  P_n = e^{-|alpha|Â²} |alpha|^{2n} / n!

    Pn = np.exp(-n_mean) * (n_mean**n) / factorial(n)



    # Phase for each n:  phi_n(t) = tÂ·[ omega_c n + (K/2) n(n-1) ]

    phi = omega_c * n + 0.5 * K * n * (n - 1)          # shape (n,)

    Et  = np.sum(Pn * np.exp(1j * np.outer(t, phi)), axis=1)



    # Ramsey overlap magnitude squared

    overlap = np.abs(Et)**2                            # shape (t,)



    # Add exponential decay envelope, amplitude, and offset

    return offset + A * np.exp(-t / T2) * overlap





# pretty LaTeX string for documentation / plotting

kerr_ramsey_model.equation = (

    r'$y(t)=\mathrm{offset}+A\,e^{-t/T_2}\,'

    r'\Bigl|\langle\alpha|\exp\!\bigl[i\,t(\omega_c\,a^\dagger a'

    r'+\tfrac{K}{2}(a^\dagger)^2 a^2)\bigr]|\alpha\rangle\Bigr|^{2}$'

)


def kerr_ramsey_model_(t, Delta, K, alpha, T2=1e9, A=1.0, offset=0.0, n_max=None):
    """
    Overlap |<alpha|exp(i Delta t n + i K t n(n-1)/2)|alpha>|^2  (Delta = small detuning).
    """
    t = np.atleast_1d(t)
    n_bar = abs(alpha)**2
    if n_max is None:
        n_max = int(np.ceil(n_bar + 5*np.sqrt(max(n_bar, 1e-3))))
    n = np.arange(n_max+1)
    Pn = np.exp(-n_bar)*(n_bar**n)/factorial(n)

    phi = Delta*n + 0.5*K*n*(n-1)                   # rad/s
    Et = np.sum(Pn*np.exp(1j*np.outer(t, phi)), axis=1)
    return offset + A*np.exp(-t/T2)*abs(Et)**2


def number_split_frequency_model(n, base_fq, chi, chi2, chi3):

    n = np.asarray(n, dtype=float)

    return (

        base_fq

        + chi * n

        + chi2 * n * (n - 1)

        + chi3 * n * (n - 1) * (n - 2)

    )



number_split_frequency_model.equation = r'$f(n) = f_{q,0} + \chi\,n + \chi_2\,n(n-1) + \chi_3\,n(n-1)(n-2)$'





from scipy.special import factorial



def coherent_population_model(n, alpha):

    """

    Expected Fock state population in a coherent state.



    The Fock state population is modeled using the Poisson distribution.



    Parameters:

        n      : int or array-like

                 Fock state number(s) (0, 1, 2, ...).

        alpha  : float

                 Coherent state amplitude.



    Returns:

        Population(s) P(n) with the same shape as `n`.

    """

    n = np.asarray(n, dtype=int)

    lam = float(alpha)**2  # mean photon number |alpha|^2



    return np.exp(-lam) * (lam**n) / factorial(n, exact=False)

    

coherent_population_model.equation = r'$P_n(\alpha) = e^{-|\alpha|^2}\,\frac{|\alpha|^{2n}}{n!}$'



def poisson_with_offset_model(n_arr, lam, scale, offset):

    """

    Poisson distribution with amplitude scaling and baseline offset.



    This model describes a Poisson distribution (e.g., photon number distribution

    in a coherent state) with additional fitting parameters for amplitude and baseline.

    Useful when fitting experimental data where the raw Poisson distribution needs

    to be scaled or shifted.



    Parameters:

        n_arr  : array-like

                 Fock state number(s) (0, 1, 2, ...).

        lam    : float

                 Mean photon number Î» (lambda), typically |alpha|Â² for coherent states.

        scale  : float

                 Amplitude scaling factor for the Poisson distribution.

        offset : float

                 Baseline offset added to the scaled Poisson distribution.



    Returns:

        Population(s) with the same shape as `n_arr`.

    """

    n_arr = np.asarray(n_arr, dtype=float)

    n_int_local = n_arr.astype(int)

    facs = np.array([factorial(k) for k in n_int_local], dtype=float)

    pois = np.exp(-lam) * (lam**n_arr) / facs

    return offset + scale * pois



poisson_with_offset_model.equation = r'$P(n) = \mathrm{offset} + \mathrm{scale} \cdot e^{-\lambda}\,\frac{\lambda^n}{n!}$'



def rb_survival_model(m, p, A, B):

    """

    Randomized benchmarking survival probability model.



    The survival probability decays exponentially with the number of gates,

    characterized by the average gate fidelity p.



    Parameters:

        m : array-like

            Number of Clifford gates (sequence length).

        p : float

            Average survival probability per gate (0 < p <= 1).

        A : float

            Amplitude (scale factor).

        B : float

            Baseline asymptotic value.



    Returns:

        Survival probability at sequence length m.

    """

    return A*p**m+B



rb_survival_model.equation = r'$y = A\,p^m + B$'





# Pauli matrices

_SIGMA = {

    "x": np.array([[0, 1], [1, 0]], dtype=complex),

    "y": np.array([[0, -1j], [1j, 0]], dtype=complex),

    "z": np.array([[1, 0], [0, -1]], dtype=complex),

}



def qubit_pulse_train_model(

    N,

    theta,

    phi,

    *,

    r0=(0.0, 0.0, 1.0),

    delta=0.0,

    amp_err=0.0,

    phase_err=0.0,

):

    """

    Bloch-vector model for a repeated imperfect single-qubit pulse.



    Parameters

    ----------

    theta : float

        Intended rotation angle per pulse (radians), e.g. pi for X180.

    phi : float

        Intended drive phase (radians). phi=0 -> X, phi=pi/2 -> Y.

    N : int or array-like

        Number of pulse repetitions. Can be a scalar or an array of integers.

    r0 : tuple or array, shape (3,)

        Initial Bloch vector. |g> -> (0,0,+1), |e> -> (0,0,-1).

    delta : float

        Detuning accumulated over ONE pulse (Delta * Ï„), in radians.

        This tilts the rotation axis toward Z.

    amp_err : float

        Fractional amplitude error: theta -> theta * (1 + amp_err).

    phase_err : float

        Phase (axis) error in radians: phi -> phi + phase_err.



    Returns

    -------

    rN : np.ndarray

        Bloch vector(s) after N pulses.

        - If N is scalar: shape (3,)

        - If N is array: shape (len(N), 3)

    """

    r = np.asarray(r0, dtype=float).reshape(3)



    # Effective rotation vector per pulse

    th = theta * (1.0 + amp_err)

    ph = phi + phase_err



    vx = th * np.cos(ph)

    vy = th * np.sin(ph)

    vz = delta



    vnorm = np.sqrt(vx*vx + vy*vy + vz*vz)

    

    # Build unitary U = exp[-i (v Â· sigma)/2]

    vhat = np.array([vx, vy, vz]) / vnorm if vnorm != 0.0 else np.array([0.0, 0.0, 1.0])

    c = np.cos(vnorm / 2.0)

    s = np.sin(vnorm / 2.0)



    sigma_dot = (

        vhat[0] * _SIGMA["x"]

        + vhat[1] * _SIGMA["y"]

        + vhat[2] * _SIGMA["z"]

    )

    U = c * np.eye(2, dtype=complex) - 1j * s * sigma_dot

    Udag = U.conj().T



    # Convert unitary to SO(3) Bloch rotation matrix

    sigmas = [_SIGMA["x"], _SIGMA["y"], _SIGMA["z"]]

    R1 = np.zeros((3, 3), dtype=float)

    for i in range(3):

        for j in range(3):

            R1[i, j] = 0.5 * np.trace(

                sigmas[i] @ U @ sigmas[j] @ Udag

            ).real



    # Handle scalar vs array N

    N_array = np.atleast_1d(N)

    is_scalar = np.isscalar(N)

    

    # Compute for each N value

    results = []

    for n_val in N_array:

        if vnorm == 0.0 or n_val == 0:

            results.append(r.copy())

        else:

            RN = np.linalg.matrix_power(R1, int(n_val))

            results.append(RN @ r)

    

    result_array = np.array(results)

    

    # Return scalar shape if input was scalar

    if is_scalar:

        return result_array[0]

    else:

        return result_array



qubit_pulse_train_model.equation = (

    r'$\vec{r}_N = R^N \vec{r}_0,\quad '

    r'U = \exp\!\bigl[-i\,\vec{v}\cdot\vec{\sigma}/2\bigr],\quad '

    r'\vec{v} = \bigl(\theta(1+\varepsilon_a)\cos(\phi+\varepsilon_\phi),\,'

    r'\theta(1+\varepsilon_a)\sin(\phi+\varepsilon_\phi),\,\delta\bigr)$'

)



# Example usage:

if __name__ == '__main__':

    pass

