
import math
from abc import ABC, abstractmethod
from typing import Any, ClassVar, List, Optional, Sequence, Set, Tuple, Type

import vapoursynth as vs
from vsutil import Range, depth, join, split

from .util import max_expr, pick_px_op

core = vs.core


class EdgeDetect(ABC):
    """Abstract edge detection interface."""
    _bits: int

    def get_mask(self, clip: vs.VideoNode,
                 lthr: float = 0.0, hthr: Optional[float] = None, multi: float = 1.0) -> vs.VideoNode:
        """
        Makes edge mask based on convolution kernel.
        he resulting mask can be thresholded with lthr, hthr and multiplied with multi.

        :param clip:            Source clip
        :param lthr:            Low threshold. Anything below lthr will be set to 0
        :param hthr:            High threshold. Anything above hthr will be set to the range max
        :param multi:           Multiply all pixels by this before thresholding

        :return:                Mask clip
        """
        if clip.format is None:
            raise ValueError('get_mask: Variable format not allowed!')

        self._bits = clip.format.bits_per_sample
        is_float = clip.format.sample_type == vs.FLOAT
        peak = 1.0 if is_float else (1 << self._bits) - 1
        hthr = peak if hthr is None else hthr

        clip_p = self._preprocess(clip)
        mask = self._compute_mask(clip_p)
        mask = self._postprocess(mask)

        if multi != 1:
            mask = pick_px_op(
                use_expr=is_float,
                expr=f'x {multi} *',
                lut=lambda x: round(max(min(x * multi, peak), 0))
            )(mask)

        if lthr > 0 or hthr < peak:
            mask = pick_px_op(
                use_expr=is_float,
                expr=f'x {hthr} > {peak} x {lthr} <= 0 x ? ?',
                lut=lambda x: peak if x > hthr else 0 if x <= lthr else x
            )(mask)

        return mask

    @abstractmethod
    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        raise NotImplementedError

    def _preprocess(self, clip: vs.VideoNode) -> vs.VideoNode:
        return clip

    def _postprocess(self, clip: vs.VideoNode) -> vs.VideoNode:
        return clip


class MatrixEdgeDetect(EdgeDetect, ABC):
    matrices: ClassVar[Sequence[Sequence[float]]]
    divisors: ClassVar[Optional[Sequence[float]]] = None
    mode_types: ClassVar[Optional[Sequence[str]]] = None

    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        return self._merge([
            clip.std.Convolution(matrix=mat, divisor=div, saturate=False, mode=mode)
            for mat, div, mode in zip(self._get_matrices(), self._get_divisors(), self._get_mode_types())
        ])

    @abstractmethod
    def _merge(self, clips: Sequence[vs.VideoNode]) -> vs.VideoNode:
        raise NotImplementedError

    def _get_matrices(self) -> Sequence[Sequence[float]]:
        return self.matrices

    def _get_divisors(self) -> Sequence[float]:
        return self.divisors if self.divisors else [0.0] * len(self._get_matrices())

    def _get_mode_types(self) -> Sequence[str]:
        return self.mode_types if self.mode_types else ['s'] * len(self._get_matrices())

    def _postprocess(self, clip: vs.VideoNode) -> vs.VideoNode:
        if len(self.matrices[0]) > 9:
            clip = clip.std.Crop(
                right=clip.format.subsampling_w * 2 if clip.format and clip.format.subsampling_w != 0 else 2
            ).resize.Point(clip.width, src_width=clip.width)
        return clip


class SingleMatrixDetect(MatrixEdgeDetect):
    def _merge(self, clips: Sequence[vs.VideoNode]) -> vs.VideoNode:
        return clips[0]


class EuclidianDistanceMatrixDetect(MatrixEdgeDetect):
    def _merge(self, clips: Sequence[vs.VideoNode]) -> vs.VideoNode:
        return core.std.Expr(clips, 'x x * y y * + sqrt')


class MaxDetect(MatrixEdgeDetect):
    def _merge(self, clips: Sequence[vs.VideoNode]) -> vs.VideoNode:
        return core.std.Expr(clips, max_expr(len(clips)))


class Laplacian1(SingleMatrixDetect):
    """Pierre-Simon de Laplace operator 1st implementation. 3x3 matrix."""
    matrices = [[0, -1, 0, -1, 4, -1, 0, -1, 0]]


class Laplacian2(SingleMatrixDetect):
    """Pierre-Simon de Laplace operator 2nd implementation. 3x3 matrix."""
    matrices = [[1, -2, 1, -2, 4, -2, 1, -2, 1]]


class Laplacian3(SingleMatrixDetect):
    """Pierre-Simon de Laplace operator 3rd implementation. 3x3 matrix."""
    matrices = [[2, -1, 2, -1, -4, -1, 2, -1, 2]]


class Laplacian4(SingleMatrixDetect):
    """Pierre-Simon de Laplace operator 4th implementation. 3x3 matrix."""
    matrices = [[-1, -1, -1, -1, 8, -1, -1, -1, -1]]


class Kayyali(SingleMatrixDetect):
    """Kayyali operator. 3x3 matrix."""
    matrices = [[6, 0, -6, 0, 0, 0, -6, 0, 6]]


class ExLaplacian1(SingleMatrixDetect):
    """Extended Pierre-Simon de Laplace operator 1st implementation. 5x5 matrix."""
    matrices = [[0, 0, -1, 0, 0, 0, 0, -1, 0, 0, -1, -1, 8, -1, -1, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0]]


class ExLaplacian2(SingleMatrixDetect):
    """Extended Pierre-Simon de Laplace operator 2nd implementation. 5x5 matrix."""
    matrices = [[0, 1, -1, 1, 0, 1, 1, -4, 1, 1, -1, -4, 8, -4, -1, 1, 1, -4, 1, 1, 0, 1, -1, 1, 0]]


class ExLaplacian3(SingleMatrixDetect):
    """Extended Pierre-Simon de Laplace operator 3rd implementation. 5x5 matrix."""
    matrices = [[-1, 1, -1, 1, -1, 1, 2, -4, 2, 1, -1, -4, 8, -4, -1, 1, 2, -4, 2, 1, -1, 1, -1, 1, -1]]


class ExLaplacian4(SingleMatrixDetect):
    """Extended Pierre-Simon de Laplace operator 4th implementation. 5x5 matrix."""
    matrices = [[-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 24, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]]


class LoG(SingleMatrixDetect):
    """Laplacian of Gaussian. 5x5 matrix."""
    matrices = [[0, 0, -1, 0, 0, 0, -1, -2, -1, 0, -1, -2, 16, -2, -1, 0, -1, -2, -1, 0, 0, 0, -1, 0, 0]]


class Roberts(EuclidianDistanceMatrixDetect):
    """Lawrence Roberts operator. 2x2 matrices computed in 3x3 matrices."""
    matrices = [
        [0, 0, 0, 0, 1, 0, 0, 0, -1],
        [0, 1, 0, -1, 0, 0, 0, 0, 0]
    ]


class Prewitt(EuclidianDistanceMatrixDetect):
    """Judith M. S. Prewitt operator. 3x3 matrices."""
    matrices = [
        [1, 0, -1, 1, 0, -1, 1, 0, -1],
        [1, 1, 1, 0, 0, 0, -1, -1, -1]
    ]


class PrewittStd(EdgeDetect):
    """Judith M. S. Prewitt Vapoursynth plugin operator. 3x3 matrices."""
    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        return clip.std.Prewitt()


class Sobel(EuclidianDistanceMatrixDetect):
    """Sobel–Feldman operator. 3x3 matrices."""
    matrices = [
        [1, 0, -1, 2, 0, -2, 1, 0, -1],
        [1, 2, 1, 0, 0, 0, -1, -2, -1]
    ]


class SobelStd(EdgeDetect):
    """Sobel–Feldman Vapoursynth plugin operator. 3x3 matrices."""
    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        return clip.std.Sobel()


class Scharr(EuclidianDistanceMatrixDetect):
    """H. Scharr optimized operator. 3x3 matrices."""
    matrices = [
        [-3, 0, 3, -10, 0, 10, -3, 0, 3],
        [-3, -10, -3, 0, 0, 0, 3, 10, 3]
    ]


class ScharrG41(Scharr):
    """H. Scharr optimized operator. 3x3 matrices from G41Fun."""
    divisors = [3, 3]


class Kroon(EuclidianDistanceMatrixDetect):
    """Dirk-Jan Kroon operator. 3x3 matrices."""
    matrices = [
        [-17, 0, 17, -61, 0, 61, -17, 0, 17],
        [-17, -61, -17, 0, 0, 0, 17, 61, 17]
    ]


class FreyChenG41(EuclidianDistanceMatrixDetect):
    """"Chen Frei" operator. 3x3 matrices from G41Fun."""
    matrices = [
        [-7, 0, 7, -10, 0, 10, -7, 0, 7],
        [-7, -10, -7, 0, 0, 0, 7, 10, 7]
    ]
    divisors = [7, 7]


class TEdge(EuclidianDistanceMatrixDetect):
    """(TEdgeMasktype=2) Avisynth plugin. 3x3 matrices."""
    matrices = [
        [12, -74, 0, 74, -12],
        [-12, 74, 0, -74, 12]
    ]
    divisors = [62, 62]
    mode_types = ['h', 'v']


class TEdgeTedgemask(EdgeDetect):
    """(tedgemask.TEdgeMask(threshold=0.0, type=2)) Vapoursynth plugin. 3x3 matrices."""
    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        return clip.tedgemask.TEdgeMask(threshold=0, type=2)


class ExPrewitt(EuclidianDistanceMatrixDetect):
    """Extended Judith M. S. Prewitt operator. 5x5 matrices."""
    matrices = [
        [2, 1, 0, -1, -2, 2, 1, 0, -1, -2, 2, 1, 0, -1, -2, 2, 1, 0, -1, -2, 2, 1, 0, -1, -2],
        [2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, -1, -1, -1, -1, -1, -2, -2, -2, -2, -2]
    ]


class ExSobel(EuclidianDistanceMatrixDetect):
    """Extended Sobel–Feldman operator. 5x5 matrices."""
    matrices = [
        [2, 1, 0, -1, -2, 2, 1, 0, -1, -2, 4, 2, 0, -2, -4, 2, 1, 0, -1, -2, 2, 1, 0, -1, -2],
        [2, 2, 4, 2, 2, 1, 1, 2, 1, 1, 0, 0, 0, 0, 0, -1, -1, -2, -1, -1, -2, -2, -4, -2, -2]
    ]


class FDOG(EuclidianDistanceMatrixDetect):
    """Flow-based Difference Of Gaussian operator. 3x3 matrices from G41Fun."""
    matrices = [
        [1, 1, 0, -1, -1, 2, 2, 0, -2, -2, 3, 3, 0, -3, -3, 2, 2, 0, -2, -2, 1, 1, 0, -1, -1],
        [1, 2, 3, 2, 1, 1, 2, 3, 2, 1, 0, 0, 0, 0, 0, -1, -2, -3, -2, -1, -1, -2, -3, -2, -1]
    ]
    divisors = [2, 2]


class Robinson3(MaxDetect):
    """Robinson compass operator level 3. 3x3 matrices."""
    matrices = [
        [1, 1, 1, 0, 0, 0, -1, -1, -1],
        [1, 1, 0, 1, 0, -1, 0, -1, -1],
        [1, 0, -1, 1, 0, -1, 1, 0, -1],
        [0, -1, -1, 1, 0, -1, 1, 1, 0]
    ]


class Robinson5(MaxDetect):
    """Robinson compass operator level 5. 3x3 matrices."""
    matrices = [
        [1, 2, 1, 0, 0, 0, -1, -2, -1],
        [2, 1, 0, 1, 0, -1, 0, -1, -2],
        [1, 0, -1, 2, 0, -2, 1, 0, -1],
        [0, -1, -2, 1, 0, -1, 2, 1, 0]
    ]


class Kirsch(MaxDetect):
    """Russell Kirsch compass operator. 3x3 matrices."""
    matrices = [
        [5, 5, 5, -3, 0, -3, -3, -3, -3],
        [5, 5, -3, 5, 0, -3, -3, -3, -3],
        [5, -3, -3, 5, 0, -3, 5, -3, -3],
        [-3, -3, -3, 5, 0, -3, 5, 5, -3],
        [-3, -3, -3, -3, 0, -3, 5, 5, 5],
        [-3, -3, -3, -3, 0, 5, -3, 5, 5],
        [-3, -3, 5, -3, 0, 5, -3, -3, 5],
        [-3, 5, 5, -3, 0, 5, -3, -3, -3]
    ]


class ExKirsch(MaxDetect):
    """Extended Russell Kirsch compass operator. 5x5 matrices."""
    matrices = [
        [9, 9, 9, 9, 9, 9, 5, 5, 5, 9, -7, -3, 0, -3, -7, -7, -3, -3, -3, -7, -7, -7, -7, -7, -7],
        [9, 9, 9, 9, -7, 9, 5, 5, -3, -7, 9, 5, 0, -3, -7, 9, -3, -3, -3, -7, -7, -7, -7, -7, -7],
        [9, 9, -7, -7, -7, 9, 5, -3, -3, -7, 9, 5, 0, -3, -7, 9, 5, -3, -3, -7, 9, 9, -7, -7, -7],
        [-7, -7, -7, -7, -7, 9, -3, -3, -3, -7, 9, 5, 0, -3, -7, 9, 5, 5, -3, -7, 9, 9, 9, 9, -7],
        [-7, -7, -7, -7, -7, -7, -3, -3, -3, -7, -7, -3, 0, -3, -7, 9, 5, 5, 5, 9, 9, 9, 9, 9, 9],
        [-7, -7, -7, -7, -7, -7, -3, -3, -3, 9, -7, -3, 0, 5, 9, -7, -3, 5, 5, 9, -7, 9, 9, 9, 9],
        [-7, -7, -7, 9, 9, -7, -3, -3, 5, 9, -7, -3, 0, 5, 9, -7, -3, -3, 5, 9, -7, -7, -7, 9, 9],
        [-7, 9, 9, 9, 9, -7, -3, 5, 5, 9, -7, -3, 0, 5, 9, -7, -3, -3, -3, 9, -7, -7, -7, -7, -7]
    ]


class MinMax(EdgeDetect):
    """Min/max mask with separate luma/chroma radii."""
    radii: Tuple[int, int, int]

    def __init__(self, rady: int = 2, radc: int = 0) -> None:
        super().__init__()
        self.radii = (rady, radc, radc)

    def _compute_mask(self, clip: vs.VideoNode) -> vs.VideoNode:
        assert clip.format

        def _minmax(clip: vs.VideoNode, iterations: int) -> Tuple[vs.VideoNode, vs.VideoNode]:
            def _getcoord(i: int) -> List[int]:
                return [0, 1, 0, 1, 1, 0, 1, 0] if (i % 3) != 1 else [1] * 8

            clip_max = clip
            for i in range(1, iterations + 1):
                clip_max = clip_max.std.Maximum(coordinates=_getcoord(i))

            clip_min = clip
            for i in range(1, iterations + 1):
                clip_min = clip_min.std.Minimum(coordinates=_getcoord(i))

            return clip_max, clip_min

        planes = [
            core.std.Expr(_minmax(p, rad), 'x y -')
            for p, rad in zip(split(clip), self.radii)
        ]
        return planes[0] if len(planes) == 1 else join(planes, clip.format.color_family)


class FreyChen(MatrixEdgeDetect):
    """Chen Frei operator. 3x3 matrices properly implemented."""
    sqrt2 = math.sqrt(2)
    matrices = [
        [1, sqrt2, 1, 0, 0, 0, -1, -sqrt2, -1],
        [1, 0, -1, sqrt2, 0, -sqrt2, 1, 0, -1],
        [0, -1, sqrt2, 1, 0, -1, -sqrt2, 1, 0],
        [sqrt2, -1, 0, -1, 0, 1, 0, 1, -sqrt2],
        [0, 1, 0, -1, 0, -1, 0, 1, 0],
        [-1, 0, 1, 0, 0, 0, 1, 0, -1],
        [1, -2, 1, -2, 4, -2, 1, -2, 1],
        [-2, 1, -2, 1, 4, 1, -2, 1, -2],
        [1, 1, 1, 1, 1, 1, 1, 1, 1]
    ]
    divisors = [
        2 * sqrt2,
        2 * sqrt2,
        2 * sqrt2,
        2 * sqrt2,
        2,
        2,
        6,
        6,
        3
    ]

    def _preprocess(self, clip: vs.VideoNode) -> vs.VideoNode:
        return depth(clip, 32)

    def _postprocess(self, clip: vs.VideoNode) -> vs.VideoNode:
        return depth(clip, self._bits, range=Range.FULL, range_in=Range.FULL)

    def _merge(self, clips: Sequence[vs.VideoNode]) -> vs.VideoNode:
        M = 'x x * y y * + z z * + a a * +'
        S = f'b b * c c * + d d * + e e * + f f * + {M} +'
        return core.std.Expr(clips, f'{M} {S} / sqrt')



def get_all_edge_detects(clip: vs.VideoNode, **kwargs: Any) -> List[vs.VideoNode]:
    def _all_subclasses(cls: Type[EdgeDetect]) -> Set[Type[EdgeDetect]]:
        return set(cls.__subclasses__()).union(
            [s for c in cls.__subclasses__() for s in _all_subclasses(c)])

    all_subclasses = {
        s for s in _all_subclasses(EdgeDetect)  # type: ignore
        if s.__name__ not in {
            'MatrixEdgeDetect', 'SingleMatrixDetect', 'EuclidianDistanceMatrixDetect', 'MaxDetect'
        }
    }
    return [
        edge_detect().get_mask(clip, **kwargs).text.Text(edge_detect.__name__)  # type: ignore
        for edge_detect in sorted(all_subclasses, key=lambda x: x.__name__)
    ]
