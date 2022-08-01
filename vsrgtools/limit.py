from __future__ import annotations

from typing import List, Tuple

import vapoursynth as vs
from vsexprtools import EXPR_VARS, PlanesT, aka_expr_available, expr_func, norm_expr_planes, normalise_planes
from vsutil import get_neutral_value, get_peak_value

from vsrgtools.enum import LimitFilterMode

__all__ = [
    'limit_filter'
]

core = vs.core


def limit_filter(
    flt: vs.VideoNode, src: vs.VideoNode, ref: vs.VideoNode | None = None,
    mode: LimitFilterMode = LimitFilterMode.CLAMPING, planes: PlanesT = None,
    thr: int | Tuple[int, int] = 1, elast: float = 2.0, bright_thr: int | None = None
) -> vs.VideoNode:
    assert flt.format and src.format

    planes = normalise_planes(flt, planes)

    is_yuv = flt.format.color_family == vs.YUV

    got_ref = ref is not None

    if isinstance(thr, tuple):
        thr, thrc = thr
    else:
        thrc = thr

    if bright_thr is None:
        bright_thr = thr

    for var, name, l in [
        (thr, 'thr', 0), (thrc, 'thrc', 0), (bright_thr, 'bright_thr', 0), (elast, 'elast', 1)
    ]:
        if var < l:
            raise ValueError(f'limit_filter: {name} must be >= 0')

    if ref is None and mode != LimitFilterMode.CLAMPING:
        raise ValueError(f'limit_filter: with mode={mode._name_} you need to specify ref!')

    force_expr = mode.force_expr

    if any([
        got_ref, flt.format.sample_type == vs.FLOAT,
        thr >= 128, bright_thr >= 128, mode != LimitFilterMode.CLAMPING
    ]):
        force_expr = True

    if thr <= 0 and bright_thr <= 0 and (not is_yuv or thrc <= 0):
        return src

    if thr >= 255 and bright_thr >= 255 and (not is_yuv or thrc >= 255):
        return flt

    if force_expr:
        peak = get_peak_value(flt)

        clips = [flt, src]

        if ref:
            clips.append(ref)

        return expr_func(clips, norm_expr_planes(flt, [
            _limit_filter_expr(got_ref, thr, elast, bright_thr, peak, mode),
            _limit_filter_expr(got_ref, thrc, elast, thrc, peak, mode)
        ]))

    diff = flt.std.MakeDiff(src, planes)

    diff = _limit_filter_lut(diff, elast, thr, bright_thr, [0])

    if 1 in planes or 2 in planes:
        diff = _limit_filter_lut(diff, elast, thrc, thrc, list({*planes} - {0}))

    return flt.std.MakeDiff(diff, planes)


def _limit_filter_lut(
    diff: vs.VideoNode, elast: float, thr: float, largen_thr: float, planes: List[int]
) -> vs.VideoNode:
    assert diff.format

    neutral = int(get_neutral_value(diff))
    peak = int(get_peak_value(diff))

    thr = int(thr * peak / 255)
    largen_thr = int(largen_thr * peak / 255)

    if thr >= peak / 2 and largen_thr >= peak / 2:
        neutral_clip = diff.std.BlankClip(color=neutral)

        all_planes = list(range(diff.format.num_planes))

        if planes == all_planes:
            return neutral_clip

        diff_planes = planes + list({*all_planes} - {*planes})

        return core.std.ShufflePlanes(
            [neutral_clip, diff], diff_planes, diff.format.color_family
        )

    no_elast = elast <= 1

    def limitLut(x: int) -> int:
        dif = x - neutral

        dif_abs = abs(dif)

        thr_1 = largen_thr if dif > 0 else thr

        if dif_abs <= thr_1:
            return neutral

        if no_elast:
            return x

        thr_2 = thr_1 * elast

        if dif_abs >= thr_2:
            return x

        thr_slope = 1 / (thr_2 - thr_1)

        return round(dif * (dif_abs - thr_1) * thr_slope + neutral)

    return diff.std.Lut(planes, function=limitLut)


def _limit_filter_expr(
    got_ref: bool, thr: float, elast: float, largen_thr: float, peak: float, mode: LimitFilterMode
) -> str:
    if mode in {LimitFilterMode.SIMPLE_MIN, LimitFilterMode.SIMPLE_MAX}:
        return f'y z - abs y x - abs {mode.op} z x ?'
    elif mode in {LimitFilterMode.DIFF_MIN, LimitFilterMode.DIFF_MAX}:
        if aka_expr_available:
            return f'y x - A! y z - B! A@ B@ xor y A@ abs B@ abs {mode.op} x z ? ?'

        return f'y x - y z - xor y y x - abs y z - abs {mode.op} x z ? ?'

    ref = EXPR_VARS[1 + got_ref]

    header = ''

    dif = 'x y -'
    dif_abs = f' x {ref} - abs'

    if aka_expr_available:
        header = f'{dif} DIF! {dif_abs} DIFABS!'
        dif, dif_abs = 'DIF@', 'DIFABS@'

    thr, largen_thr = [x * peak / 255 for x in (thr, largen_thr)]

    if thr <= 0 and largen_thr <= 0:
        return 'y'

    if thr >= peak and largen_thr >= peak:
        return ''

    def _limit_xthr_expr(var: float) -> str:
        if var <= 0:
            return 'y'

        if var >= peak:
            return 'x'

        if elast <= 1:
            return f'{dif_abs} {var} <= x y ?'

        thr_1, thr_2 = var, var * elast
        thr_slope = 1 / (thr_2 - thr_1)

        return f'{dif_abs} {thr_1} <= x {dif_abs} {thr_2} >= y y {dif} {thr_2} {dif_abs} - * {thr_slope} * + ? ?'

    limitExpr = _limit_xthr_expr(thr)

    if largen_thr != thr:
        limitExpr = f'x {ref} > {_limit_xthr_expr(largen_thr)} {limitExpr} ?'

    return f'{header} {limitExpr}'
