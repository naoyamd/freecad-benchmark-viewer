"""Export visible FreeCAD final shapes to a portable viewer JSON bundle.

This module intentionally imports no FreeCAD module.  FreeCAD is used through
the document objects passed to :func:`export_document`, so the file is also
usable by stdlib-only tests.
"""

import json
import math
import os
import re
from pathlib import Path


SCHEMA = "freecad-benchmark/v1"
DEFAULT_DEFLECTION_MM = 0.5
DEFAULT_COLOR = "#B0B0B0"
EVAL_STATES = {"unverified", "self-reported", "verified"}
GATE_STATES = {"pass", "fail", "pending", "unverified"}


class FreeCADExportError(ValueError):
    """Raised when a document or sidecar cannot be exported safely."""


def export_document(doc, outpath, metadata_path=None, objects=None, deflection=DEFAULT_DEFLECTION_MM):
    """Write one ``freecad-benchmark/v1`` bundle and return its data.

    ``objects`` is an optional explicit list of FreeCAD objects or Name/Label
    strings.  With no list, visible shape-bearing objects are selected using
    the policy documented in README.md.
    """
    _number(deflection, "deflection", positive=True)
    metadata = _read_metadata(metadata_path) if metadata_path else {}
    document_objects = list(getattr(doc, "Objects"))
    parents = _parent_map(document_objects)
    candidates = (
        _resolve_objects(doc, document_objects, objects)
        if objects is not None
        else _auto_objects(document_objects, parents)
    )

    parts = []
    used_ids = set()
    for ordinal, obj in enumerate(candidates, 1):
        if _is_link(obj):
            raise FreeCADExportError(
                "App::Link %s is unsupported; resolve the instance in FreeCAD "
                "or select its final Part/Body instead" % _name(obj)
            )
        part = _part(obj, ordinal, parents, float(deflection), used_ids)
        if part:
            parts.append(part)

    run = {
        "id": str(getattr(doc, "Name", "freecad-document") or "freecad-document"),
        "title": str(getattr(doc, "Label", None) or getattr(doc, "Name", "FreeCAD")),
        # A benchmark version belongs in metadata; never confuse it with the
        # transport schema version.  Empty means no benchmark version supplied.
        "specVersion": "",
        "model": "",
        "status": "unverified",
        "sourceFiles": _source_files(doc),
    }
    run.update({key: metadata["run"][key] for key in ("id", "title", "specVersion", "model", "sourceFiles") if key in metadata.get("run", {})})
    run["status"] = "unverified"

    evaluation = {
        "status": "unverified",
        "score": None,
        "maxScore": 100,
        "gates": [],
        "metrics": [],
        "issues": [],
    }
    if metadata.get("evaluation"):
        evaluation.update(metadata["evaluation"])

    points = [tuple(part["vertices"][i:i + 3]) for part in parts for i in range(0, len(part["vertices"]), 3)]
    bundle = {
        "schema": SCHEMA,
        "run": run,
        "parts": parts,
        "assembly": {"units": "mm", "bboxMm": _bbox(points)},
        "evaluation": evaluation,
    }
    if metadata.get("timeseries") is not None:
        bundle["timeseries"] = metadata["timeseries"]
    _validate_bundle(bundle)
    try:
        Path(outpath).write_text(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except Exception as exc:
        raise FreeCADExportError("cannot write export %s: %s" % (outpath, exc))
    return bundle


def _number(value, path, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise FreeCADExportError("%s must be finite" % path)
    if positive and value <= 0:
        raise FreeCADExportError("%s must be positive" % path)
    return float(value)


def _shape(obj):
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    is_null = getattr(shape, "isNull", None)
    if callable(is_null) and is_null():
        return None
    return shape


def _type(obj):
    return str(getattr(obj, "TypeId", ""))


def _name(obj):
    return str(getattr(obj, "Name", None) or getattr(obj, "Label", None) or "object")


def _label(obj):
    return str(getattr(obj, "Label", None) or _name(obj))


def _is_body(obj):
    type_id = _type(obj).lower()
    return type_id == "partdesign::body" or type_id.endswith("::body")


def _is_container(obj):
    type_id = _type(obj).lower()
    return type_id in {"app::part", "app::partcontainer"} or ("assembly" in type_id and hasattr(obj, "Group"))


def _is_link(obj):
    type_id = _type(obj).lower()
    return type_id == "app::link" or type_id.startswith("app::link") or type_id.endswith("::link")


def _visible(obj):
    view = getattr(obj, "ViewObject", None)
    if view is not None:
        try:
            return bool(view.Visibility)
        except (AttributeError, RuntimeError):
            pass
    try:
        return bool(obj.Visibility)
    except (AttributeError, RuntimeError):
        return None


def _parent_map(objects):
    parents = {}
    for parent in objects:
        try:
            children = list(parent.Group)
        except (AttributeError, TypeError):
            continue
        for child in children:
            parents.setdefault(id(child), parent)
    return parents


def _parents(obj, parent_map):
    result, seen = [], set()
    current = obj
    while id(current) not in seen:
        seen.add(id(current))
        parent = parent_map.get(id(current))
        if parent is None:
            getter = getattr(current, "getParentGroup", None)
            parent = getter() if callable(getter) else None
        if isinstance(parent, (list, tuple)):
            parent = parent[0] if parent else None
        if parent is None:
            break
        result.append(parent)
        current = parent
    return result


def _visible_in_tree(obj, parent_map):
    values = [_visible(obj)] + [_visible(parent) for parent in _parents(obj, parent_map)]
    return all(value is True for value in values)


def _visibility_known(obj, parent_map):
    return all(value is not None for value in [_visible(obj)] + [_visible(parent) for parent in _parents(obj, parent_map)])


def _resolve_objects(doc, all_objects, requested):
    if isinstance(requested, (str, bytes)):
        items = [requested]
    else:
        try:
            items = list(requested)
        except TypeError:
            items = [requested]
    by_name = {str(getattr(obj, key)): obj for obj in all_objects for key in ("Name", "Label") if getattr(obj, key, None)}
    result = []
    seen = set()
    for item in items:
        obj = item
        if isinstance(item, bytes):
            item = item.decode()
        if isinstance(item, str):
            getter = getattr(doc, "getObject", None)
            obj = getter(item) if callable(getter) else by_name.get(item)
            obj = obj or by_name.get(item)
        if obj is None:
            raise FreeCADExportError("explicit object not found: %r" % (item,))
        if id(obj) not in seen:
            result.append(obj)
            seen.add(id(obj))
    return result


def _auto_objects(objects, parent_map):
    for obj in objects:
        if _shape(obj) is not None and not _visibility_known(obj, parent_map):
            raise FreeCADExportError(
                "visibility is unavailable for %s; pass explicit objects=[...] "
                "instead of guessing hidden FreeCAD features" % _name(obj)
            )
    for obj in objects:
        if _is_link(obj) and _visible_in_tree(obj, parent_map):
            raise FreeCADExportError(
                "App::Link %s is unsupported; resolve the instance in FreeCAD "
                "or select its final Part/Body instead" % _name(obj)
            )
    visible_shapes = [obj for obj in objects if _shape(obj) is not None and _visible_in_tree(obj, parent_map)]
    container_children = set()
    for child in visible_shapes:
        for parent in _parents(child, parent_map):
            if _is_container(parent):
                container_children.add(id(parent))

    result = []
    for obj in visible_shapes:
        if any(_is_body(parent) for parent in _parents(obj, parent_map)):
            continue
        if _is_container(obj) and id(obj) in container_children:
            continue
        result.append(obj)
    return result


def _mesh(obj, deflection, parent_map):
    shape = _shape(obj)
    if shape is None:
        return None
    try:
        mesh_shape = shape.copy()
        getter = getattr(obj, "getGlobalPlacement", None)
        placement = getter() if callable(getter) else getattr(obj, "Placement", None)
        if placement is not None:
            # Shape.tessellate already includes Shape.Placement.  Replacing it
            # with the object's global placement handles nested App::Part once.
            mesh_shape.Placement = placement
        vertices, facets = mesh_shape.tessellate(deflection)
    except Exception as exc:
        raise FreeCADExportError("tessellation failed for %s: %s" % (_name(obj), exc))
    flat = []
    for vertex in vertices:
        try:
            xyz = (float(vertex.x), float(vertex.y), float(vertex.z))
        except (AttributeError, TypeError, ValueError) as exc:
            raise FreeCADExportError("invalid vertex for %s: %s" % (_name(obj), exc))
        if not all(math.isfinite(value) for value in xyz):
            raise FreeCADExportError("non-finite vertex for %s" % _name(obj))
        flat.extend(xyz)
    indices = []
    for facet in facets:
        if len(facet) != 3:
            raise FreeCADExportError("non-triangular facet for %s" % _name(obj))
        for index in facet:
            if not isinstance(index, int) or index < 0 or index >= len(vertices):
                raise FreeCADExportError("invalid triangle index for %s" % _name(obj))
            indices.append(index)
    return flat, indices, mesh_shape


def _color(obj):
    value = getattr(getattr(obj, "ViewObject", None), "ShapeColor", None)
    if value is None:
        return DEFAULT_COLOR
    components = tuple(value[:3])
    numbers = [_number(component, "%s.ShapeColor" % _name(obj)) for component in components]
    if all(0 <= component <= 1 for component in numbers):
        numbers = [component * 255 for component in numbers]
    if any(component < 0 or component > 255 for component in numbers):
        raise FreeCADExportError("ShapeColor outside supported range for %s" % _name(obj))
    return "#%02X%02X%02X" % tuple(int(round(component)) for component in numbers)


def _part(obj, ordinal, parent_map, deflection, used_ids):
    mesh = _mesh(obj, deflection, parent_map)
    if not mesh or not mesh[1]:
        return None
    flat, indices, shape = mesh
    base_id = str(getattr(obj, "Name", None) or "part-%d" % ordinal)
    part_id = base_id
    suffix = 2
    while part_id in used_ids:
        part_id = "%s-%d" % (base_id, suffix)
        suffix += 1
    used_ids.add(part_id)
    part = {"id": part_id, "name": _label(obj), "color": _color(obj), "vertices": flat, "indices": indices, "sourceObject": _name(obj)}
    volume = getattr(shape, "Volume", None)
    if volume is not None:
        part["volumeMm3"] = _number(volume, "%s.Volume" % _name(obj))
        if part["volumeMm3"] < 0:
            raise FreeCADExportError("negative volume for %s" % _name(obj))
    material = getattr(obj, "Material", None)
    if isinstance(material, str) and material.strip():
        part["material"] = material
    return part


def _source_files(doc):
    filename = str(getattr(doc, "FileName", "") or "").replace("\\", "/")
    return [filename.rsplit("/", 1)[-1]] if filename else []


def _bbox(points):
    if not points:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "size": [0.0, 0.0, 0.0], "empty": True}
    minimum = [min(point[index] for point in points) for index in range(3)]
    maximum = [max(point[index] for point in points) for index in range(3)]
    return {"min": minimum, "max": maximum, "size": [maximum[i] - minimum[i] for i in range(3)], "empty": False}


def _read_metadata(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except Exception as exc:
        raise FreeCADExportError("cannot read metadata %s: %s" % (path, exc))
    if not isinstance(value, dict) or set(value) - {"schema", "run", "evaluation", "timeseries"}:
        raise FreeCADExportError("metadata has an invalid root schema")
    if "schema" in value and value["schema"] != SCHEMA:
        raise FreeCADExportError("metadata.schema must be %s" % SCHEMA)
    _finite_tree(value, "metadata")
    run = value.get("run", {})
    if not isinstance(run, dict) or set(run) - {"id", "title", "specVersion", "model", "status", "sourceFiles"}:
        raise FreeCADExportError("metadata.run has an invalid schema")
    for key in ("id", "title", "specVersion", "model", "status"):
        if key in run and not isinstance(run[key], str):
            raise FreeCADExportError("metadata.run.%s must be a string" % key)
    if run.get("status") not in (None, "unverified"):
        raise FreeCADExportError("metadata.run.status must remain unverified")
    if "sourceFiles" in run and (not isinstance(run["sourceFiles"], list) or not all(isinstance(item, str) for item in run["sourceFiles"])):
        raise FreeCADExportError("metadata.run.sourceFiles must be a string array")
    if value.get("evaluation") is not None:
        _validate_evaluation(value["evaluation"], "metadata.evaluation")
    if value.get("timeseries") is not None:
        _validate_timeseries(value["timeseries"], "metadata.timeseries")
    return value


def _validate_evaluation(value, path):
    allowed = {"status", "score", "maxScore", "gates", "metrics", "issues", "source"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise FreeCADExportError("%s has an invalid schema" % path)
    if value.get("status", "unverified") not in EVAL_STATES:
        raise FreeCADExportError("%s.status is invalid" % path)
    max_score = value.get("maxScore", 100)
    _number(max_score, path + ".maxScore", positive=True)
    score = value.get("score")
    if score is not None and (_number(score, path + ".score") < 0 or score > max_score):
        raise FreeCADExportError("%s.score is outside maxScore" % path)
    gates = value.get("gates", [])
    if not isinstance(gates, list):
        raise FreeCADExportError(path + ".gates must be an array")
    gate_ids = set()
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str) or not isinstance(gate.get("label"), str) or gate.get("status") not in GATE_STATES or gate["id"] in gate_ids:
            raise FreeCADExportError(path + ".gates has an invalid item")
        gate_ids.add(gate["id"])
    metrics = value.get("metrics", [])
    if not isinstance(metrics, list):
        raise FreeCADExportError(path + ".metrics must be an array")
    for metric in metrics:
        if not isinstance(metric, dict) or not isinstance(metric.get("label"), str):
            raise FreeCADExportError(path + ".metrics has an invalid item")
        metric_value = metric.get("value")
        if metric_value is not None and not isinstance(metric_value, str):
            _number(metric_value, path + ".metrics.value")
    issues = value.get("issues", [])
    if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
        raise FreeCADExportError(path + ".issues must be a string array")
    if "source" in value and not isinstance(value["source"], str):
        raise FreeCADExportError(path + ".source must be a string")


def _validate_timeseries(value, path):
    if not isinstance(value, dict) or set(value) != {"name", "xLabel", "xUnit", "series"} or not all(isinstance(value[key], str) for key in ("name", "xLabel", "xUnit")) or not isinstance(value["series"], list):
        raise FreeCADExportError("%s has an invalid schema" % path)
    for series in value["series"]:
        if not isinstance(series, dict) or set(series) != {"name", "unit", "values"} or not isinstance(series["name"], str) or not isinstance(series["unit"], str) or not isinstance(series["values"], list):
            raise FreeCADExportError("%s.series has an invalid item" % path)
        for pair in series["values"]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise FreeCADExportError("%s.series values must be [time,value]" % path)
            _number(pair[0], path + ".time")
            _number(pair[1], path + ".value")


def _finite_tree(value, path):
    if isinstance(value, float) and not math.isfinite(value):
        raise FreeCADExportError("%s contains a non-finite number" % path)
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_tree(item, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_tree(item, "%s[%d]" % (path, index))


def _validate_bundle(bundle):
    if bundle.get("schema") != SCHEMA or bundle["run"].get("status") != "unverified":
        raise FreeCADExportError("bundle schema or run status is invalid")
    _finite_tree(bundle, "bundle")
    run = bundle["run"]
    if not all(isinstance(run.get(key), str) for key in ("id", "title", "specVersion", "model")) or not isinstance(run.get("sourceFiles"), list):
        raise FreeCADExportError("bundle.run is invalid")
    for part in bundle["parts"]:
        if len(part["vertices"]) < 9 or len(part["vertices"]) % 3 or len(part["indices"]) < 3 or len(part["indices"]) % 3:
            raise FreeCADExportError("bundle part mesh is empty or malformed")
        if not re.match(r"^#[0-9A-Fa-f]{6}$", part["color"]):
            raise FreeCADExportError("bundle part color is invalid")
        count = len(part["vertices"]) // 3
        if any(not isinstance(index, int) or index < 0 or index >= count for index in part["indices"]):
            raise FreeCADExportError("bundle part indices are invalid")
    _validate_evaluation(bundle["evaluation"], "bundle.evaluation")
    if "timeseries" in bundle:
        _validate_timeseries(bundle["timeseries"], "bundle.timeseries")
