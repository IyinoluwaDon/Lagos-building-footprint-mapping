# Independent project review

## Rating after the current upgrades: 7/10 as a reproducible project demonstration

| Dimension | Score | Reason |
|---|---:|---|
| Project scope and provenance | 8/10 | Clear Lagos LGA scope with named Earth Engine source layers and license metadata |
| Reproducibility | 8/10 | Colab export, parameterized confidence cutoff, source hashes, dependency pins, reports, and repeatable local commands |
| Data quality controls | 8/10 | Count, score, ID, coordinate, ring, area, topology, and optional exact-boundary checks |
| Local detection accuracy evidence | 2/10 | No independent Ikeja reference labels or field survey were supplied |
| Communication and presentation readiness | 8/10 | Project narrative, speaker notes, data caveats, figures, and an editable slide deck |

The overall score reflects a strong, explainable geospatial data pipeline. It is not a score for model accuracy. The low accuracy-evidence score is the main research limitation and prevents defensible claims about completeness, precision, or recall.

## Required next evidence for a stronger research claim

1. Add the matching boundary GeoJSON and rerun the exact containment check.
2. Define a reproducible sample of map locations or buildings and compare predictions to an independent, recent reference source or field verification.
3. Report precision, recall, omission/commission errors, and uncertainty for that sample, with the sampling method and reference date.
4. Only then compare confidence cutoffs or describe local model performance.
