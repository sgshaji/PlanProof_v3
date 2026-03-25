# BCC Real Data Provenance

## Source

- **Authority:** Birmingham City Council (BCC) Planning Portal
- **URL:** <https://planningapplications.birmingham.gov.uk/>
- **Record type:** Public planning application records (Householder Planning Applications)
- **Downloaded:** 2026-03-25

## Dataset Composition

- 10 planning application sets
- 5 with status **PA Held**, 5 with status **PA Validated**
- 39 total files (PDFs, PNGs, JPGs)
- Application types: Householder Planning Application (full-form submissions)

## Application IDs

| Application ID | Status       | Files | Notes                              |
|----------------|--------------|-------|------------------------------------|
| 2025 00532     | PA Held      | 3     | Form + 2 drawings (PDF, JPG)       |
| 2025 00768     | PA Held      | 4     | Form + 2 drawings + private corr.  |
| 2025 00841     | PA Held      | 6     | App form + 5 architectural drawings|
| 2025 00867     | PA Held      | 4     | Form + 1 PDF drawing + 2 PNGs      |
| 2025 03008     | PA Held      | 3     | Form + 1 PDF drawing + 1 PNG       |
| 2025 07100     | PA Validated | 7     | Form + 6 drawings                  |
| 2025 07200     | PA Validated | 3     | Form + 2 drawings                  |
| 2026 00041     | PA Validated | 2     | Form + 1 drawing                   |
| 2026 00068     | PA Validated | 3     | Form + 2 drawings                  |
| 2026 00085     | PA Validated | 4     | Form + 3 drawings                  |

**Total: 39 files across 10 applications.**

## File Type Breakdown

| Type                          | Count | Classification |
|-------------------------------|-------|----------------|
| Planning Application Form PDF | 10    | FORM — contains PII |
| Householder App Form PDF      | 1     | FORM — contains PII |
| Private Correspondence PDF    | 1     | FORM — contains PII |
| Architectural Drawing PDF     | 22    | DRAWING — safe      |
| Drawing / Photo PNG           | 3     | DRAWING — safe      |
| Drawing / Photo JPG           | 2     | DRAWING — safe      |

## PII Notice

Planning application forms (typically pages 1–2 of the BCC householder form) contain
personal information in the following fields:

- Applicant full name and address
- Applicant phone number and email address
- Agent full name, company, address, phone, and email
- Site address (also appears on drawing title blocks)
- Applicant / agent signature on the planning certificate

Architectural drawings and plans do **not** contain PII.  They show only building geometry,
dimensions, and site layout.

See [`pii_manifest.json`](pii_manifest.json) for the per-file PII classification,
SHA-256 checksums, and copy disposition for every file in this directory.

## Anonymisation Approach

Because `pymupdf` is not available on the ARM64 Windows development environment,
programmatic in-place PDF redaction is not feasible.  The chosen approach is:

1. **Manifest-first:** every file is classified and documented in `pii_manifest.json`
   before any copying takes place.
2. **Safe-copy:** drawing files (DRAWING class) are copied verbatim to `data/anonymised/`,
   preserving the application-folder structure.
3. **Manual gate:** form files remain in `data/raw/` only.  They are listed as
   `"disposition": "manual_redaction_required"` in the manifest.  They must be
   manually redacted (e.g., with Adobe Acrobat or a PDF editor) before being placed
   in a shared or published context.

The script that produced this classification and the anonymised copies is
`scripts/anonymise_bcc_data.py`.

## Usage Restrictions

- Data is sourced from public planning records and is freely accessible via the BCC portal.
- Used for academic research (MSc Dissertation — PlanProof project).
- The PII contained in form documents must not be shared, published, or committed to a
  public repository.
- Anonymised copies in `data/anonymised/` (drawings only) are safe for sharing.
- `data/raw/` must remain in `.gitignore` to prevent accidental PII exposure.
