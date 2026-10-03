# Domain Glossary

Terms used across EquiContracts. These have precise meanings in Indian construction
contracting and should not be paraphrased by agents or documentation generators.

| Term | Full form | Meaning |
|------|-----------|---------|
| BG | Bank Guarantee | Financial instrument issued by a bank on behalf of the contractor. The client can invoke (claim) it if the contractor defaults. |
| PBG | Performance Bank Guarantee | BG specifically securing performance obligations under a work order. |
| Mobilization BG | — | BG securing advance payments made to the contractor before work begins. |
| Retention BG | — | BG replacing cash retention deducted from running bills. |
| WCC | Work Completion Certificate | Issued when the contractor completes the physical scope of a work order. |
| DLP | Defect Liability Period | Post-completion period (typically 12–24 months) during which the contractor must fix defects at own cost. |
| RA bill | Running Account Bill | Progressive (interim) payment claim submitted by contractor as work advances. Becomes a "certified invoice" once the client/PMC certifies the quantities. |
| Proforma invoice | — | The contractor's claim before certification. Distinct from the tax invoice issued after certification. |
| Tax invoice | — | GST-compliant invoice issued by the contractor after the RA bill is certified. |
| TDS | Tax Deducted at Source | Income tax withheld by the client from contractor payments (typically 1–2%). |
| WCT | Works Contract Tax | State-level tax on works contracts (subsumed into GST in most states post-2017, but legacy deductions still appear in reconciliations). |
| PMC | Project Management Consultant | Third-party firm hired by the client to supervise the contractor. Has read access to verified project data. |
| Annexure | — | A supporting document required per work order terms (e.g. safety certificate, insurance policy, material test report). Defined at WO level, tracked per proforma submission. |
| Client Clock | Certification SLA | The number of days from contractor submission to client/PMC certification, as defined in the work order. Breach means the client is holding up payment. |
| GSTIN | GST Identification Number | 15-digit alphanumeric. First two digits = state code. Determines whether CGST+SGST or IGST applies. |
| CGST / SGST | Central / State GST | Apply when buyer and seller are in the same state (same first-2 digits of GSTIN). |
| IGST | Integrated GST | Applies on inter-state supply. Mutually exclusive with CGST+SGST. |
| Debit note | — | Issued by client to contractor for recoveries (defects, penalties, advance adjustments). |
| MoM | Minutes of Meeting | Site meeting records. Often contain instructions that create or modify obligations. |
| LOI | Letter of Intent | Precedes the formal work order. May contain BG requirements. |

## Conventions in this codebase

- Money is always `Decimal` (Python) / `numeric(18,2)` (Postgres). Never float.
- Dates from Indian documents are day-first (`DD.MM.YYYY` or `DD/MM/YYYY`). Always store ISO-8601 plus `raw_text`.
- BG has **two** date fields: `expiry_date` (guarantee validity) and `claim_expiry_date` (period for invocation after expiry). These can differ by a year or more.
- `null` means "not present in source document" — never substitute `0.00`.
