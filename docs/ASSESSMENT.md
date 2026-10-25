# Independent project review

This assessment covers two separate results: the supplied Open Buildings V3 Ikeja export and the project-trained SpaceNet U-Net. The U-Net has now been trained on a compact real-data subset and evaluated on separate, unseen SpaceNet scenes. Validation IoU/F1 were 0.516/0.680; test IoU/F1 were 0.597/0.748 at threshold 0.5. These are in-domain Las Vegas metrics. A compatible high-resolution Lagos image and independent Lagos reference labels are still needed to measure transfer performance in Lagos. The U-Net results remain separate from the 53,437-feature Ikeja baseline.

## Rating for the supplied Open Buildings V3 export and QA deliverable: 7/10

This rating is scoped to the supplied Ikeja Open Buildings export and QA deliverable; it is not a score for U-Net accuracy. The compact U-Net run proves that training and separate in-domain testing work, while its small subset and different test city do not establish Lagos accuracy.

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
