"""Numerical fits for SnV OPX calibration; no GUI or hardware dependencies.

Amplitudes are OPX scale factors (1 == 100%). The tracker's historical
``omega`` column is cycles/us (MHz), not angular frequency in rad/us.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit, minimize_scalar


def ensure_dummy_rabi_log(folder, name="snv_e1_e2"):
    """Create an explicitly named synthetic RP fixture, never measured data."""
    from pathlib import Path
    filename = name + "_dummy_rabi.dat"
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("Calibration name must not contain a path.")
    path = Path(folder) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write("amp0\ttransition\tomega\tdate\n")
            for amplitude in np.linspace(0, 1, 11):
                stream.write(f"{amplitude:.1f}\t0\t{5*amplitude:.1f}\tSYNTHETIC_NOT_MEASURED\n")
    except FileExistsError:
        pass
    return path


@dataclass
class CalibrationFit:
    x: np.ndarray
    y: np.ndarray
    fit_x: np.ndarray
    fit_y: np.ndarray
    frequency: float
    error: float
    r_squared: float


def _xy(x, y, minimum=8):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or x.size < minimum:
        raise ValueError(f"Need at least {minimum} paired data points.")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Calibration contains missing or nonfinite data.")
    order = np.argsort(x)
    x, y = x[order], y[order]
    if np.any(np.diff(x) <= 0) or np.ptp(y) <= 1e-12:
        raise ValueError("Need distinct x values and nonconstant observations.")
    return x, y


def fit_time_sine(duration_ns, signal, minimum_r_squared=0.7):
    """Fit a time trace; x/fit_x are microseconds, frequency/error are MHz."""
    x, y = _xy(np.asarray(duration_ns, dtype=float)/1000, signal, minimum=12)
    lower = 0.5 / np.ptp(x)
    upper = 0.45 / np.max(np.diff(x))
    if upper <= lower:
        raise ValueError("Time grid is too sparse to resolve an oscillation.")

    def linear_fit(k):
        design = np.column_stack((np.ones_like(x), np.cos(2*np.pi*k*x),
                                  np.sin(2*np.pi*k*x)))
        coeff = np.linalg.lstsq(design, y, rcond=None)[0]
        return np.sum((design @ coeff - y)**2), coeff

    grid = np.linspace(lower, upper, max(300, 12 * len(x)))
    scores = np.array([linear_fit(k)[0] for k in grid])
    index = int(np.argmin(scores))
    if index in (0, len(grid)-1):
        raise ValueError("Oscillation is unresolved or near the sampling limit.")
    result = minimize_scalar(lambda k: linear_fit(k)[0],
                             bounds=(grid[index-1], grid[index+1]), method="bounded")
    _, coeff = linear_fit(result.x)

    def model(a, offset, cosine, sine, k):
        return offset + cosine*np.cos(2*np.pi*k*a) + sine*np.sin(2*np.pi*k*a)

    parameters, covariance = curve_fit(
        model, x, y, p0=[*coeff, result.x],
        bounds=([-np.inf]*3 + [lower], [np.inf]*3 + [upper]), maxfev=20000)
    residual = np.sum((model(x, *parameters)-y)**2)
    r_squared = 1 - residual / np.sum((y-y.mean())**2)
    error = float(np.sqrt(max(0, covariance[3, 3])))
    if r_squared < minimum_r_squared or not np.isfinite(error):
        raise ValueError(f"Sine fit rejected: R²={r_squared:.3f}.")
    if parameters[3] - lower < 0.01*(upper-lower) or upper-parameters[3] < 0.01*(upper-lower):
        raise ValueError("Sine frequency is too close to a fit bound.")
    fit_x = np.linspace(x[0], x[-1], 500)
    return CalibrationFit(x, y, fit_x, model(fit_x, *parameters),
                          float(parameters[3]), error, float(r_squared))


def rabi_calibration(frame, observation="result_0"):
    """Fit duration sweeps independently at each fixed amplitude.

    Return normalized amplitudes, measured frequencies in MHz, and fits keyed
    by amplitude percent. No proportionality between amplitude and frequency
    is imposed. A monotonic response allows unambiguous inverse interpolation.
    """
    if not np.isfinite(frame[["MW_amp", "MW_pulse_len", observation]].to_numpy(dtype=float)).all():
        raise ValueError("Calibration contains missing or nonfinite data.")
    if (frame.MW_pulse_len <= 0).any():
        raise ValueError("Pulse durations must be positive ns values.")
    fits, amplitudes, frequencies = {}, [], []
    for amplitude, rows in frame.groupby("MW_amp", sort=True):
        if not 0 < amplitude <= 100:
            raise ValueError("Rabi amplitudes must be in (0, 100]%; zero has no oscillation to fit.")
        averaged = rows.groupby("MW_pulse_len")[observation].mean().sort_index()
        try:
            fit = fit_time_sine(averaged.index.to_numpy(), averaged.to_numpy())
        except ValueError as exc:
            raise ValueError(f"Rabi fit at {amplitude:g}% amplitude: {exc}") from exc
        fits[float(amplitude)] = fit
        amplitudes.append(amplitude/100)
        frequencies.append(fit.frequency)
    if len(fits) < 2:
        raise ValueError("Need time sweeps at at least two amplitudes for interpolation.")
    if np.any(np.diff(frequencies) <= 0):
        raise ValueError("Fitted frequencies must increase with amplitude for inverse interpolation.")
    return np.asarray(amplitudes), np.asarray(frequencies), fits


def fit_odmr(frequency_mhz, signal, minimum_r_squared=0.5):
    """Fit a single Lorentzian peak or dip; return its center in MHz."""
    x, y = _xy(frequency_mhz, signal)
    step, span = np.min(np.diff(x)), np.ptp(x)

    def model(f, offset, contrast, center, width):
        return offset + contrast / (1 + ((f-center)/width)**2)

    candidates = []
    for index in (np.argmax(y), np.argmin(y)):
        try:
            p, cov = curve_fit(model, x, y,
                p0=[np.median(y), y[index]-np.median(y), x[index], span/10],
                bounds=([-np.inf, -np.inf, x[0], step/2],
                        [np.inf, np.inf, x[-1], span/2]), maxfev=20000)
            candidates.append((np.sum((model(x, *p)-y)**2), p, cov))
        except (RuntimeError, ValueError):
            continue
    if not candidates:
        raise ValueError("ODMR fit did not converge.")
    residual, p, cov = min(candidates, key=lambda item: item[0])
    r_squared = 1 - residual/np.sum((y-y.mean())**2)
    error = float(np.sqrt(max(0, cov[2, 2])))
    if (r_squared < minimum_r_squared or not np.isfinite(error)
            or not x[0]+step < p[2] < x[-1]-step or error > p[3]
            or p[3] >= 0.49*span):
        raise ValueError(f"ODMR fit rejected: center/width unresolved or R²={r_squared:.3f}.")
    fit_x = np.linspace(x[0], x[-1], 500)
    return CalibrationFit(x, y, fit_x, model(fit_x, *p), float(p[2]), error, float(r_squared))
