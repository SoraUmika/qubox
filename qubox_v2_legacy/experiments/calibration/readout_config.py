"""Configuration dataclass for the readout calibration pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import warnings


@dataclass
class ReadoutConfig:
    """Centralised configuration for the full readout calibration pipeline.

    This replaces scattered kwargs on :class:`CalibrateReadoutFull` with a
    single, documented configuration object.  All fields have sensible
    defaults that reproduce the current (pre-enhancement) behaviour.

    Parameters
    ----------
    ro_op : str
        Readout operation name (e.g. ``"readout"``).
    drive_frequency : float | None
        Readout drive frequency in Hz.  Must be set before running.
    ro_el : str
        Readout element name.
    r180 : str
        Pi-pulse operation to use for state preparation.
    skip_weights_optimization : bool
        If *True*, skip the weight-optimisation step entirely.
    n_avg_weights : int
        Number of averages for weight-optimisation traces.
    persist_weights : bool
        Persist optimised weights to the pulse manager.
    revert_on_no_improvement : bool
        If *True*, revert optimised weights when they do not improve
        discrimination fidelity over the baseline.
    cos_weight_key, sin_weight_key, m_sin_weight_key : str
        Integration-weight labels passed to the weight-optimisation and
        discrimination pipeline.  Changing these decouples the pipeline
        from the hard-coded ``"cos"``/``"sin"``/``"minus_sin"`` labels.
    n_samples_disc : int
        Number of IQ blob samples for the discrimination step.
    burn_rot_weights : bool
        If *True*, burn rotated weights after discrimination fitting.
    blob_k_g, blob_k_e : float | None
        Blob filtering thresholds for ground / excited states.
    k : float | None
        Legacy convenience alias for symmetric blob thresholding. When set,
        callers may use a single ``k`` value instead of separate
        ``blob_k_g``/``blob_k_e``.
    n_shots_butterfly : int
        Number of shots for the butterfly measurement.
    M0_MAX_TRIALS : int
        Maximum retries for post-selection preparation in butterfly
        measurement (legacy-compatible control).
    max_iterations : int
        Maximum discrimination+butterfly iterations (convergence loop).
        Default ``1`` preserves current single-pass behaviour.
    fidelity_tolerance : float
        Convergence threshold (percentage points).  The loop exits when
        ``|fidelity_new - fidelity_old| < fidelity_tolerance``.
    adaptive_samples : bool
        When *True*, start with fewer samples and increase if the
        statistical uncertainty (Wilson interval) exceeds the tolerance.
    min_samples_disc : int
        Minimum sample count; below this, a warning is emitted.
    display_analysis : bool
        Print analysis summaries during the pipeline.
    save : bool
        Persist experiment outputs to disk.
    gaussianity_warn_threshold : float
        Non-Gaussianity score above which a warning is logged.
    cv_split_ratio : float
        Fraction of IQ blob data held out for cross-validated fidelity.
        ``0.0`` (default) disables cross-validation.
    wopt_kwargs, ge_kwargs, bfly_kwargs : dict
        Extra keyword arguments forwarded to the respective sub-experiments.
    """

    # General
    ro_op: str = "readout"
    drive_frequency: float | None = None
    ro_el: str = "resonator"
    r180: str = "x180"

    # Weight optimisation
    skip_weights_optimization: bool = False
    n_avg_weights: int = 200_000
    persist_weights: bool = True
    revert_on_no_improvement: bool = False
    cos_weight_key: str = "cos"
    sin_weight_key: str = "sin"
    m_sin_weight_key: str = "minus_sin"

    # Discrimination
    n_samples_disc: int = 250_000
    burn_rot_weights: bool = True
    blob_k_g: float = 2.0
    blob_k_e: float | None = None
    k: float | None = None

    # Butterfly
    n_shots_butterfly: int = 50_000
    M0_MAX_TRIALS: int = 16

    # Iteration (Section 3)
    max_iterations: int = 1
    fidelity_tolerance: float = 0.5
    adaptive_samples: bool = False
    min_samples_disc: int = 100

    # Display / persistence
    display_analysis: bool = False
    save: bool = True

    # Extended analysis (Section 6)
    gaussianity_warn_threshold: float = 2.0
    cv_split_ratio: float = 0.0

    # Sub-experiment forwarded kwargs
    wopt_kwargs: dict = field(default_factory=dict)
    ge_kwargs: dict = field(default_factory=dict)
    bfly_kwargs: dict = field(default_factory=dict)

    # ------------------------------------------------------------
    # Explicit config aliases / controls (legacy-style naming)
    # ------------------------------------------------------------
    # Aliases (when set) override the corresponding canonical fields.
    measure_op: str | None = None
    n_samples: int | None = None

    # Explicit behavior controls
    update_weights: bool = True
    update_threshold: bool = True
    rotation_method: str = "optimal"
    weight_extraction_method: str = "ge_diff_norm"
    histogram_fitting: str = "two_state_discriminator"
    threshold_extraction: str = "optimal_discriminator"
    overwrite_policy: str = "override"

    # Explicit persistence controls
    save_to_config: bool = True
    save_calibration_json: bool = True
    save_calibration_db: bool = False
    save_measure_config: bool = True
    save_session_state: bool = False

    def validate(self) -> None:
        """Raise :class:`ValueError` if the configuration is invalid."""
        eff_drive_frequency = self.drive_frequency
        eff_n_samples_disc = int(self.n_samples) if self.n_samples is not None else self.n_samples_disc
        eff_ro_op = self.measure_op if self.measure_op is not None else self.ro_op

        if not eff_ro_op:
            raise ValueError("ro_op/measure_op is required")
        if self.drive_frequency is None:
            raise ValueError("drive_frequency is required")
        if eff_n_samples_disc < self.min_samples_disc:
            raise ValueError(
                f"n_samples_disc ({eff_n_samples_disc}) < "
                f"min_samples_disc ({self.min_samples_disc})"
            )
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        if not (0.0 <= self.cv_split_ratio < 1.0):
            raise ValueError(
                f"cv_split_ratio must be in [0, 1), got {self.cv_split_ratio}"
            )
        if self.rotation_method not in {"optimal"}:
            raise ValueError(
                f"rotation_method={self.rotation_method!r} not supported; only 'optimal' is valid"
            )
        if self.weight_extraction_method == "legacy_ge_diff_norm":
            warnings.warn(
                "weight_extraction_method='legacy_ge_diff_norm' is deprecated; use 'ge_diff_norm'.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.weight_extraction_method = "ge_diff_norm"
        if self.weight_extraction_method not in {"ge_diff_norm"}:
            raise ValueError(
                "weight_extraction_method must be 'ge_diff_norm'"
            )
        if self.histogram_fitting not in {"two_state_discriminator"}:
            raise ValueError(
                "histogram_fitting must be 'two_state_discriminator' for parity"
            )
        if self.threshold_extraction == "legacy_discriminator":
            warnings.warn(
                "threshold_extraction='legacy_discriminator' is deprecated; use 'optimal_discriminator'.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.threshold_extraction = "optimal_discriminator"
        if self.threshold_extraction not in {"optimal_discriminator"}:
            raise ValueError(
                "threshold_extraction must be 'optimal_discriminator'"
            )
        if self.overwrite_policy not in {"override", "error_if_exists"}:
            raise ValueError(
                f"overwrite_policy={self.overwrite_policy!r} must be 'override' or 'error_if_exists'"
            )
        _ = eff_drive_frequency

    def resolved_ro_op(self) -> str:
        return self.measure_op if self.measure_op is not None else self.ro_op

    def resolved_n_samples_disc(self) -> int:
        return int(self.n_samples) if self.n_samples is not None else int(self.n_samples_disc)

    @classmethod
    def from_binding(
        cls,
        ro: "Any",
        *,
        r180: str = "x180",
        **overrides: Any,
    ) -> "ReadoutConfig":
        """Construct a ReadoutConfig from a ReadoutBinding.

        Parameters
        ----------
        ro : ReadoutBinding
            The readout binding to derive configuration from.
        r180 : str
            Pi-pulse operation name.
        **overrides
            Any additional field overrides.

        Returns
        -------
        ReadoutConfig
        """
        from ...core.bindings import ReadoutBinding

        if not isinstance(ro, ReadoutBinding):
            raise TypeError(
                f"ReadoutConfig.from_binding: expected ReadoutBinding, "
                f"got {type(ro).__name__}"
            )

        # Derive ro_op from the binding's active_op or pulse_op
        ro_op = ro.active_op or "readout"
        if ro.pulse_op is not None:
            ro_op = getattr(ro.pulse_op, "op", ro_op)

        # Derive ro_el from the physical_id (no element name dependency)
        ro_el = ro.physical_id

        # Derive weight keys from binding
        weight_sets = ro.demod_weight_sets
        cos_key = "cos"
        sin_key = "sin"
        m_sin_key = "minus_sin"
        if weight_sets and len(weight_sets) >= 2:
            if len(weight_sets[0]) >= 2:
                cos_key = weight_sets[0][0]
                sin_key = weight_sets[0][1]
            if len(weight_sets[1]) >= 1:
                m_sin_key = weight_sets[1][0]

        kwargs: dict[str, Any] = {
            "ro_op": ro_op,
            "ro_el": ro_el,
            "r180": r180,
            "drive_frequency": ro.drive_frequency,
            "cos_weight_key": cos_key,
            "sin_weight_key": sin_key,
            "m_sin_weight_key": m_sin_key,
        }
        kwargs.update(overrides)
        return cls(**kwargs)
