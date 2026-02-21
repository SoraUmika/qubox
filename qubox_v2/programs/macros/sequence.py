from qm.qua import *
from .measure_macro import measureMacro
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
        qb_el="qubit",
        x90="x90",
        yn90="yn90",
        qb_probe_if=None,
        selective_pulse: str = None,
        selective_freq: int = None,
        wait_after: bool = False,
        wait_after_clks=None,
    ):
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
        qb_el="qubit",
        st_el="storage",
        sel_r180="sel_x180",
    ):
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
        *, qb_el="qubit", st_el="storage", sel_r180="sel_x180"
    ):
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
        policy: str | None = None,         # "ZSCORE", "AFFINE", "HYSTERESIS", "BLOBS", or None
        r180: str = "x180",
        qb_el: str = "qubit",
        max_trials: int = 4,
        targets: list | None = None,
        state=None,
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
            Name of the Ï€ pulse used for conditional resets.
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
                    If provided, overrides measureMacro._threshold for this call.

            - policy == "ZSCORE":
                mu_g, sigma_g, mu_e, sigma_e, k=2.5

            - policy == "AFFINE":
                a, b, c, margin=0.0

            - policy == "HYSTERESIS":
                T_low, T_high   (default to threshold if omitted)

            - policy == "BLOBS":
                Ig, Qg, rg, Ie, Qe, re, require_exclusive=True
        """

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
            # Conditional Ï€ to move toward target_state
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
        thr = float(kwargs.get("threshold", getattr(measureMacro, "_threshold", 0.0)))

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

        # ---- DEFAULT scalar threshold on I ----
        else:
            if ts == "e":
                assign(accept, I > thr)
            else:
                assign(accept, I < thr)
