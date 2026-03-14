import numpy as np

import qubox_tools as qt


def test_qubox_tools_generalized_fit_on_gaussian_model():
    x = np.linspace(-1.0, 1.0, 101)
    y = qt.fitting.models.gaussian_model(x, 0.15, 0.2, 0.8, 0.1)

    popt, _ = qt.generalized_fit(
        x,
        y,
        qt.fitting.models.gaussian_model,
        p0=[0.0, 0.25, 1.0, 0.0],
    )

    assert popt is not None
    assert np.allclose(popt, [0.15, 0.2, 0.8, 0.1], atol=1e-6)


def test_legacy_analysis_wrapper_resolves_to_extracted_function():
    from qubox_v2_legacy.analysis.fitting import generalized_fit as legacy_generalized_fit

    assert legacy_generalized_fit is qt.generalized_fit


def test_butterfly_metrics_runs_without_pandas_dependency():
    out = qt.algorithms.metrics.butterfly_metrics(
        m1_g=[0, 0, 0, 1],
        m1_e=[1, 1, 0, 1],
        m2_g=[0, 0, 0, 0],
        m2_e=[1, 1, 1, 1],
    )

    assert "F" in out
    assert "confusion_matrix" in out
    assert hasattr(out["confusion_matrix"], "__repr__")


def test_legacy_optimization_namespace_still_imports():
    import qubox_v2_legacy.optimization as legacy_optimization

    assert hasattr(legacy_optimization, "scipy_minimize")
