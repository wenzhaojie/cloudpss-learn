#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dxf_dump.py — 解析 DXF，导出基础结构为 JSON，便于后续分析

用法：
  python dxf_dump.py your.dxf --outdir ./dxf_dump --limit 0

说明：
- 不做识别，只导出“原始事实”：图层、块定义、块引用(INSERT)、多段线(LWPOLYLINE/POLYLINE)、
  直线、圆弧、圆、文字(TEXT/MTEXT)、标注(DIMENSION) 等。
- --limit 控制每类实体最多导出条数（0 表示不限制，慎用大图）。
"""

from __future__ import annotations
import argparse
import json
import os
from collections import defaultdict
from typing import Any

import ezdxf


# ------------------------ 工具函数 ------------------------
def as_float(x):
    try:
        return float(x)
    except Exception:
        return None


def vec_to_list(v):
    """把 DXF 的 Vec2/Vec3 转成 Python list，便于 JSON 序列化。"""
    try:
        seq = list(v)
        return [as_float(t) for t in seq]
    except Exception:
        return None


def write_json(path: str, data: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_flag(obj, attr: str):
    """兼容属性/方法两种写法，统一返回 bool 或 None。"""
    v = getattr(obj, attr, None)
    if v is None:
        return None
    if callable(v):
        try:
            v = v()
        except Exception:
            return None
    try:
        return bool(v)
    except Exception:
        return None


# ------------------------ 各类导出 ------------------------
def dump_meta(doc, outdir: str):
    """只使用跨版本更稳的字段。"""
    try:
        dxfversion = str(getattr(doc, "dxfversion", ""))
    except Exception:
        dxfversion = ""

    meta = {
        "filename": getattr(doc, "filename", None),
        "dxfversion": dxfversion,               # ezdxf 提供的版本字符串（如 'R2010'）
        "header_$ACADVER": doc.header.get("$ACADVER"),
        "units_code_$INSUNITS": doc.header.get("$INSUNITS"),  # 0=无单位, 4=mm, 6=m
        "drawing_limits": {
            "min_$LIMMIN": vec_to_list(doc.header.get("$LIMMIN")),
            "max_$LIMMAX": vec_to_list(doc.header.get("$LIMMAX")),
        },
        "layouts": [layout.name for layout in doc.layouts],
        "modelspace_entity_count": sum(1 for _ in doc.modelspace()),
    }
    write_json(os.path.join(outdir, "00_meta.json"), meta)


def dump_layers(doc, outdir: str):
    layers = []
    for l in doc.layers:
        dxf = getattr(l, "dxf", l)
        name = getattr(dxf, "name", getattr(l, "name", None))
        # 这些字段在不同版本里可能是方法，也可能是属性；统一用 get_flag 取值
        is_off = get_flag(l, "is_off")
        layers.append({
            "name": name,
            "color": getattr(dxf, "color", None),
            "linetype": getattr(dxf, "linetype", None),
            "lineweight": getattr(dxf, "lineweight", None),
            "on": (not is_off) if is_off is not None else None,
            "frozen": get_flag(l, "is_frozen"),
            "locked": get_flag(l, "is_locked"),
            "plottable": get_flag(l, "is_plottable"),
        })
    write_json(os.path.join(outdir, "01_layers.json"), layers)


def dump_blocks(doc, outdir: str, limit: int | None):
    blocks = []
    for blk in doc.blocks:
        type_count = defaultdict(int)
        for e in blk:
            try:
                type_count[e.dxftype()] += 1
            except Exception:
                type_count["<unknown>"] += 1
        base_pt = None
        try:
            base_pt = vec_to_list(blk.block.dxf.base_point)
        except Exception:
            pass
        blocks.append({
            "name": blk.name,
            "base_point": base_pt,
            "entity_type_counts": dict(type_count),
        })
        if limit and len(blocks) >= limit:
            break
    write_json(os.path.join(outdir, "02_blocks_definitions.json"), blocks)


def dump_inserts(msp, outdir: str, limit: int | None):
    data = []
    for e in msp.query("INSERT"):
        atts = {}
        try:
            for a in e.attribs():
                atts[getattr(a.dxf, "tag", None)] = getattr(a.dxf, "text", None)
        except Exception:
            pass
        dxf = e.dxf
        insert = [as_float(getattr(dxf.insert, "x", None)),
                  as_float(getattr(dxf.insert, "y", None)),
                  as_float(getattr(dxf.insert, "z", None))]
        scale = [as_float(getattr(dxf, "xscale", None)),
                 as_float(getattr(dxf, "yscale", None)),
                 as_float(getattr(dxf, "zscale", None))]
        data.append({
            "block_name": getattr(dxf, "name", None),
            "layer": getattr(dxf, "layer", None),
            "insert": insert,
            "rotation_deg": as_float(getattr(dxf, "rotation", None)),
            "scale": scale,
            "attribs": atts,
        })
        if limit and len(data) >= limit:
            break
    write_json(os.path.join(outdir, "10_inserts_blocks.json"), data)


def dump_lwpolylines(msp, outdir: str, limit: int | None):
    data = []
    for e in msp.query("LWPOLYLINE"):
        pts = []
        try:
            # get_points() 返回 (x, y, [start_width, end_width, bulge])
            for p in e.get_points():
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    pts.append([as_float(p[0]), as_float(p[1])])
        except Exception:
            pass
        data.append({
            "layer": getattr(e.dxf, "layer", None),
            "closed": bool(getattr(e, "closed", False)),
            "points_xy": pts,
        })
        if limit and len(data) >= limit:
            break
    write_json(os.path.join(outdir, "11_lwpolylines.json"), data)


def dump_polylines(msp, outdir: str, limit: int | None):
    data = []
    for e in msp.query("POLYLINE"):
        pts = []
        try:
            for v in e.vertices:
                loc = getattr(v.dxf, "location", None)
                if loc is not None:
                    pts.append([as_float(getattr(loc, "x", None)),
                                as_float(getattr(loc, "y", None)),
                                as_float(getattr(loc, "z", None))])
        except Exception:
            pass
        closed = None
        try:
            closed = bool(getattr(e, "is_closed", None))
        except Exception:
            pass
        data.append({
            "layer": getattr(e.dxf, "layer", None),
            "closed": closed,
            "points_xyz": pts,
        })
        if limit and len(data) >= limit:
            break
    write_json(os.path.join(outdir, "12_polylines.json"), data)


def dump_lines(msp, outdir: str, limit: int | None):
    data = []
    for e in msp.query("LINE"):
        dxf = e.dxf
        start = [as_float(getattr(dxf.start, "x", None)),
                 as_float(getattr(dxf.start, "y", None)),
                 as_float(getattr(dxf.start, "z", None))]
        end = [as_float(getattr(dxf.end, "x", None)),
               as_float(getattr(dxf.end, "y", None)),
               as_float(getattr(dxf.end, "z", None))]
        data.append({
            "layer": getattr(dxf, "layer", None),
            "start": start,
            "end": end,
        })
        if limit and len(data) >= limit:
            break
    write_json(os.path.join(outdir, "13_lines.json"), data)


def dump_arcs_circles(msp, outdir: str, limit: int | None):
    arcs = []
    for e in msp.query("ARC"):
        dxf = e.dxf
        center = [as_float(getattr(dxf.center, "x", None)),
                  as_float(getattr(dxf.center, "y", None)),
                  as_float(getattr(dxf.center, "z", None))]
        arcs.append({
            "layer": getattr(dxf, "layer", None),
            "center": center,
            "radius": as_float(getattr(dxf, "radius", None)),
            "start_angle_deg": as_float(getattr(dxf, "start_angle", None)),
            "end_angle_deg": as_float(getattr(dxf, "end_angle", None)),
        })
        if limit and len(arcs) >= limit:
            break
    write_json(os.path.join(outdir, "14_arcs.json"), arcs)

    circles = []
    for e in msp.query("CIRCLE"):
        dxf = e.dxf
        center = [as_float(getattr(dxf.center, "x", None)),
                  as_float(getattr(dxf.center, "y", None)),
                  as_float(getattr(dxf.center, "z", None))]
        circles.append({
            "layer": getattr(dxf, "layer", None),
            "center": center,
            "radius": as_float(getattr(dxf, "radius", None)),
        })
        if limit and len(circles) >= limit:
            break
    write_json(os.path.join(outdir, "15_circles.json"), circles)


def dump_texts(msp, outdir: str, limit: int | None):
    texts = []
    for e in msp.query("TEXT"):
        dxf = e.dxf
        insert = [as_float(getattr(dxf.insert, "x", None)),
                  as_float(getattr(dxf.insert, "y", None)),
                  as_float(getattr(dxf.insert, "z", None))]
        texts.append({
            "layer": getattr(dxf, "layer", None),
            "text": getattr(dxf, "text", None),
            "insert": insert,
            "height": as_float(getattr(dxf, "height", None)),
            "rotation_deg": as_float(getattr(dxf, "rotation", None)),
        })
        if limit and len(texts) >= limit:
            break

    mtexts = []
    for e in msp.query("MTEXT"):
        dxf = e.dxf
        insert = [as_float(getattr(dxf.insert, "x", None)),
                  as_float(getattr(dxf.insert, "y", None)),
                  as_float(getattr(dxf.insert, "z", None))]
        mtexts.append({
            "layer": getattr(dxf, "layer", None),
            "text": getattr(e, "text", None),
            "insert": insert,
            "char_height": as_float(getattr(dxf, "char_height", None)),
            "rotation_deg": as_float(getattr(dxf, "rotation", None)),
            "width": as_float(getattr(dxf, "width", None)),
        })
        if limit and len(mtexts) >= limit:
            break

    write_json(os.path.join(outdir, "16_texts.json"), texts)
    write_json(os.path.join(outdir, "17_mtexts.json"), mtexts)


def dump_dimensions(msp, outdir: str, limit: int | None):
    data = []
    for e in msp.query("DIMENSION"):
        try:
            e.render()  # 让 ezdxf 计算 measurement（部分版本可能抛异常，忽略即可）
        except Exception:
            pass
        dxf = e.dxf
        defpt = getattr(dxf, "defpoint", None)
        data.append({
            "layer": getattr(dxf, "layer", None),
            "dimtype": getattr(e, "dimtype", None),
            "text": getattr(dxf, "text", None),
            "measurement": getattr(e, "measurement", None),
            "defpoint": [as_float(getattr(defpt, "x", None)),
                         as_float(getattr(defpt, "y", None)),
                         as_float(getattr(defpt, "z", None))] if defpt is not None else None,
        })
        if limit and len(data) >= limit:
            break
    write_json(os.path.join(outdir, "18_dimensions.json"), data)


# ------------------------ CLI ------------------------
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", help="DXF 文件路径（DWG 请先转为 DXF，如 2010 ASCII DXF）")
    ap.add_argument("--outdir", default="dxf_dump", help="输出目录")
    ap.add_argument("--limit", type=int, default=5000, help="每类实体最多导出条数；0 表示不限制")
    return ap.parse_args()


def main():
    args = parse_args()

    # 读取 DXF
    doc = ezdxf.readfile(args.dxf)
    msp = doc.modelspace()
    outdir = args.outdir
    limit = None if args.limit == 0 else int(args.limit)

    dump_meta(doc, outdir)
    dump_layers(doc, outdir)
    dump_blocks(doc, outdir, limit)
    dump_inserts(msp, outdir, limit)
    dump_lwpolylines(msp, outdir, limit)
    dump_polylines(msp, outdir, limit)
    dump_lines(msp, outdir, limit)
    dump_arcs_circles(msp, outdir, limit)
    dump_texts(msp, outdir, limit)
    dump_dimensions(msp, outdir, limit)

    print(f"DXF parsed. JSON files saved to: {os.path.abspath(outdir)}")


if __name__ == "__main__":
    main()
