"""Regressions for the publisher routes used by the offline metadata audit."""
from pathlib import Path
import copy
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("featurecut_metadata", Path(__file__).with_name("metadata.py"))
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class PublisherRoutes(unittest.TestCase):
    def records(self):
        return [metadata.load(name) for name in (
            "reference_verification.csv", "literature_matrix.csv", "external_resources.csv")]

    def test_current_records(self):
        metadata.validate_primary_routes(*self.records())

    def corrupt(self, key, index, key_field, url_field):
        rows = copy.deepcopy(self.records())
        identifier, good_url = metadata.PRIMARY_PDFS[key]
        wanted = identifier if index == 2 else key
        row = next(row for row in rows[index] if row[key_field] == wanted)
        row[url_field] = good_url.replace("begoli.pdf", "akidau.pdf").replace("camacho-rodriguez.pdf", "liu.pdf")
        with self.assertRaises(AssertionError):
            metadata.validate_primary_routes(*rows)

    def test_watermarks_reference(self):
        self.corrupt("watermarks", 0, "bib_key", "primary_record")

    def test_watermarks_literature(self):
        self.corrupt("watermarks", 1, "id", "primary_url")

    def test_watermarks_resource(self):
        self.corrupt("watermarks", 2, "immutable_scientific_identifier", "scholarly_or_official_url")

    def test_featurepipelines_reference(self):
        self.corrupt("featurepipelines", 0, "bib_key", "primary_record")

    def test_featurepipelines_literature(self):
        self.corrupt("featurepipelines", 1, "id", "primary_url")

    def test_featurepipelines_resource(self):
        self.corrupt("featurepipelines", 2, "immutable_scientific_identifier", "scholarly_or_official_url")


if __name__ == "__main__":
    unittest.main()
