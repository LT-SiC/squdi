"""Static regression tests for editor positioning and preview integration."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class StaticUIRegressions(unittest.TestCase):
    def test_circuit_gates_stay_absolutely_positioned(self):
        css = (ROOT / 'frontend/styles.css').read_text()
        self.assertIn('.canvas-gate{position:absolute', css)
        self.assertNotIn('.palette-gate,.canvas-gate{position:relative}', css)

    def test_rectangular_envelope_has_vertical_edges(self):
        js = (ROOT / 'frontend/app.js').read_text()
        self.assertIn("if(mode==='rect')return", js)
        self.assertIn('function pulseShapePath', js)

    def test_pulse_waveforms_do_not_stroke_bottom_closure(self):
        js = (ROOT / 'frontend/app.js').read_text()
        self.assertIn('<path d="${path}"', js)
        self.assertIn('<path d="${echo}"', js)
        self.assertNotIn('<path d="${path} Z"', js)

    def test_measurement_layout_keeps_controls_together(self):
        html = (ROOT / 'frontend/index.html').read_text()
        self.assertIn('measurement-overview',html)
        self.assertIn('scan-workspace-grid',html)
        self.assertLess(html.index('class="panel spin-register-panel"'),html.index('class="panel setup-code-panel"'))
        self.assertLess(html.index('class="measurement-controls"'),html.index('class="scan-panel"'))
        self.assertLess(html.index('class="scan-panel"'),html.index('class="linecuts-panel"'))

    def test_register_asset_is_served(self):
        from server import STATIC
        self.assertEqual(STATIC.get('/measurement_extras.js'), 'measurement_extras.js')
        self.assertTrue((ROOT/'frontend/measurement_extras.js').is_file())

if __name__=='__main__':unittest.main()
