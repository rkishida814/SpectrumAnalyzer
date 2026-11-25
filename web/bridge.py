"""
ブラウザ（Pyodide）から core/ と state.py を呼ぶための橋渡し。
計算は core/ のコードをそのまま使う。ここではデータの受け渡し（JSON）だけを行う。
"""
import json
import dataclasses
import time

import numpy as np
from core.parser import parse_xrd_file
from core.math_utils import apply_sg_filter, calculate_baseline_y, calculate_integral
from core.fitter import (fit_individual_peak, fit_global_peaks,
                         refresh_peak, set_width, convert_profile)
from state import Peak

_PEAK_FIELDS = {f.name for f in dataclasses.fields(Peak)}


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not serializable: {type(o)}")


def _dumps(obj):
    return json.dumps(obj, default=_json_default)


def _peaks_from(dicts):
    return [Peak(**{k: v for k, v in d.items() if k in _PEAK_FIELDS}) for d in dicts]


def _peak_dicts(peaks):
    return [dataclasses.asdict(p) for p in peaks]


def _clipped(req):
    """state.AppState.get_clipped_data と同じ切り出しをし、ベースラインの y を付ける。"""
    x = np.asarray(req["x"], dtype=float)
    y = np.asarray(req["y"], dtype=float)
    bmin, bmax = req.get("baseline_min_x"), req.get("baseline_max_x")
    if bmin is not None and bmax is not None:
        mask = (x >= bmin) & (x <= bmax)
        x, y = x[mask], y[mask]
    pts = req.get("baseline_pts")
    base_y = calculate_baseline_y(x, *pts) if pts else np.zeros_like(x)
    return x, y, base_y


def parse(path):
    x, y = parse_xrd_file(path)
    if len(x) == 0:
        raise ValueError("No valid numerical data found in the file.")
    return _dumps({"x": x.tolist(), "y": y.tolist()})


def smooth(req_json):
    req = json.loads(req_json)
    y = np.asarray(req["y"], dtype=float)
    return _dumps({"y": apply_sg_filter(y).tolist()})


def integral(req_json):
    req = json.loads(req_json)
    x, y, base_y = _clipped(req)
    area = float(calculate_integral(x, y, base_y))
    return _dumps({"area": area, "x": x.tolist(), "y": y.tolist(), "base_y": base_y.tolist()})


def peaks_op(req_json):
    """
    ピークの派生値の計算（core/fitter.py の関数をそのまま使う）。
      op="refresh"   : 表で値を直したあと（TCH の FWHM・G Frac、面積を計算し直す）
      op="convert"   : プロファイルを切り替えたとき（形を保って変換する）
      op="set_width" : FWHM のドラッグ（index のピーク）と、G Frac の一括適用（index なし）
    """
    req = json.loads(req_json)
    profile = req["profile"]
    peaks = _peaks_from(req["peaks"])
    op = req["op"]
    if op == "refresh":
        for p in peaks:
            refresh_peak(p, profile)
    elif op == "convert":
        for p in peaks:
            convert_profile(p, profile)
    elif op == "set_width":
        index = req.get("index")
        targets = peaks if index is None else [peaks[index]]
        for p in targets:
            fwhm = req.get("fwhm")
            g_ratio = req.get("g_ratio")
            set_width(p, p.fwhm if fwhm is None else fwhm,
                      p.g_ratio if g_ratio is None else g_ratio, profile)
    else:
        raise ValueError("unknown op: " + op)
    return _dumps({"peaks": _peak_dicts(peaks)})


def fit(req_json):
    """kind='global' は全ピーク、kind='individual' は index のピークだけを最適化する。"""
    from js import reportProgress  # worker.js で定義

    req = json.loads(req_json)
    x, y, base_y = _clipped(req)
    peaks = _peaks_from(req["peaks"])
    if len(x) == 0 or len(peaks) == 0:
        return _dumps({"peaks": _peak_dicts(peaks), "mse": None, "timeout": False})

    last = [0.0]
    final = [0, 0]

    def progress(step=None, max_nfev=None):
        final[0], final[1] = step, max_nfev
        now = time.time()
        if now - last[0] > 0.05:
            last[0] = now
            reportProgress(step, max_nfev)

    method = req.get("method", "trf")
    profile = req.get("profile", "pv")
    timeout = False
    mse = None
    try:
        if req["kind"] == "global":
            max_evals = max(1500, 500 * len(peaks))
            mse = fit_global_peaks(x, y, base_y, peaks, max_nfev=max_evals, method=method,
                                   timeout=45.0, callback_fn=progress, profile=profile)
        else:
            peak = peaks[req["index"]]
            mse = fit_individual_peak(x, y, base_y, peak, max_nfev=1500, method=method,
                                      timeout=45.0, callback_fn=progress, profile=profile)
    except TimeoutError:
        timeout = True
    reportProgress(final[0], final[1])  # 間引いた途中経過の最後の値を必ず送る
    return _dumps({"peaks": _peak_dicts(peaks), "mse": mse, "timeout": timeout})
