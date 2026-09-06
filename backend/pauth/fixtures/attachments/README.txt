Dummy chart files for local prior-auth testing. Upload these on New case.
PDF is preferred; .txt copies are also accepted.

Infliximab / Aetna / J1745 / M05.9  (patient A.R.)
  AR-rheumatology-progress-note.pdf
  AR-quantiferon-lab.pdf
  AR-incomplete-note.pdf          (use alone to create Matcher gaps)

MRI brain / UnitedHealthcare / 70553 / R56.9  (patient B.K.)
  BK-neurology-mri-consult.pdf

Injectafer / Cigna / J1439 / D50.9  (patient L.M.)
  LM-hematology-progress-note.pdf
  LM-iron-studies-lab.pdf

Regenerate PDFs after editing a .txt:
  cd backend && uv run --extra dev python scripts/render_attachment_pdfs.py
