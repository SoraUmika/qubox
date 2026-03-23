# qubox_v2/compile/templates.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from .param_space import ParamBlock


class GateTemplate:
    """
    A template contributes parameters (ParamBlock(s)) and builds GateModel(s)
    from the corresponding slice of x.
    """
    def param_blocks(self) -> List[ParamBlock]:
        raise NotImplementedError

    def build(self, x_slice: np.ndarray, *, ctx: Any, n_max: int) -> List[Any]:
        raise NotImplementedError


class DisplacementTemplate(GateTemplate):
    def __init__(
        self,
        *,
        name: str,
        alpha_max: float = 2.0,
        duration_override_s: Optional[float] = None,
        freeze_re: Optional[float] = None,
        freeze_im: Optional[float] = None,
    ):
        self.name = str(name)
        self.alpha_max = float(alpha_max)
        self.duration_override_s = duration_override_s
        self.freeze_re = freeze_re
        self.freeze_im = freeze_im

    def param_blocks(self) -> List[ParamBlock]:
        fixed = [self.freeze_re, self.freeze_im]
        return [
            ParamBlock(
                name=self.name,
                size=2,
                bounds=[(-self.alpha_max, self.alpha_max), (-self.alpha_max, self.alpha_max)],
                names=["alpha_re", "alpha_im"],
                fixed=fixed,
            )
        ]

    def build(self, x_slice: np.ndarray, *, ctx: Any, n_max: int) -> List[Any]:
        try:
            from qubox.gates.models import DisplacementModel
        except Exception as e:
            raise ImportError("DisplacementTemplate requires qubox.gates.models.DisplacementModel") from e

        a_re, a_im = float(x_slice[0]), float(x_slice[1])
        alpha = complex(a_re, a_im)
        return [DisplacementModel(alpha=alpha, duration_override_s=self.duration_override_s)]


class SQRTemplate(GateTemplate):
    def __init__(
        self,
        *,
        name: str,
        n_max: int,
        n_active: Optional[int] = None,
        theta_max: float = np.pi,
        duration_override_s: Optional[float] = None,
        freeze_thetas: Optional[Dict[int, float]] = None,
        freeze_phis: Optional[Dict[int, float]] = None,
    ):
        """
        - n_active: optimize only indices n=0..n_active; others fixed to 0.
        - freeze_thetas/phis: dict mapping n -> fixed value (only applied if n <= n_active)
        """
        self.name = str(name)
        self.n_max = int(n_max)
        self.n_levels = self.n_max + 1
        self.n_active = self.n_max if n_active is None else int(n_active)
        if self.n_active < 0 or self.n_active > self.n_max:
            raise ValueError("n_active must be in [0, n_max]")
        self.theta_max = float(theta_max)
        self.duration_override_s = duration_override_s
        self.freeze_thetas = dict(freeze_thetas or {})
        self.freeze_phis = dict(freeze_phis or {})

    def param_blocks(self) -> List[ParamBlock]:
        na = self.n_active

        theta_fixed: List[Optional[float]] = [None] * (na + 1)
        phi_fixed: List[Optional[float]] = [None] * (na + 1)

        for n, v in self.freeze_thetas.items():
            if 0 <= n <= na:
                theta_fixed[n] = float(v)
        for n, v in self.freeze_phis.items():
            if 0 <= n <= na:
                phi_fixed[n] = float(v)

        b_theta = [(-self.theta_max, self.theta_max)] * (na + 1)
        b_phi = [(-np.pi, np.pi)] * (na + 1)

        return [
            ParamBlock(
                name=f"{self.name}.thetas",
                size=(na + 1),
                bounds=b_theta,
                names=[f"th[{n}]" for n in range(na + 1)],
                fixed=theta_fixed,
            ),
            ParamBlock(
                name=f"{self.name}.phis",
                size=(na + 1),
                bounds=b_phi,
                names=[f"ph[{n}]" for n in range(na + 1)],
                fixed=phi_fixed,
            ),
        ]

    def build(self, x_slice: np.ndarray, *, ctx: Any, n_max: int) -> List[Any]:
        if int(n_max) != self.n_max:
            raise ValueError(f"{self.name}: template n_max={self.n_max} but build called with n_max={n_max}")

        try:
            from qubox.gates.models import SQRModel
        except Exception as e:
            raise ImportError("SQRTemplate requires qubox.gates.models.SQRModel") from e

        na = self.n_active
        nL = self.n_levels
        zeros = np.zeros(nL, dtype=float)

        if x_slice.size != 2 * (na + 1):
            raise ValueError(f"{self.name}: expected slice of size {2*(na+1)}, got {x_slice.size}")

        thetas = np.zeros(nL, dtype=float)
        phis = np.zeros(nL, dtype=float)

        thetas[: na + 1] = x_slice[: na + 1]
        phis[: na + 1] = x_slice[na + 1 : 2 * (na + 1)]

        return [
            SQRModel(
                thetas=thetas,
                phis=phis,
                d_lambda=zeros,
                d_alpha=zeros,
                d_omega=zeros,
                duration_override_s=self.duration_override_s,
            )
        ]


class QubitRotationTemplate(GateTemplate):
    def __init__(
        self,
        *,
        name: str,
        theta_max: float = np.pi,
        duration_override_s: Optional[float] = None,
        freeze_theta: Optional[float] = None,
        freeze_phi: Optional[float] = None,
    ):
        self.name = str(name)
        self.theta_max = float(theta_max)
        self.duration_override_s = duration_override_s
        self.freeze_theta = freeze_theta
        self.freeze_phi = freeze_phi

    def param_blocks(self) -> List[ParamBlock]:
        return [
            ParamBlock(
                name=self.name,
                size=2,
                bounds=[(-self.theta_max, self.theta_max), (-np.pi, np.pi)],
                names=["theta", "phi"],
                fixed=[self.freeze_theta, self.freeze_phi],
            )
        ]

    def build(self, x_slice: np.ndarray, *, ctx: Any, n_max: int) -> List[Any]:
        try:
            from qubox.gates.models import QubitRotationModel
        except Exception as e:
            raise ImportError("QubitRotationTemplate requires qubox.gates.models.QubitRotationModel") from e

        theta, phi = float(x_slice[0]), float(x_slice[1])
        return [QubitRotationModel(theta=theta, phi=phi, duration_override_s=self.duration_override_s)]


class SNAPTemplate(GateTemplate):
    def __init__(
        self,
        *,
        name: str,
        n_max: int,
        n_active: Optional[int] = None,
        angle_max: float = np.pi,
        freeze_angles: Optional[Dict[int, float]] = None,
    ):
        """
        SNAPModel has angles[n] giving phase on |e,n>.
        """
        self.name = str(name)
        self.n_max = int(n_max)
        self.n_levels = self.n_max + 1
        self.n_active = self.n_max if n_active is None else int(n_active)
        if self.n_active < 0 or self.n_active > self.n_max:
            raise ValueError("n_active must be in [0, n_max]")
        self.angle_max = float(angle_max)
        self.freeze_angles = dict(freeze_angles or {})

    def param_blocks(self) -> List[ParamBlock]:
        na = self.n_active
        fixed: List[Optional[float]] = [None] * (na + 1)
        for n, v in self.freeze_angles.items():
            if 0 <= n <= na:
                fixed[n] = float(v)

        b = [(-self.angle_max, self.angle_max)] * (na + 1)
        return [
            ParamBlock(
                name=f"{self.name}.angles",
                size=(na + 1),
                bounds=b,
                names=[f"ang[{n}]" for n in range(na + 1)],
                fixed=fixed,
            )
        ]

    def build(self, x_slice: np.ndarray, *, ctx: Any, n_max: int) -> List[Any]:
        if int(n_max) != self.n_max:
            raise ValueError(f"{self.name}: template n_max={self.n_max} but build called with n_max={n_max}")

        try:
            from qubox.gates.models import SNAPModel
        except Exception as e:
            raise ImportError("SNAPTemplate requires qubox.gates.models.SNAPModel") from e

        na = self.n_active
        nL = self.n_levels

        angles = np.zeros(nL, dtype=float)
        angles[: na + 1] = x_slice[: na + 1]
        return [SNAPModel(angles=angles)]

