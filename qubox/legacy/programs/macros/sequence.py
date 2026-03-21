from qm.qua import *
from .measure import measureMacro
from qualang_tools.loops import from_array
import numpy as np
class sequenceMacros:
    @classmethod
    def qubit_ramsey(cls, delay_clk, qb_el, r90_1, r90_2):
        play(r90_1, qb_el)
        wait(delay_clk, qb_el)
        play(r90_2, qb_el)

    @classmethod
    def qubit_echo(cls, delay_clk_1, delay_clk_2, qb_el, r90, r180):
        play(r90, qb_el)
        wait(delay_clk_1, qb_el)
        play(r180, qb_el)
        wait(delay_clk_2, qb_el)
        play(r90, qb_el)

    @classmethod
    def conditional_reset_ground(cls, I, thr, r180: str, qb_el: str):
        play(r180, qb_el, condition=I > thr)
        align()

    @classmethod
    def conditional_reset_excited(cls, I, thr, r180: str, qb_el: str):
        play(r180, qb_el, condition=I < thr)
        align()

    @classmethod
    def qubit_state_tomography(
        cls,
        state,
        *,
        state_prep: callable = None,
        state_st=None,
        therm_clks=None,
        targets=None,
        axis: str = "z",
        qb_el=None,
        x90="x90",
        yn90="yn90",
        qb_probe_if=None,
        selective_pulse: str = None,
        selective_freq: int = None,
        wait_after: bool = False,
        wait_after_clks=None,
        bindings=None,
    ):
        if bindings is not None:
            from ...core.bindings import ConfigBuilder
            _names = ConfigBuilder.ephemeral_names(bindings)
            if qb_el is None:
                qb_el = _names.get("qubit", "__qb")
        else:
            qb_el = qb_el or "qubit"

        if state_prep:
            state_prep()
            align()

        # ------------------------------------------------------------------
        # If selective_pulse is provided, we enforce a symmetric OFF/ON skeleton:
        #   state_prep -> pre-rotation(axis) -> [tag or dummy] -> measure Z
        # This is what you want for clean OFF/ON subtraction.
        # ------------------------------------------------------------------
        if selective_pulse is not None:
            # 1) Pre-rotation (map requested axis -> Z)
            if axis == "x":
                play(yn90, qb_el)  # Ry(-pi/2)
            elif axis == "y":
                play(x90, qb_el)   # Rx(+pi/2) (your convention)
            # align qubit with readout element timing like measureMacro does
            align(qb_el, measureMacro.active_element())

            # 2) Tag (ON) or Dummy (OFF) at the SAME frequency and SAME duration
            if selective_freq is not None:
                update_frequency(qb_el, selective_freq)

            if wait_after:
                if wait_after_clks is not None:
                    wait(int(wait_after_clks))
                else:
                # OFF: dummy pulse with identical duration
                    play(selective_pulse * amp(0), qb_el)
            else:
                # ON: real selective pulse
                play(selective_pulse, qb_el)

            align(qb_el, measureMacro.active_element())

            # 3) Always measure Z (no extra tomography rotation here)
            measureMacro.measure(with_state=True, targets=targets, state=state,
                                axis="z", qb_el=qb_el)

        else:
            # ------------------------------------------------------------------
            # No selective pulse: standard tomography (legacy behavior)
            # ------------------------------------------------------------------
            if qb_probe_if is not None:
                update_frequency(qb_el, qb_probe_if)

            measureMacro.measure(with_state=True, targets=targets, state=state,
                                axis=axis, x90=x90, yn90=yn90, qb_el=qb_el)

        if state_st:
            save(state, state_st)

        if therm_clks:
            wait(int(therm_clks))


    @classmethod
    def num_splitting_spectroscopy(cls, probe_ifs, state_prep, I, Q, I_st, Q_st, st_therm_clks,
        *,
        qb_el=None,
        st_el=None,
        sel_r180="sel_x180",
        bindings=None,
    ):
        if bindings is not None:
            from ...core.bindings import ConfigBuilder
            _names = ConfigBuilder.ephemeral_names(bindings)
            if qb_el is None:
                qb_el = _names.get("qubit", "__qb")
            if st_el is None:
                st_el = _names.get("storage", "__st")
        else:
            qb_el = qb_el or "qubit"
            st_el = st_el or "storage"

        f = declare(int)
        with for_(*from_array(f, probe_ifs)):
            update_frequency(qb_el, f)
            state_prep()
            align()

            play(sel_r180, qb_el)
            align()
            measureMacro.measure(targets=[I, Q])
            wait(int(st_therm_clks), st_el)
            save(I, I_st)
            save(Q, Q_st)

    @classmethod
    def fock_resolved_spectroscopy(cls, fock_ifs, state_prep, I, Q, I_st, Q_st, st_therm_clks,
        *, qb_el=None, st_el=None, sel_r180="sel_x180",
        bindings=None,
    ):
        if bindings is not None:
            from ...core.bindings import ConfigBuilder
            _names = ConfigBuilder.ephemeral_names(bindings)
            if qb_el is None:
                qb_el = _names.get("qubit", "__qb")
            if st_el is None:
                st_el = _names.get("storage", "__st")
        else:
            qb_el = qb_el or "qubit"
            st_el = st_el or "storage"

        f = declare(int)

        with for_each_(f, fock_ifs):
            state_prep()
            align()

            update_frequency(qb_el, f)
            align(qb_el, st_el)
            play(sel_r180, qb_el)
            align(qb_el, measureMacro.active_element())

            measureMacro.measure(targets=[I, Q])
            wait(int(st_therm_clks), st_el)
            save(I, I_st)
            save(Q, Q_st)

    @classmethod
    def prepare_state(
        cls,
        *,
        target_state: str = "g",           # "g" or "e"
        policy: str | None = None,         # "ZSCORE", "AFFINE", "HYSTERESIS", "BLOBS", "POSTERIOR", or None
        r180: str = "x180",
        qb_el: str = None,
        max_trials: int = 4,
        targets: list | None = None,
        state=None,
        bindings=None,
        **prep_kwargs,
    ):
        """
        Actively reset the qubit into `target_state` using single-shot readout.

        Parameters
        ----------
        target_state : {"g","e"}
            Desired final state: "g" for ground, "e" for excited.
        policy : str | None
            One of {"ZSCORE","AFFINE","HYSTERESIS","BLOBS"} or None.
            If None, uses simple scalar-threshold rule on I.
        r180 : str
            Name of the pi_val pulse used for conditional resets.
        qb_el : str
            Qubit element name.
        max_trials : int
            Maximum number of prepareâ€“measure attempts.
        targets : list | None
            Optional [I, Q] QUA variables to reuse. If None, they are declared here.
        state : QUA bool or None
            Optional QUA bool to reuse as the measured state. If None, declared here.
        **prep_kwargs :
            - Common:
                threshold : float (optional)
                    If provided, overrides the discrimination threshold for this call.

            - policy == "ZSCORE":
                mu_g, sigma_g, mu_e, sigma_e, k=2.5

            - policy == "AFFINE":
                a, b, c, margin=0.0

            - policy == "HYSTERESIS":
                T_low, T_high   (default to threshold if omitted)

            - policy == "BLOBS":
                Ig, Qg, rg, Ie, Qe, re, require_exclusive=True

            - policy == "POSTERIOR":
                Ig, Qg, Ie, Qe, sigma_g, sigma_e,
                posterior_classification_threshold=0.5
        """

        if bindings is not None:
            from ...core.bindings import ConfigBuilder
            _names = ConfigBuilder.ephemeral_names(bindings)
            if qb_el is None:
                qb_el = _names.get("qubit", "__qb")
        else:
            qb_el = qb_el or "qubit"

        # -------------------------------
        # Normalize inputs
        # -------------------------------
        ts = str(target_state).lower()
        if ts not in ("g", "e"):
            raise ValueError(f"prepare_state: target_state must be 'g' or 'e', got {target_state!r}")

        # Copy prep_kwargs so we can safely pop from it
        p = dict(prep_kwargs or {})

        # Threshold: global default, overridden by prep_kwargs["threshold"] if present
        thr = p["threshold"]

        policy_norm = policy.upper() if isinstance(policy, str) else None

        # -------------------------------
        # Pre-parse policy parameters
        # -------------------------------
        if policy_norm == "ZSCORE":
            try:
                mu_g  = float(p["mu_g"])
                sig_g = float(p["sigma_g"])
                mu_e  = float(p["mu_e"])
                sig_e = float(p["sigma_e"])
            except KeyError as e:
                raise ValueError(
                    "prepare_state[ZSCORE]: missing one of mu_g, sigma_g, mu_e, sigma_e"
                ) from e
            k = float(p.get("k", 2.5))
            if sig_g <= 0 or sig_e <= 0:
                raise ValueError("prepare_state[ZSCORE]: sigmas must be > 0")

        elif policy_norm == "AFFINE":
            try:
                a = float(p["a"])
                b = float(p["b"])
                c = float(p["c"])
            except KeyError as e:
                raise ValueError(
                    "prepare_state[AFFINE]: missing one of a, b, c"
                ) from e
            margin = float(p.get("margin", 0.0))

        elif policy_norm == "HYSTERESIS":
            # Default to scalar threshold if not provided
            T_low  = float(p.get("T_low", thr))
            T_high = float(p.get("T_high", thr))
            if not (T_low < T_high):
                raise ValueError("prepare_state[HYSTERESIS]: require T_low < T_high")

        elif policy_norm == "BLOBS":
            try:
                Ig0 = float(p["Ig"])
                Qg0 = float(p["Qg"])
                rg2 = float(p["rg2"]) if "rg2" in p else float(p["rg"]) ** 2
                Ie0 = float(p["Ie"])
                Qe0 = float(p["Qe"])
                re2 = float(p["re2"]) if "re2" in p else float(p["re"]) ** 2
            except KeyError as e:
                raise ValueError(
                    "prepare_state[BLOBS]: missing one of "
                    "Ig, Qg, rg (or rg2), Ie, Qe, re (or re2)"
                ) from e

            require_exclusive = bool(p.get("require_exclusive", True))

            # QUA vars for blob geometry
            d_g2 = declare(fixed)
            d_e2 = declare(fixed)
            dIg  = declare(fixed)
            dQg  = declare(fixed)
            dIe  = declare(fixed)
            dQe  = declare(fixed)
            inside_g = declare(bool)
            inside_e = declare(bool)

        elif policy_norm == "POSTERIOR":
            try:
                Ig0 = float(p["Ig"])
                Qg0 = float(p["Qg"])
                Ie0 = float(p["Ie"])
                Qe0 = float(p["Qe"])
                sigma_g = float(p["sigma_g"])
                sigma_e = float(p["sigma_e"])
            except KeyError as e:
                raise ValueError(
                    "prepare_state[POSTERIOR]: missing one of Ig, Qg, Ie, Qe, sigma_g, sigma_e"
                ) from e

            if not (np.isfinite(sigma_g) and sigma_g > 0):
                raise ValueError(f"prepare_state[POSTERIOR]: sigma_g must be finite and > 0, got {sigma_g}")
            if not (np.isfinite(sigma_e) and sigma_e > 0):
                raise ValueError(f"prepare_state[POSTERIOR]: sigma_e must be finite and > 0, got {sigma_e}")

            post_thr = float(p.get("posterior_classification_threshold", 0.5))
            if not np.isfinite(post_thr) or post_thr < 0.0 or post_thr > 1.0:
                raise ValueError(
                    "prepare_state[POSTERIOR]: posterior_classification_threshold must be finite in [0, 1]"
                )

            pi_e = float(p.get("posterior_prior_e", 0.5))
            if not np.isfinite(pi_e) or not (0.0 < pi_e < 1.0):
                raise ValueError("prepare_state[POSTERIOR]: posterior_prior_e must be finite in (0,1)")
            pi_g = 1.0 - pi_e
            log_prior_odds = float(np.log(pi_e / pi_g))

            if 0.0 < post_thr < 1.0:
                post_logit_thr = float(np.log(post_thr / (1.0 - post_thr)))
            else:
                post_logit_thr = 0.0

            inv_2sg2 = float(1.0 / (2.0 * sigma_g * sigma_g))
            inv_2se2 = float(1.0 / (2.0 * sigma_e * sigma_e))
            sg2 = float(sigma_g * sigma_g)
            se2 = float(sigma_e * sigma_e)
            llr_clip = float(p.get("posterior_llr_clip", p.get("posterior_exp_clip", 60.0)))
            if not np.isfinite(llr_clip) or llr_clip <= 0:
                raise ValueError("prepare_state[POSTERIOR]: posterior_llr_clip must be finite and > 0")

            # QUA-side constants for Math domain-safe operations
            sg2_q = declare(fixed)
            se2_q = declare(fixed)
            assign(sg2_q, sg2)
            assign(se2_q, se2)

        # -------------------------------
        # I/Q + state variables
        # -------------------------------
        if not targets:
            I = declare(fixed)
            Q = declare(fixed)
            targets = [I, Q]
        else:
            I = targets[0]
            Q = targets[1] if len(targets) > 1 else declare(fixed)

        if state is None:
            state = declare(bool)

        tries  = declare(int)
        done   = declare(bool)
        accept = declare(bool)

        assign(tries, 0)
        assign(done, False)

        # -------------------------------
        # Active reset loop
        # -------------------------------
        with while_((~done) & (tries < max_trials)):
            # Conditional pi_val to move toward target_state
            if ts == "e":
                cls.conditional_reset_excited(I, thr, r180=r180, qb_el=qb_el)
            else:
                cls.conditional_reset_ground(I, thr, r180=r180, qb_el=qb_el)

            # Verify via measurement
            measureMacro.measure(with_state=True, targets=targets, state=state)

            # Acceptance rule
            if policy_norm == "ZSCORE":
                if ts == "e":
                    assign(accept, (I - mu_e) > (k * sig_e))
                else:
                    assign(accept, (mu_g - I) > (k * sig_g))

            elif policy_norm == "AFFINE":
                S = declare(fixed)
                assign(S, a * I + b * Q)
                if ts == "e":
                    assign(accept, S > (c + margin))
                else:
                    assign(accept, S < (c - margin))

            elif policy_norm == "HYSTERESIS":
                if ts == "e":
                    assign(accept, I >= T_high)
                else:
                    assign(accept, I <= T_low)

            elif policy_norm == "BLOBS":
                # distance^2 to ground center
                assign(dIg, I - Ig0)
                assign(dQg, Q - Qg0)
                assign(d_g2, dIg * dIg + dQg * dQg)

                # distance^2 to excited center
                assign(dIe, I - Ie0)
                assign(dQe, Q - Qe0)
                assign(d_e2, dIe * dIe + dQe * dQe)

                # inside each circle?
                assign(inside_g, d_g2 <= rg2)
                assign(inside_e, d_e2 <= re2)

                if ts == "e":
                    if require_exclusive:
                        assign(accept, inside_e & (~inside_g))
                    else:
                        assign(accept, inside_e)
                else:
                    if require_exclusive:
                        assign(accept, inside_g & (~inside_e))
                    else:
                        assign(accept, inside_g)

            elif policy_norm == "POSTERIOR":
                if Q is None:
                    raise ValueError("prepare_state[POSTERIOR]: requires Q")

                if post_thr <= 0.0:
                    assign(accept, True)
                elif post_thr >= 1.0:
                    assign(accept, False)
                else:
                    d_g2_q = declare(fixed)
                    d_e2_q = declare(fixed)
                    l_g_q = declare(fixed)
                    l_e_q = declare(fixed)
                    llr_q = declare(fixed)
                    llr_clip_q = declare(fixed)

                    assign(d_g2_q, ((I - Ig0) * (I - Ig0)) + ((Q - Qg0) * (Q - Qg0)))
                    assign(d_e2_q, ((I - Ie0) * (I - Ie0)) + ((Q - Qe0) * (Q - Qe0)))

                    assign(l_g_q, (-d_g2_q * inv_2sg2) - Math.ln(sg2_q))
                    assign(l_e_q, (-d_e2_q * inv_2se2) - Math.ln(se2_q))

                    # LLR = log p(e|S) - log p(g|S) + log(pi_e/pi_g)
                    assign(llr_q, (l_e_q - l_g_q) + log_prior_odds)

                    with if_(llr_q > llr_clip):
                        assign(llr_clip_q, llr_clip)
                    with elif_(llr_q < -llr_clip):
                        assign(llr_clip_q, -llr_clip)
                    with else_():
                        assign(llr_clip_q, llr_q)

                    if ts == "e":
                        assign(accept, llr_clip_q >= post_logit_thr)
                    else:
                        assign(accept, llr_clip_q <= -post_logit_thr)

            else:
                # Default SCALAR policy: compare to (possibly overridden) threshold
                if ts == "e":
                    assign(accept, I > thr)
                else:
                    assign(accept, I < thr)

            assign(done, accept)
            assign(tries, tries + 1)

    @classmethod
    def post_select(
        cls,
        *,
        accept,                 # QUA bool (passed in) -> assigned True/False here
        I,                      # QUA fixed
        Q=None,                 # QUA fixed (required for AFFINE/BLOBS)
        target_state: str="g",  # "g" or "e"
        policy: str | None=None,
        **kwargs,               # threshold + policy params
    ):
        ts = str(target_state).lower()
        if ts not in ("g", "e"):
            raise ValueError(f"post_select: target_state must be 'g' or 'e', got {target_state!r}")

        policy_norm = policy.upper() if isinstance(policy, str) else None

        # threshold used by default scalar policy (and often for correction outside)
        thr = float(kwargs.get("threshold", measureMacro._ro_disc_params.get("threshold", 0.0)))

        # ---- ZSCORE ----
        if policy_norm == "ZSCORE":
            mu_g  = float(kwargs["mu_g"])
            sig_g = float(kwargs["sigma_g"])
            mu_e  = float(kwargs["mu_e"])
            sig_e = float(kwargs["sigma_e"])
            k     = float(kwargs.get("k", 2.5))

            if ts == "e":
                assign(accept, (I - mu_e) > (k * sig_e))
            else:
                assign(accept, (mu_g - I) > (k * sig_g))

        # ---- AFFINE ----  (no scratch var: inline)
        elif policy_norm == "AFFINE":
            if Q is None:
                raise ValueError("post_select[AFFINE]: requires Q")
            a = float(kwargs["a"])
            b = float(kwargs["b"])
            c = float(kwargs["c"])
            margin = float(kwargs.get("margin", 0.0))

            if ts == "e":
                assign(accept, (a * I + b * Q) > (c + margin))
            else:
                assign(accept, (a * I + b * Q) < (c - margin))

        # ---- HYSTERESIS ----
        elif policy_norm == "HYSTERESIS":
            T_low  = float(kwargs.get("T_low", thr))
            T_high = float(kwargs.get("T_high", thr))
            if not (T_low < T_high):
                raise ValueError("post_select[HYSTERESIS]: require T_low < T_high")

            if ts == "e":
                assign(accept, I >= T_high)
            else:
                assign(accept, I <= T_low)

        # ---- BLOBS ---- (inline geometry, no declares)
        elif policy_norm == "BLOBS":
            if Q is None:
                raise ValueError("post_select[BLOBS]: requires Q")

            Ig0 = float(kwargs["Ig"])
            Qg0 = float(kwargs["Qg"])
            Ie0 = float(kwargs["Ie"])
            Qe0 = float(kwargs["Qe"])
            rg2 = float(kwargs["rg2"]) if "rg2" in kwargs else float(kwargs["rg"]) ** 2
            re2 = float(kwargs["re2"]) if "re2" in kwargs else float(kwargs["re"]) ** 2
            require_exclusive = bool(kwargs.get("require_exclusive", True))

            # NEW knobs (all host-side constants)
            extend_halfplane = bool(kwargs.get("extend_halfplane", False))
            extend_mode = str(kwargs.get("extend_mode", "circle_edge")).lower()   # "circle_edge" or "threshold"
            extend_margin = float(kwargs.get("extend_margin", 0.0))

            inside_g = ((I - Ig0) * (I - Ig0) + (Q - Qg0) * (Q - Qg0)) <= rg2
            inside_e = ((I - Ie0) * (I - Ie0) + (Q - Qe0) * (Q - Qe0)) <= re2

            # Base acceptance: crescent or circle depending on require_exclusive
            if ts == "e":
                expr = (inside_e & (~inside_g)) if require_exclusive else inside_e
            else:
                expr = (inside_g & (~inside_e)) if require_exclusive else inside_g

            # Optional extension: crescent OR "definitely not the other" half-plane
            if extend_halfplane:
                if extend_mode == "threshold":
                    # use scalar threshold along I
                    if ts == "e":
                        extra = I >= (thr + extend_margin)
                    else:
                        extra = I <= (thr - extend_margin)
                else:
                    # default: "circle_edge" â€” use the x-extent of the opposite blob
                    # (sqrt happens on host; QUA sees constants)
                    rg = float(np.sqrt(rg2))
                    re = float(np.sqrt(re2))

                    if ts == "e":
                        # definitely-not-g region: right of g-circle right edge
                        extra = I >= (Ig0 + rg + extend_margin)
                    else:
                        # definitely-not-e region: left of e-circle left edge
                        extra = I <= (Ie0 - re - extend_margin)

                expr = expr | extra

            assign(accept, expr)

        # ---- POSTERIOR ----
        elif policy_norm == "POSTERIOR":
            if Q is None:
                raise ValueError("post_select[POSTERIOR]: requires Q")

            try:
                Ig0 = float(kwargs["Ig"])
                Qg0 = float(kwargs["Qg"])
                Ie0 = float(kwargs["Ie"])
                Qe0 = float(kwargs["Qe"])
                sigma_g = float(kwargs["sigma_g"])
                sigma_e = float(kwargs["sigma_e"])
            except KeyError as e:
                raise ValueError(
                    "post_select[POSTERIOR]: missing one of Ig, Qg, Ie, Qe, sigma_g, sigma_e"
                ) from e

            if not (np.isfinite(sigma_g) and sigma_g > 0):
                raise ValueError(f"post_select[POSTERIOR]: sigma_g must be finite and > 0, got {sigma_g}")
            if not (np.isfinite(sigma_e) and sigma_e > 0):
                raise ValueError(f"post_select[POSTERIOR]: sigma_e must be finite and > 0, got {sigma_e}")

            post_thr = float(kwargs.get("posterior_classification_threshold", 0.5))
            if not np.isfinite(post_thr) or post_thr < 0.0 or post_thr > 1.0:
                raise ValueError(
                    "post_select[POSTERIOR]: posterior_classification_threshold must be finite in [0, 1]"
                )

            pi_e = float(kwargs.get("posterior_prior_e", 0.5))
            if not np.isfinite(pi_e) or not (0.0 < pi_e < 1.0):
                raise ValueError("post_select[POSTERIOR]: posterior_prior_e must be finite in (0,1)")
            pi_g = 1.0 - pi_e
            log_prior_odds = float(np.log(pi_e / pi_g))

            if 0.0 < post_thr < 1.0:
                post_logit_thr = float(np.log(post_thr / (1.0 - post_thr)))
            else:
                post_logit_thr = 0.0

            llr_clip = float(kwargs.get("posterior_llr_clip", kwargs.get("posterior_exp_clip", 60.0)))
            if not np.isfinite(llr_clip) or llr_clip <= 0:
                raise ValueError("post_select[POSTERIOR]: posterior_llr_clip must be finite and > 0")

            if post_thr <= 0.0:
                assign(accept, True)
            elif post_thr >= 1.0:
                assign(accept, False)
            else:
                inv_2sg2 = float(1.0 / (2.0 * sigma_g * sigma_g))
                inv_2se2 = float(1.0 / (2.0 * sigma_e * sigma_e))
                sg2 = float(sigma_g * sigma_g)
                se2 = float(sigma_e * sigma_e)

                sg2_q = declare(fixed)
                se2_q = declare(fixed)
                d_g2_q = declare(fixed)
                d_e2_q = declare(fixed)
                l_g_q = declare(fixed)
                l_e_q = declare(fixed)
                llr_q = declare(fixed)
                llr_clip_q = declare(fixed)

                assign(sg2_q, sg2)
                assign(se2_q, se2)

                assign(d_g2_q, ((I - Ig0) * (I - Ig0)) + ((Q - Qg0) * (Q - Qg0)))
                assign(d_e2_q, ((I - Ie0) * (I - Ie0)) + ((Q - Qe0) * (Q - Qe0)))

                assign(l_g_q, (-d_g2_q * inv_2sg2) - Math.ln(sg2_q))
                assign(l_e_q, (-d_e2_q * inv_2se2) - Math.ln(se2_q))

                # LLR = log p(e|S) - log p(g|S) + log(pi_e/pi_g)
                assign(llr_q, (l_e_q - l_g_q) + log_prior_odds)

                with if_(llr_q > llr_clip):
                    assign(llr_clip_q, llr_clip)
                with elif_(llr_q < -llr_clip):
                    assign(llr_clip_q, -llr_clip)
                with else_():
                    assign(llr_clip_q, llr_q)

                if ts == "e":
                    assign(accept, llr_clip_q >= post_logit_thr)
                else:
                    assign(accept, llr_clip_q <= -post_logit_thr)

        # ---- DEFAULT scalar threshold on I ----
        else:
            if ts == "e":
                assign(accept, I > thr)
            else:
                assign(accept, I < thr)
