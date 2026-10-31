"""Optional long-hair extraction bounds cannot change the legacy default."""
import unittest
from reference_surface import extraction_lower_y

class ExtractionBounds(unittest.TestCase):
    def test_legacy_bound_exact(self):
        for centre in [1.61,1.67]:self.assertEqual(extraction_lower_y(centre),centre-.34)
    def test_opt_in_preserves_complete_lower_tip(self):
        self.assertEqual(extraction_lower_y(1.65,1.05),1.05)
        self.assertLess(extraction_lower_y(1.65,1.05),extraction_lower_y(1.65))
    def test_invalid_or_unbounded_inputs_fail_closed(self):
        for value in [float('nan'),float('inf'),-float('inf'),-.5,1.64]:
            with self.assertRaises(ValueError):extraction_lower_y(1.65,value)

if __name__=='__main__':unittest.main()
