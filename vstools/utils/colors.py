from abc import abstractmethod
from math import sqrt
from typing import TYPE_CHECKING, Any, ClassVar

import vapoursynth as vs
from jetpytools import CustomIntEnum, FuncExceptT, KwargsT, inject_self, interleave_arr

from ..enums import Matrix, Primaries, Transfer
from ..enums.color import _norm_props_enums
from ..functions import check_variable_format, depth, plane, video_heuristics, video_resample_heuristics
from ..types import ConstantFormatVideoNode

__all__ = [
    'ResampleUtil',

    'ResampleRGBUtil', 'ResampleYUVUtil',

    'ResampleRGBMatrixUtil',

    'ResampleRGB', 'ResampleYUV', 'ResampleGRAY',

    'ResampleOPP', 'ResampleOPPLCC',

    'ResampleOPPBM3D', 'ResampleOPPBM3DS',

    'ResampleYCgCo', 'ResampleYCgCoR',

    'Colorspace'
]


class ResampleUtil:
    @inject_self
    def clip2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        """
        Convert any clip to the implemented colorspace.

        :param clip:    Clip to be processed.
        :param fp32:    Whether to process in original bitdepth (None) or in int16 (False) or float32 (True).
        :param func:    Function returned for custom error handling.
                        This should only be set by VS package developers.

        :return:        Converted clip.
        """

        func = func or self.clip2csp

        assert check_variable_format(clip, func)

        if clip.format.color_family is vs.RGB:
            return self.rgb2csp(clip, fp32, func, **kwargs)

        return self.yuv2csp(clip, fp32, func, **kwargs)

    @inject_self
    @abstractmethod
    def rgb2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        """
        Convert an RGB clip to the implemented colorspace.

        :param clip:    RGB clip to be processed.
        :param fp32:    Whether to process in original bitdepth (None) or in int16 (False) or float32 (True).
        :param func:    Function returned for custom error handling.
                        This should only be set by VS package developers.

        :return:        Converted clip.
        """

    @inject_self
    @abstractmethod
    def yuv2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        """
        Convert a YUV clip to the implemented colorspace.

        :param clip:    YUV clip to be processed.
        :param fp32:    Whether to process in original bitdepth (None) or in int16 (False) or float32 (True).
        :param func:    Function returned for custom error handling.
                        This should only be set by VS package developers.

        :return:        Converted clip.
        """

    @inject_self
    @abstractmethod
    def csp2rgb(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        ...

    @inject_self
    @abstractmethod
    def csp2yuv(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        ...


class ResampleRGBUtil(ResampleUtil):
    @inject_self
    def yuv2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.yuv2csp))

        conv_args = video_resample_heuristics(clip, kwargs, color_family=vs.RGB, subsampling_w=0, subsampling_h=0)

        return self.rgb2csp(clip.resize.Bicubic(**_norm_props_enums(conv_args)), fp32, func)

    @inject_self
    def csp2yuv(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.csp2yuv))

        rgb = self.csp2rgb(clip, fp32, func)

        conv_args = video_resample_heuristics(rgb, kwargs, color_family=vs.YUV)

        return rgb.resize.Bicubic(**_norm_props_enums(conv_args))


class ResampleYUVUtil(ResampleUtil):
    @inject_self
    def rgb2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.rgb2csp))

        conv_args = video_resample_heuristics(clip, kwargs, color_family=vs.YUV)

        return self.yuv2csp(clip.resize.Bicubic(**_norm_props_enums(conv_args)), fp32, func)

    @inject_self
    def csp2rgb(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.csp2yuv))

        yuv = self.csp2yuv(clip, fp32, func)

        conv_args = video_resample_heuristics(yuv, kwargs, color_family=vs.RGB, subsampling_w=0, subsampling_h=0)

        return yuv.resize.Bicubic(**_norm_props_enums(conv_args))


class ResampleRGBMatrixUtil(ResampleRGBUtil):
    matrix_rgb2csp: ClassVar[list[float]]
    matrix_csp2rgb: ClassVar[list[float]]

    @inject_self
    def rgb2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.rgb2csp))

        clip = clip.fmtc.matrix(
            fulls=True, fulld=True, col_fam=vs.YUV, coef=list(interleave_arr(self.matrix_rgb2csp, [0, 0, 0], 3))
        )

        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)

    @inject_self
    def csp2rgb(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        assert check_variable_format(clip, (func := func or self.csp2rgb))

        clip = clip.fmtc.matrix(
            fulls=True, fulld=True, col_fam=vs.RGB, coef=list(interleave_arr(self.matrix_csp2rgb, [0, 0, 0], 3))
        )

        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)


class ResampleRGB(ResampleRGBUtil):
    @inject_self
    def rgb2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)

    @inject_self
    def csp2rgb(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)


class ResampleYUV(ResampleYUVUtil):
    @inject_self
    def yuv2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)

    @inject_self
    def csp2yuv(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)


class ResampleGRAY(ResampleYUV):
    @inject_self
    def yuv2csp(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:

        assert clip.format

        if fp32 is None or (32 if fp32 else 16) == clip.format.bits_per_sample:
            return plane(clip, 0)

        return clip.resize.Point(format=vs.GRAYS if fp32 else vs.GRAY16)

    @inject_self
    def csp2yuv(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        return clip if fp32 is None else depth(clip, 32 if fp32 else 16)


class ResampleOPP(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 3, 1 / 3, 1 / 3,
        0, 1 / sqrt(6), -1 / sqrt(6),
        -sqrt(2) / 3, 1 / (3 * sqrt(2)), 1 / (3 * sqrt(2))
    ]
    matrix_csp2rgb = [
        1, 0, -sqrt(2),
        1, sqrt(3 / 2), 1 / sqrt(2),
        1, -sqrt(3 / 2), 1 / sqrt(2)
    ]


class ResampleOPPLCC(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 3, 1 / 3, 1 / 3,
        1 / sqrt(6), 0, -1 / sqrt(6),
        1 / (3 * sqrt(2)), sqrt(2) / -3, 1 / (3 * sqrt(2))
    ]
    matrix_csp2rgb = [
        1, sqrt(3 / 2), 1 / sqrt(2),
        1, 0, -sqrt(2),
        1, -sqrt(3 / 2), 1 / sqrt(2)
    ]


class ResampleOPPBM3D(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 3, 1 / 3, 1 / 3,
        1 / 2, 0, -1 / 2,
        1 / 4, -1 / 2, 1 / 4
    ]
    matrix_csp2rgb = [
        1, 1, 2 / 3,
        1, 0, -4 / 3,
        1, -1, 2 / 3
    ]


class ResampleOPPBM3DS(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 3, 1 / 3, 1 / 3,
        0, 1 / 2, -1 / 2,
        -1 / 2, 1 / 4, 1 / 4
    ]
    matrix_csp2rgb = [
        1, 0, -4 / 3,
        1, 1, 2 / 3,
        1, -1, 2 / 3
    ]


class ResampleYCgCo(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 4, 1 / 2, 1 / 4,
        1 / 2, 0, -1 / 2,
        -1 / 4, 1 / 2, -1 / 4
    ]
    matrix_csp2rgb = [
        1, 1, -1,
        1, 0, 1,
        1, -1, -1
    ]


class ResampleYCgCoR(ResampleRGBMatrixUtil):
    matrix_rgb2csp = [
        1 / 4, 1 / 2, 1 / 4,
        1, 0, -1,
        -1 / 2, 1, -1 / 2
    ]
    matrix_csp2rgb = [
        1, 1 / 2, -1 / 2,
        1, 0, 1 / 2,
        1, -1 / 2, -1 / 2
    ]


class Colorspace(CustomIntEnum):
    GRAY = 0
    YUV = 1
    RGB = 2
    YCgCo = 3
    YCgCoR = 4
    OPP = 5
    OPP_LCC = 6
    OPP_BM3D = 7
    OPP_BM3DS = 8

    if TYPE_CHECKING:
        class to:
            @staticmethod
            def GRAY(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def YUV(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def RGB(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def YCgCo(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def YCgCoR(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def OPP(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def OPP_LCC(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def OPP_BM3D(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...

            @staticmethod
            def OPP_BM3DS(
                clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
            ) -> vs.VideoNode:
                ...
    else:
        @property
        def to(self):
            class to(CustomIntEnum):
                GRAY = 0
                YUV = 1
                RGB = 2
                YCgCo = 3
                YCgCoR = 4
                OPP = 5
                OPP_LCC = 6
                OPP_BM3D = 7
                OPP_BM3DS = 8

                def __call__(
                    self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
                ) -> vs.VideoNode:
                    if self._from.value == self:
                        return clip

                    to_csp = Colorspace.from_param(self)
                    assert to_csp

                    if not to_csp.is_rgb and not self._from.is_rgb:
                        kwargs.setdefault('matrix', Matrix.from_video(clip))
                        kwargs.setdefault('transfer', Transfer.from_video(clip))
                        kwargs.setdefault('primaries', Primaries.from_video(clip))

                    return to_csp.from_clip(self._from.to_rgb(clip, fp32, func), fp32, func, **kwargs)

            to._from = self

            return to

    @property
    def is_opp(self) -> bool:
        return 'OPP' in self.name

    @property
    def is_rgb(self) -> bool:
        return 'RGB' in self.name

    @property
    def is_yuv(self) -> bool:
        return 'YUV' in self.name

    @property
    def resampler(self) -> type[ResampleUtil]:
        if self is self.YCgCo:
            return ResampleYCgCo
        elif self is self.YCgCoR:
            return ResampleYCgCoR
        elif self is self.OPP:
            return ResampleOPP
        elif self is self.OPP_LCC:
            return ResampleOPPLCC
        elif self is self.OPP_BM3D:
            return ResampleOPPBM3D
        elif self is self.OPP_BM3DS:
            return ResampleOPPBM3DS
        elif self is self.GRAY:
            return ResampleGRAY
        elif self is self.YUV:
            return ResampleYUV
        elif self is self.RGB:
            return ResampleRGB

        raise NotImplementedError

    def _kw_from_props(
        self, clip: ConstantFormatVideoNode, props: vs.VideoNode, func: FuncExceptT, **kwargs: Any
    ) -> KwargsT:
        assert check_variable_format(props, func)

        h_kwargs = video_heuristics(
            props, True, clip.format.color_family != props.format.color_family, False
        )

        for k, v in list(kwargs.items()):
            if k in h_kwargs and v is None:
                kwargs.pop(k)

        kwargs |= h_kwargs

        if 'format' not in kwargs:
            kwargs |= KwargsT(format=props.format.id)

        return kwargs

    def __call__(self, clip: vs.VideoNode, **kwargs: Any) -> vs.VideoNode:
        assert check_variable_format(clip, self.from_clip)

        return self.resampler.clip2csp(clip, **kwargs)

    def from_clip(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        func = func or self.from_clip

        assert check_variable_format(clip, func)

        return self.resampler.clip2csp(clip, fp32, func, **kwargs)

    def to_rgb(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None,
        props: vs.VideoNode | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        func = func or self.to_rgb

        assert check_variable_format(clip, func)

        if props:
            kwargs = self._kw_from_props(clip, props, func, **kwargs)

        return self.resampler.csp2rgb(clip, fp32, func, **kwargs)

    def to_yuv(
        self, clip: vs.VideoNode, fp32: bool | None = None, func: FuncExceptT | None = None,
        props: vs.VideoNode | None = None, **kwargs: Any
    ) -> vs.VideoNode:
        func = func or self.to_yuv

        assert check_variable_format(clip, func)

        if props:
            kwargs = self._kw_from_props(clip, props, func, **kwargs)

        return self.resampler.csp2yuv(clip, fp32, func, **kwargs)
