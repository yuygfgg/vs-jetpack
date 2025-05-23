from __future__ import annotations

from enum import auto
from math import ceil, exp, log2, pi, sqrt
from typing import Any, Iterable, Literal, Sequence, TypeVar, overload

from jetpytools import CustomEnum, CustomNotImplementedError
from typing_extensions import Self

from vsexprtools import ExprList, ExprOp, ExprToken, ExprVars
from vstools import (
    ConstantFormatVideoNode, ConvMode, CustomIntEnum, CustomStrEnum, CustomValueError, KwargsT, PlanesT, check_variable,
    core, fallback, iterate, shift_clip_multi, vs
)

__all__ = [
    'LimitFilterMode',
    'RemoveGrainMode', 'RemoveGrainModeT',
    'RepairMode', 'RepairModeT',
    'VerticalCleanerMode', 'VerticalCleanerModeT',
    'ClenseMode', 'ClenseModeT',
    'BlurMatrixBase', 'BlurMatrix', 'BilateralBackend'
]


class LimitFilterModeMeta:
    force_expr = True


class LimitFilterMode(LimitFilterModeMeta, CustomIntEnum):
    """Two sources, one filtered"""
    SIMPLE_MIN = auto()
    SIMPLE_MAX = auto()
    """One source, two filtered"""
    SIMPLE2_MIN = auto()
    SIMPLE2_MAX = auto()
    DIFF_MIN = auto()
    DIFF_MAX = auto()
    """One/Two sources, one filtered"""
    CLAMPING = auto()

    @property
    def op(self) -> str:
        return '<' if 'MIN' in self._name_ else '>'

    def __call__(self, force_expr: bool = True) -> Self:
        self.force_expr = force_expr

        return self


class RemoveGrainMode(CustomIntEnum):
    NONE = 0
    MINMAX_AROUND1 = 1
    MINMAX_AROUND2 = 2
    MINMAX_AROUND3 = 3
    MINMAX_MEDIAN = 4
    EDGE_CLIP_STRONG = 5
    EDGE_CLIP_MODERATE = 6
    EDGE_CLIP_MEDIUM = 7
    EDGE_CLIP_LIGHT = 8
    LINE_CLIP_CLOSE = 9
    MIN_SHARP = 10
    BINOMIAL_BLUR = 11
    BOB_TOP_CLOSE = 13
    BOB_BOTTOM_CLOSE = 14
    BOB_TOP_INTER = 15
    BOB_BOTTOM_INTER = 16
    MINMAX_MEDIAN_OPP = 17
    LINE_CLIP_OPP = 18
    MEAN_NO_CENTER = 19
    MEAN = 20
    BOX_BLUR_NO_CENTER = MEAN_NO_CENTER
    BOX_BLUR = MEAN
    OPP_CLIP_AVG = 21
    OPP_CLIP_AVG_FAST = 22
    EDGE_DEHALO = 23
    EDGE_DEHALO2 = 24
    SMART_RGC = 26
    SMART_RGCL = 27
    SMART_RGCL2 = 28

    def __call__(self, clip: vs.VideoNode, planes: PlanesT = None) -> ConstantFormatVideoNode:
        from .rgtools import remove_grain
        from .util import norm_rmode_planes
        return remove_grain(clip, norm_rmode_planes(clip, self, planes))


RemoveGrainModeT = int | RemoveGrainMode | Sequence[int | RemoveGrainMode]


class RepairMode(CustomIntEnum):
    NONE = 0
    MINMAX_SQUARE1 = 1
    MINMAX_SQUARE2 = 2
    MINMAX_SQUARE3 = 3
    MINMAX_SQUARE4 = 4
    LINE_CLIP_MIN = 5
    LINE_CLIP_LIGHT = 6
    LINE_CLIP_MEDIUM = 7
    LINE_CLIP_STRONG = 8
    LINE_CLIP_CLOSE = 9
    MINMAX_SQUARE_REF_CLOSE = 10
    MINMAX_SQUARE_REF1 = 11
    MINMAX_SQUARE_REF2 = 12
    MINMAX_SQUARE_REF3 = 13
    MINMAX_SQUARE_REF4 = 14
    CLIP_REF_RG5 = 15
    CLIP_REF_RG6 = 16
    CLIP_REF_RG17 = 17
    CLIP_REF_RG18 = 18
    CLIP_REF_RG19 = 19
    CLIP_REF_RG20 = 20
    CLIP_REF_RG21 = 21
    CLIP_REF_RG22 = 22
    CLIP_REF_RG23 = 23
    CLIP_REF_RG24 = 24
    CLIP_REF_RG26 = 26
    CLIP_REF_RG27 = 27
    CLIP_REF_RG28 = 28

    def __call__(self, clip: vs.VideoNode, repairclip: vs.VideoNode, planes: PlanesT = None) -> ConstantFormatVideoNode:
        from .rgtools import repair
        from .util import norm_rmode_planes
        return repair(clip, repairclip, norm_rmode_planes(clip, self, planes))


RepairModeT = int | RepairMode | Sequence[int | RepairMode]


class VerticalCleanerMode(CustomIntEnum):
    NONE = 0
    MEDIAN = 1
    PRESERVING = 2

    def __call__(self, clip: vs.VideoNode, planes: PlanesT = None) -> ConstantFormatVideoNode:
        from .rgtools import vertical_cleaner
        from .util import norm_rmode_planes
        return vertical_cleaner(clip, norm_rmode_planes(clip, self, planes))


VerticalCleanerModeT = int | VerticalCleanerMode | Sequence[int | VerticalCleanerMode]


class ClenseMode(CustomStrEnum):
    NONE = ''
    BACKWARD = 'BackwardClense'
    FORWARD = 'ForwardClense'
    BOTH = 'Clense'

    def __call__(
        self,
        clip: vs.VideoNode,
        previous_clip: vs.VideoNode | None = None,
        next_clip: vs.VideoNode | None = None,
        planes: PlanesT = None
    ) -> ConstantFormatVideoNode:
        from .rgtools import clense
        return clense(clip, previous_clip, next_clip, self, planes)


ClenseModeT = str | ClenseMode

_Nb = TypeVar('_Nb', bound=float | int)


class BlurMatrixBase(list[_Nb]):
    def __init__(
        self, __iterable: Iterable[_Nb], /, mode: ConvMode = ConvMode.SQUARE,
    ) -> None:
        self.mode = mode
        super().__init__(__iterable)

    def __call__(
        self, clip: vs.VideoNode, planes: PlanesT = None,
        bias: float | None = None, divisor: float | None = None, saturate: bool = True,
        passes: int = 1, expr_kwargs: KwargsT | None = None, **conv_kwargs: Any
    ) -> ConstantFormatVideoNode:
        """
        Performs a spatial or temporal convolution.
        It will either calls std.Convolution, std.AverageFrames or ExprOp.convolution
        based on the ConvMode mode picked.

        :param clip:            Clip to process.
        :param planes:          Specifies which planes will be processed.
        :param bias:            Value to add to the final result of the convolution
                                (before clamping the result to the format's range of valid values).
        :param divisor:         Divide the output of the convolution by this value (before adding bias).
                                The default is the sum of the elements of the matrix
        :param saturate:        If True, negative values become 0.
                                If False, absolute values are returned.
        :param passes:          Number of iterations.
        :param expr_kwargs:     A KwargsT of keyword arguments for ExprOp.convolution.__call__ when it is picked.
        :param **conv_kwargs:   Additional keyword arguments for std.Convolution, std.AverageFrames or ExprOp.convolution.

        :return:                Processed clip.
        """
        assert check_variable(clip, self)

        if len(self) <= 1:
            return clip

        expr_kwargs = expr_kwargs or KwargsT()

        fp16 = clip.format.sample_type == vs.FLOAT and clip.format.bits_per_sample == 16

        if self.mode.is_spatial:
            # std.Convolution is limited to 25 numbers
            # SQUARE mode is not optimized
            # std.Convolution doesn't support float 16
            if len(self) <= 25 and self.mode != ConvMode.SQUARE and not fp16:
                return iterate(clip, core.std.Convolution, passes, self, bias, divisor, planes, saturate, self.mode)

            return iterate(
                clip, ExprOp.convolution("x", self, bias, fallback(divisor, True), saturate, self.mode, **conv_kwargs),
                passes, planes=planes, **expr_kwargs
            )

        if all([
            not fp16,
            len(self) <= 31,
            not bias,
            saturate,
            (len(conv_kwargs) == 0 or (len(conv_kwargs) == 1 and "scenechange" in conv_kwargs))
        ]):
            return iterate(clip, core.std.AverageFrames, passes, self, divisor, planes=planes, **conv_kwargs)

        return self._averageframes_akarin(clip, planes, bias, divisor, saturate, passes, expr_kwargs, **conv_kwargs)

    def _averageframes_akarin(self, *args: Any, **kwargs: Any) -> ConstantFormatVideoNode:
        clip, planes, bias, divisor, saturate, passes, expr_kwargs = args
        conv_kwargs = kwargs

        r = len(self) // 2

        if conv_kwargs.pop("scenechange", False) is False:
            expr_conv = ExprOp.convolution(
                ExprVars(len(self)), self, bias, fallback(divisor, True), saturate, self.mode, **conv_kwargs
            )
            return iterate(
                clip, lambda x: expr_conv(shift_clip_multi(x, (-r, r)), planes=planes, **expr_kwargs), passes
            ).std.CopyFrameProps(clip)

        expr = ExprList()

        vars_ = [[f"{v}"] for v in ExprOp.matrix(ExprVars(len(self), akarin=True), r, self.mode)[0]]

        back_vars = vars_[:r]

        # Constructing the expression for backward (previous) clips.
        # Each clip is weighted by its corresponding weight and multiplied by the logical NOT
        # of all `_SceneChangeNext` properties from the current and subsequent clips.
        # This ensures that the expression excludes frames that follow detected scene changes.
        for i, (var, weight) in enumerate(zip(back_vars, self[:r])):
            expr.append(
                var, weight, ExprOp.MUL,
                [[f"{back_vars[ii][0]}._SceneChangeNext", ExprOp.NOT, ExprOp.MUL]
                 for ii in range(i, len(back_vars))],
                ExprOp.DUP, f"cond{i}!"
            )

        forw_vars = vars_[r + 1:]
        forw_vars.reverse()

        # Same thing for forward (next) clips.
        for j, (var, weight) in enumerate(zip(forw_vars, reversed(self[r + 1:]))):
            expr.append(
                var, weight, ExprOp.MUL,
                [[f"{forw_vars[jj][0]}._SceneChangePrev", ExprOp.NOT, ExprOp.MUL]
                 for jj in range(j, len(forw_vars))],
                ExprOp.DUP, f"cond{len(vars_) - j - 1}!"
            )

        # If a scene change is detected, all the weights beyond it are applied
        # to the center frame.
        expr.append(vars_[r], self[r])

        for k, w in enumerate(self[:r] + ([None] + self[r + 1:])):
            if w is not None:
                expr.append(f"cond{k}@", 0, w, ExprOp.TERN)

        expr.append(ExprOp.ADD * r * 2, ExprOp.MUL, ExprOp.ADD * r * 2)

        if (premultiply := conv_kwargs.get("premultiply", None)):
            expr.append(premultiply, ExprOp.MUL)

        if divisor:
            expr.append(divisor, ExprOp.DIV)
        else:
            expr.append(sum(self), ExprOp.DIV)

        if bias:
            expr.append(bias, ExprOp.ADD)

        if not saturate:
            expr.append(ExprOp.ABS)

        if (multiply := conv_kwargs.get("multiply", None)):
            expr.append(multiply, ExprOp.MUL)

        if conv_kwargs.get("clamp", False):
            expr.append(ExprOp.clamp(ExprToken.RangeMin, ExprToken.RangeMax))

        return iterate(
            clip, lambda x: expr(shift_clip_multi(x, (-r, r)), planes=planes, **expr_kwargs), passes
        ).std.CopyFrameProps(clip)

    def outer(self) -> Self:
        from numpy import outer

        return self.__class__(list[_Nb](outer(self, self).flatten()), self.mode)  #pyright: ignore[reportArgumentType]



class BlurMatrix(CustomEnum):
    MEAN_NO_CENTER = auto()
    MEAN = auto()
    BOX_BLUR_NO_CENTER = MEAN_NO_CENTER
    CIRCLE = MEAN_NO_CENTER  # TODO: remove
    BOX_BLUR = MEAN
    BINOMIAL = auto()
    LOG = auto()
    GAUSS = auto()

    @overload
    def __call__(  # type: ignore[misc]
        self: Literal[BlurMatrix.MEAN_NO_CENTER], taps: int = 1, *, mode: ConvMode = ConvMode.SQUARE
    ) -> BlurMatrixBase[int]:
        ...

    @overload
    def __call__(  # type: ignore[misc]
        self: Literal[BlurMatrix.MEAN], taps: int = 1, *, mode: ConvMode = ConvMode.SQUARE
    ) -> BlurMatrixBase[int]:
        ...

    @overload
    def __call__(  # type: ignore[misc]
        self: Literal[BlurMatrix.BINOMIAL], taps: int = 1, *, mode: ConvMode = ConvMode.HV
    ) -> BlurMatrixBase[int]:
        ...

    @overload
    def __call__(  # type: ignore[misc]
        self: Literal[BlurMatrix.LOG], taps: int = 1, *, strength: float = 100.0, mode: ConvMode = ConvMode.HV
    ) -> BlurMatrixBase[float]:
        ...

    @overload
    def __call__(  # type: ignore[misc]
        self: Literal[BlurMatrix.GAUSS], taps: int | None = None, *, sigma: float = 0.5, mode: ConvMode = ConvMode.HV,
        **kwargs: Any
    ) -> BlurMatrixBase[float]:
        ...

    @overload
    def __call__(self, taps: int | None = None, **kwargs: Any) -> Any:
        ...

    def __call__(self, taps: int | None = None, **kwargs: Any) -> Any:
        kernel: BlurMatrixBase[Any]

        match self:
            case BlurMatrix.MEAN_NO_CENTER:
                taps = fallback(taps, 1)
                mode = kwargs.pop("mode", ConvMode.SQUARE)

                matrix = [1 for _ in range(((2 * taps + 1) ** (2 if mode == ConvMode.SQUARE else 1)) - 1)]
                matrix.insert(len(matrix) // 2, 0)

                return BlurMatrixBase[int](matrix, mode)

            case BlurMatrix.MEAN:
                taps = fallback(taps, 1)
                mode = kwargs.pop("mode", ConvMode.SQUARE)

                kernel = BlurMatrixBase[int]([1 for _ in range(((2 * taps + 1)))], mode)

            case BlurMatrix.BINOMIAL:
                taps = fallback(taps, 1)
                mode = kwargs.pop("mode", ConvMode.HV)

                c = 1
                n = taps * 2 + 1

                matrix = list[int]()

                for i in range(1, taps + 2):
                    matrix.append(c)
                    c = c * (n - i) // i

                kernel = BlurMatrixBase(matrix[:-1] + matrix[::-1], mode)

            case BlurMatrix.LOG:
                taps = fallback(taps, 1)
                strength = kwargs.pop("strength", 100)
                mode = kwargs.pop("mode", ConvMode.HV)

                strength = max(1e-6, min(log2(3) * strength / 100, log2(3)))

                weight = 0.5 ** strength / ((1 - 0.5 ** strength) * 0.5)

                matrixf = [1.0]

                for _ in range(taps):
                    matrixf.append(matrixf[-1] / weight)

                kernel = BlurMatrixBase([*matrixf[::-1], *matrixf[1:]], mode)

            case BlurMatrix.GAUSS:
                taps = fallback(taps, 1)
                sigma = kwargs.pop("sigma", 0.5)
                mode = kwargs.pop("mode", ConvMode.HV)
                scale_value = kwargs.pop("scale_value", 1023)

                if mode == ConvMode.SQUARE:
                    scale_value = sqrt(scale_value)

                taps = self.get_taps(sigma, taps)

                if taps < 0:
                    raise CustomValueError('Taps must be >= 0!')

                if sigma > 0.0:
                    half_pisqrt = 1.0 / sqrt(2.0 * pi) * sigma
                    doub_qsigma = 2 * sigma ** 2

                    high, *mat = [half_pisqrt * exp(-x ** 2 / doub_qsigma) for x in range(taps + 1)]

                    mat = [x * scale_value / high for x in mat]
                    mat = [*mat[::-1], scale_value, *mat]
                else:
                    mat = [scale_value]

                kernel = BlurMatrixBase(mat, mode)

            case _:
                raise CustomNotImplementedError("Unsupported blur matrix enum!", self, self)

        if mode == ConvMode.SQUARE:
            kernel = kernel.outer()

        return kernel

    def from_radius(self: Literal[BlurMatrix.GAUSS], radius: int) -> BlurMatrixBase[float]:  # type: ignore[misc]
        assert self is BlurMatrix.GAUSS

        return BlurMatrix.GAUSS(None, sigma=(radius + 1.0) / 3)

    def get_taps(self: Literal[BlurMatrix.GAUSS], sigma: float, taps: int | None = None) -> int:  # type: ignore[misc]
        assert self is BlurMatrix.GAUSS

        if taps is None:
            taps = ceil(abs(sigma) * 8 + 1) // 2

        return taps


class BilateralBackend(CustomStrEnum):
    CPU = 'vszip'
    GPU = 'bilateralgpu'
    GPU_RTC = 'bilateralgpu_rtc'
