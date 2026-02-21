#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
from scipy.special import wofz

###############################################################################
# Common Analytical Model Functions
###############################################################################

def lorentzian_model(x, x0, fwhm, A, offset):
    """
    Generic Lorentzian model.

    Models a Lorentzian lineshape, which is often used to describe resonant
    responses in spectroscopy or other systems.

    Parameters:
        x      : array-like
                 Independent variable (e.g., frequency).
        x0     : float
                 Center value of the peak (e.g., resonance frequency).
        fwhm   : float
                 Full-width at half-maximum linewidth.
        A      : float
                 Amplitude of the Lorentzian.
        offset : float
                 Baseline offset.
                 
    Returns:
        Model value at x.
    """
    return offset + A / (1 + (2 * (x - x0) / fwhm) ** 2)

lorentzian_model.equation = r'$y = offset + \frac{A}{1 + \left(\frac{2\,(x - x_0)}{fwhm}\right)^2}$'


def gaussian_model(x, x0, sigma, A, offset):
    """
    Generic Gaussian model.

    Models a Gaussian profile that is commonly used to describe peak-like
    responses as well as distributions.

    Parameters:
        x      : array-like
                 Independent variable.
        x0     : float
                 Center value of the peak.
        sigma  : float
                 Standard deviation of the Gaussian.
        A      : float
                 Amplitude of the Gaussian peak.
        offset : float
                 Baseline offset.
                 
    Returns:
        Model value at x.
    """
    return offset + A * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2))

gaussian_model.equation = r'$y = offset + A\,\exp\!\left[-\frac{(x-x_0)^2}{2\sigma^2}\right]$'


def voigt_model(x, x0, sigma, gamma, A, offset):
    """
    Generic Voigt model.

    Models a Voigt profile, which represents the convolution of a Gaussian and
    a Lorentzian. It is widely used in spectroscopy to model line shapes that
    have contributions from both Doppler (Gaussian) and collisional (Lorentzian)
    broadening.

    Parameters:
        x      : array-like
                 Independent variable.
        x0     : float
                 Center value of the peak.
        sigma  : float
                 Standard deviation of the Gaussian component.
        gamma  : float
                 Lorentzian half-width at half-maximum (HWHM) or damping parameter.
        A      : float
                 Amplitude of the Voigt profile.
        offset : float
                 Baseline offset.
                 
    Returns:
        Model value at x.
    """
    # Compute the complex argument for the Faddeeva function (wofz)
    z = ((x - x0) + 1j * gamma) / (sigma * np.sqrt(2))
    voigt_profile = np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi))
    return offset + A * voigt_profile

voigt_model.equation = r'$y = offset + A\,\frac{\Re\!\left[w\!\left(\frac{x-x_0+i\gamma}{\sigma\sqrt{2}}\right)\right]}{\sigma\sqrt{2\pi}}$'


def linear_model(x, slope, intercept):
    """
    Generic Linear model.

    Models a linear relationship between the independent and dependent variables.

    Parameters:
        x         : array-like
                    Independent variable.
        slope     : float
                    Slope of the line.
        intercept : float
                    Y-intercept.
                    
    Returns:
        Model value at x.
    """
    return slope * x + intercept

linear_model.equation = r'$y = slope\,x + intercept$'

def exponential_model(t, A, tau, t0, offset):
    """
    Generic Exponential model.

    Models an exponential decay or growth function. Exponential behavior is 
    common in many physical processes including relaxation dynamics, 
    radioactive decay, or charging/discharging in circuits.

    Parameters:
        x      : array-like
                 Independent variable (e.g., time or distance).
        A      : float
                 Amplitude of the exponential component.
        tau    : float
                 Time constant (or decay constant). Positive values lead to decay,
                 while negative values produce growth.
        offset : float
                 Baseline offset.
                 
    Returns:
        Model value at x.
    """
    return offset + A * np.exp(-(t-t0) / tau)

exponential_model.equation = r'$y = offset + A\,e^{-(t-t_0)/\tau}$'


def polynomial_model(x, coeffs):
    """
    Generic Polynomial model.

    Models a polynomial function of degree n (where n = len(coeffs)-1). 
    The polynomial is evaluated in the form:
    
        y = c0*x^n + c1*x^(n-1) + ... + cn
    
    Parameters:
        x      : array-like
                 Independent variable.
        coeffs : array-like
                 Sequence of polynomial coefficients, with the coefficient for 
                 the highest power first.
                 
    Returns:
        Model value at x.
    """
    return np.polyval(coeffs, x)

polynomial_model.equation = r'$y = c_0\,x^n + c_1\,x^{n-1} + \cdots + c_n$'

###############################################################################
# Example usage (optional)
###############################################################################
if __name__ == '__main__':
    # Define a common x-range for demonstration
    x = np.linspace(-10, 10, 400)
    
    # Lorentzian Model Example
    y_lorentzian = lorentzian_model(x, x0=0, fwhm=4, A=1, offset=0)
    plt.figure()
    plt.plot(x, y_lorentzian)
    plt.title('Lorentzian Model')
    plt.xlabel('x')
    plt.ylabel('y')
    
    # Gaussian Model Example
    y_gaussian = gaussian_model(x, x0=0, sigma=2, A=1, offset=0)
    plt.figure()
    plt.plot(x, y_gaussian)
    plt.title('Gaussian Model')
    plt.xlabel('x')
    plt.ylabel('y')
    
    # Voigt Model Example
    y_voigt = voigt_model(x, x0=0, sigma=2, gamma=1, A=1, offset=0)
    plt.figure()
    plt.plot(x, y_voigt)
    plt.title('Voigt Model')
    plt.xlabel('x')
    plt.ylabel('y')
    
    # Linear Model Example
    y_linear = linear_model(x, slope=0.5, intercept=0)
    plt.figure()
    plt.plot(x, y_linear)
    plt.title('Linear Model')
    plt.xlabel('x')
    plt.ylabel('y')
    
    plt.show()

