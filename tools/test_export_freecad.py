import json
import importlib.util
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from export_freecad import FreeCADExportError, export_document

TEST_TMP_ROOT = Path(os.environ.get("VIEWER_TEST_TMP", tempfile.gettempdir()))
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

try:
    import FreeCAD as App
    import Part
except ImportError:  # Normal Python test runs do not ship FreeCAD.
    App = None
    Part = None


class Vector:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class Placement:
    def __init__(self, dx=0, dy=0, dz=0):
        self.dx, self.dy, self.dz = dx, dy, dz

    def multVec(self, point):
        return Vector(point.x + self.dx, point.y + self.dy, point.z + self.dz)


class Shape:
    def __init__(self, vertices, facets, volume=1.0, placement=None):
        self.vertices = vertices
        self.facets = facets
        self.Volume = volume
        self.Placement = placement or Placement()

    def copy(self):
        return Shape(self.vertices, self.facets, self.Volume, self.Placement)

    def tessellate(self, _deflection):
        return [self.Placement.multVec(vertex) for vertex in self.vertices], self.facets


class View:
    def __init__(self, visible=True, color=(0.7, 0.7, 0.7)):
        self.Visibility = visible
        self.ShapeColor = color


class Object:
    def __init__(self, name, shape=None, type_id="Part::Feature", label=None, visible=True, color=(0.7, 0.7, 0.7), placement=None, global_placement=None):
        self.Name = name
        self.Label = label or name
        self.TypeId = type_id
        self.Shape = shape
        self.ViewObject = View(visible, color)
        self.Placement = placement or Placement()
        self._global_placement = global_placement or self.Placement
        self.Group = []

    def getGlobalPlacement(self):
        return self._global_placement


class Document:
    def __init__(self, objects, filename="C:/private/design.FCStd"):
        self.Objects = objects
        self.Name = "MockDoc"
        self.Label = "Mock document"
        self.FileName = filename

    def getObject(self, name):
        return next((obj for obj in self.Objects if obj.Name == name), None)


def triangle(placement=None):
    return Shape([Vector(0, 0, 0), Vector(1, 0, 0), Vector(0, 1, 0)], [(0, 1, 2)], 2.5, placement)


class ExportTests(unittest.TestCase):
    def test_documented_importlib_loader_has_no_freecad_import_requirement(self):
        path = Path(__file__).parent / "export_freecad.py"
        spec = importlib.util.spec_from_file_location("freecad_export_test_loader", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.export_document))

    def run_export(self, doc, metadata=None, objects=None):
        token = uuid.uuid4().hex
        outpath = TEST_TMP_ROOT / ("test-" + token + ".json")
        metadata_path = TEST_TMP_ROOT / ("metadata-" + token + ".json") if metadata is not None else None
        try:
            if metadata_path is not None:
                metadata_path.write_text(metadata, encoding="utf-8")
            bundle = export_document(doc, outpath, metadata_path, objects=objects)
            self.assertEqual(bundle, json.loads(outpath.read_text(encoding="utf-8")))
            return bundle
        finally:
            for path in (outpath, metadata_path):
                if path is not None:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass

    def test_body_children_are_not_duplicated_and_global_placement_is_used(self):
        body = Object("Body", triangle(), "PartDesign::Body", color=(0.25, 0.5, 0.75), placement=Placement(10, 20, 30))
        child = Object("Pad", triangle(Placement(100, 100, 100)))
        body.Group = [child]
        bundle = self.run_export(Document([body, child]))
        self.assertEqual(len(bundle["parts"]), 1)
        part = bundle["parts"][0]
        self.assertEqual(part["color"], "#4080BF")
        self.assertEqual(part["indices"], [0, 1, 2])
        self.assertEqual(part["vertices"], [10.0, 20.0, 30.0, 11.0, 20.0, 30.0, 10.0, 21.0, 30.0])
        self.assertEqual(bundle["run"]["sourceFiles"], ["design.FCStd"])

    def test_explicit_link_is_rejected_and_hidden_shape_is_skipped(self):
        hidden = Object("Hidden", triangle(), visible=False)
        link = Object("Instance", None, "App::Link")
        with self.assertRaisesRegex(FreeCADExportError, "App::Link"):
            self.run_export(Document([hidden, link]), objects=[link])
        self.assertEqual(self.run_export(Document([hidden]))["parts"], [])

    def test_unknown_visibility_requires_explicit_selection(self):
        unknown = Object("Headless", triangle())
        del unknown.ViewObject
        with self.assertRaisesRegex(FreeCADExportError, "visibility is unavailable"):
            self.run_export(Document([unknown]))
        self.assertEqual(len(self.run_export(Document([unknown]), objects=[unknown])["parts"]), 1)

    def test_metadata_provenance_spec_version_and_timeseries_are_preserved(self):
        metadata = json.dumps({
            "schema": "freecad-benchmark/v1",
            "run": {"specVersion": "2.0", "title": "Sidecar"},
            "evaluation": {
                "status": "self-reported",
                "score": 75,
                "source": "verification.json",
                "gates": [{"id": "G1", "label": "fit", "status": "pending"}],
                "metrics": [{"label": "fit", "value": 0.8}],
                "issues": ["needs review"],
            },
            "timeseries": {
                "name": "load", "xLabel": "time", "xUnit": "s",
                "series": [{"name": "force", "unit": "N", "values": [[0, 0], [1, 2.5]]}],
            },
        })
        bundle = self.run_export(Document([Object("Part", triangle())]), metadata)
        self.assertEqual(bundle["run"]["specVersion"], "2.0")
        self.assertEqual(bundle["evaluation"]["source"], "verification.json")
        self.assertEqual(bundle["evaluation"]["status"], "self-reported")
        self.assertEqual(bundle["timeseries"]["series"][0]["values"][1], [1, 2.5])

    def test_bad_metadata_is_rejected(self):
        with self.assertRaisesRegex(FreeCADExportError, "non-finite|metadata"):
            self.run_export(Document([Object("Part", triangle())]), '{"evaluation":{"score":NaN}}')
        with self.assertRaisesRegex(FreeCADExportError, "gates"):
            self.run_export(Document([Object("Part", triangle())]), '{"evaluation":{"gates":[{"id":"G1","label":"x","status":"self-reported"}]}}')


@unittest.skipUnless(App is not None, "FreeCAD is available only in FreeCADCmd")
class RealFreeCADPlacementTests(unittest.TestCase):
    def test_rotated_translated_shape_is_not_transformed_twice(self):
        doc = App.newDocument("export_rotation_test")
        outpath = TEST_TMP_ROOT / ("rotation-" + uuid.uuid4().hex + ".json")
        try:
            box = doc.addObject("Part::Box", "RotatedBox")
            box.Length, box.Width, box.Height = 10, 20, 30
            box.Placement = App.Placement(App.Vector(100, 20, 30), App.Rotation(App.Vector(0, 0, 1), 90))
            doc.recompute()
            bundle = export_document(doc, outpath, objects=[box])
            for got, expected in zip(bundle["assembly"]["bboxMm"]["min"], [80, 20, 30]):
                self.assertAlmostEqual(got, expected, places=6)
            for got, expected in zip(bundle["assembly"]["bboxMm"]["max"], [100, 30, 60]):
                self.assertAlmostEqual(got, expected, places=6)
        finally:
            outpath.unlink(missing_ok=True)
            App.closeDocument(doc.Name)

    def test_nested_part_uses_global_placement_once(self):
        doc = App.newDocument("export_placement_test")
        try:
            part = doc.addObject("App::Part", "Assembly")
            part.Placement.Base = App.Vector(1000, 2000, 3000)
            box = doc.addObject("Part::Box", "Box")
            box.Length, box.Width, box.Height = 10, 20, 30
            box.Placement.Base = App.Vector(100, 200, 300)
            part.addObject(box)
            doc.recompute()
            outpath = TEST_TMP_ROOT / ("real-" + uuid.uuid4().hex + ".json")
            try:
                bundle = export_document(doc, outpath)
            finally:
                try:
                    outpath.unlink()
                except FileNotFoundError:
                    pass
            self.assertEqual(bundle["parts"][0]["vertices"][:3], [1100.0, 2200.0, 3300.0])
            self.assertEqual(bundle["assembly"]["bboxMm"]["max"], [1110.0, 2220.0, 3330.0])
        finally:
            App.closeDocument(doc.Name)


if __name__ == "__main__":
    unittest.main()
