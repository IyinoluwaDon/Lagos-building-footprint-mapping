# Lagos export archive

This folder holds the supplied Ikeja source exports and their quality records. Keep the footprint GeoJSON, matching summary CSV, and matching boundary GeoJSON (when available) together. The supplied export currently lacks its boundary file, which is why exact containment is reported as not verified.

`analyze_export.py` accepts explicit file paths, so it also works with other Lagos LGAs and cutoffs without replacing the Ikeja source data. It writes area-specific outputs by default for non-Ikeja inputs. `QA_REPORT.md`, `qa_summary.json`, and `qa_run.log` record the latest audit; `unit_tests.log` records the focused automated tests. See `DATA_DICTIONARY.md` and `docs/METHOD_AND_REPRODUCIBILITY.md` for field meanings and the full procedure.
