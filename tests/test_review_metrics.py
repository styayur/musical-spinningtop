import unittest

from scripts.artwork_review import canonical_geometry, decolored_svg


class ReviewMetricTests(unittest.TestCase):
    def test_palette_and_stroke_order_are_not_new_geometries(self):
        first = '<svg xmlns="http://www.w3.org/2000/svg" fill="none"><line x1="1" y1="0" x2="9" y2="0" stroke="red"/><circle cx="4" cy="4" r="2" stroke="blue"/></svg>'
        second = '<svg xmlns="http://www.w3.org/2000/svg" fill="none"><circle cx="4" cy="4" r="2" stroke="green"/><line x1="1.0" y1="0" x2="9" y2="0" stroke="black"/></svg>'
        self.assertEqual(canonical_geometry(first), canonical_geometry(second))
        self.assertNotEqual(decolored_svg(first), decolored_svg(second))

    def test_filled_occluder_retains_order_and_geometry(self):
        line = '<line x1="0" y1="5" x2="10" y2="5" stroke="red"/>'
        wash = '<rect x="3" y="3" width="4" height="4" fill="tan"/>'
        def svg(body):
            return '<svg xmlns="http://www.w3.org/2000/svg" fill="none">' + body + '</svg>'
        self.assertNotEqual(canonical_geometry(svg(line + wash)), canonical_geometry(svg(wash + line)))
        self.assertIn('#ffffff', decolored_svg(svg(line + wash)))
        self.assertNotEqual(canonical_geometry(svg(line)), canonical_geometry(svg(line + line)))

    def test_unsupported_shapes_cannot_silently_improve_metrics(self):
        with self.assertRaises(ValueError):
            canonical_geometry('<svg xmlns="http://www.w3.org/2000/svg"><text>Title</text></svg>')
