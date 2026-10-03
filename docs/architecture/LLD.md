# EquiContracts — Low Level Design

---

## 1. Entity relationship

Corrected for dual-sided access: `org` now carries a type, and `project_participant` grants
client/PMC read access without making them tenants of the contractor's data.

```mermaid
erDiagram
    ORG ||--o{ APP_USER : employs
    ORG ||--o{ PROJECT : owns
    PROJECT ||--o{ PROJECT_PARTICIPANT : grants_access_to
    ORG ||--o{ PROJECT_PARTICIPANT : participates_in
    PROJECT ||--o{ WORK_ORDER : contains
    PROJECT ||--o{ DOCUMENT : receives
    PROJECT ||--o{ PROJECT_MODULE : enables

    WORK_ORDER ||--o{ BANK_GUARANTEE : secured_by
    WORK_ORDER ||--o{ ANNEXURE_REQUIREMENT : mandates
    WORK_ORDER ||--o{ PROFORMA_INVOICE : billed_via
    WORK_ORDER ||--o| WCC : completed_by
    WORK_ORDER ||--o{ WARRANTY : warranted_by
    WORK_ORDER ||--o{ EXCEPTION : raises

    BANK_GUARANTEE ||--o{ BG_EVENT : logs

    PROFORMA_INVOICE ||--o{ ANNEXURE_SUBMISSION : includes
    PROFORMA_INVOICE ||--o| CERTIFICATION : certified_as
    CERTIFICATION ||--o| TAX_INVOICE : invoiced_as
    TAX_INVOICE ||--o{ PAYMENT_RECEIPT : paid_by
    TAX_INVOICE ||--o{ DEDUCTION_LINE : reduced_by

    DOCUMENT ||--o{ EXTRACTED_FIELD : yields
    DOCUMENT }o--|| DOCUMENT_CLASSIFICATION : classified_as

    ORG {
        uuid id PK
        text name
        text org_type "contractor|client|pmc|internal"
    }
    APP_USER {
        uuid id PK
        uuid org_id FK
        text email
        text role "contractor_admin|contractor_user|client_mgmt|client_pm|pmc_user|ec_admin"
    }
    PROJECT {
        uuid id PK
        uuid owner_org_id FK "always a contractor org"
        text name
        text project_code "EC-MUM-101"
        text inbound_email
    }
    PROJECT_PARTICIPANT {
        uuid project_id FK
        uuid org_id FK
        text role "client|pmc"
        text data_scope "verified_only"
    }
    WORK_ORDER {
        uuid id PK
        uuid project_id FK
        text wo_number "HVAC/WO/042"
        text trade "HVAC"
        numeric value
        integer certification_sla_days
        text bg_clause_conditionality
        text retention_bg_ratio_clause
    }
    BANK_GUARANTEE {
        uuid id PK
        uuid work_order_id FK
        text bg_type "mobilization|performance|retention"
        numeric value
        date expiry_date
        date claim_expiry_date "SEPARATE and LATER"
        text status "active|expiring|idle|redundant|released"
    }
    ANNEXURE_REQUIREMENT {
        uuid id PK
        uuid work_order_id FK
        text annexure_name
        boolean mandatory
    }
    ANNEXURE_SUBMISSION {
        uuid id PK
        uuid proforma_invoice_id FK
        uuid annexure_requirement_id FK
        text status "present|missing|na"
    }
    PROFORMA_INVOICE {
        uuid id PK
        uuid work_order_id FK
        text number
        numeric value
        date submitted_at
    }
    CERTIFICATION {
        uuid id PK
        uuid proforma_invoice_id FK
        text ra_bill_number
        numeric certified_amount
        date certified_at
    }
    TAX_INVOICE {
        uuid id PK
        uuid certification_id FK
        text seller_gstin
        text buyer_gstin
        numeric cgst
        numeric sgst
        numeric igst
        numeric total_value
    }
    PAYMENT_RECEIPT {
        uuid id PK
        uuid tax_invoice_id FK
        numeric amount_received
        date received_at
        text source "manual|excel_import"
    }
    DEDUCTION_LINE {
        uuid id PK
        uuid tax_invoice_id FK
        text category "tds|wct|retention|advance|cement_recovery|debris|other"
        numeric amount
        boolean disputed
    }
    DOCUMENT {
        uuid id PK
        uuid project_id FK
        text sha256
        text source
        integer reminder_sequence_number
    }
    DOCUMENT_CLASSIFICATION {
        uuid document_id FK
        text category "routine|core_evidence|potential_dispute|bg|proforma|certified|wcc|warranty|payment_advice|delay_mom"
        numeric confidence
    }
    EXTRACTED_FIELD {
        uuid id PK
        uuid document_id FK
        text field_name
        text field_value
        text state "ai_extracted|needs_review|verified"
        boolean is_financial
        numeric confidence
        text model_version
        uuid verified_by FK
    }
    EXCEPTION {
        uuid id PK
        uuid work_order_id FK
        text rule_id
        text severity
        numeric rupees_at_risk
        text action_owner "contractor|client_pm|pmc"
        text state "open|acknowledged|resolved|dismissed"
        timestamp due_at
    }
    WCC {
        uuid id PK
        uuid work_order_id FK
        date completion_date
        date final_bill_date
    }
    WARRANTY {
        uuid id PK
        uuid work_order_id FK
        date start_date
        date expiry_date
        integer tenure_months
    }
```

---

## 2. Verification state machine

Three states, from the product spec. The boolean I originally proposed can't express
"AI extracted but not yet flagged for review", which matters for confident non-financial
fields.

```mermaid
stateDiagram-v2
    [*] --> ai_extracted : extractor writes field

    ai_extracted --> needs_review : is_financial = true<br/>(ALWAYS, any confidence)
    ai_extracted --> needs_review : confidence < 0.90
    ai_extracted --> verified : non-financial<br/>AND confidence >= 0.90

    needs_review --> verified : contractor confirms
    needs_review --> needs_review : contractor corrects value
    needs_review --> [*] : contractor rejects document

    verified --> needs_review : contradicted by a later document

    note right of needs_review
        Only path to verified for
        any financial field.
        DB constraint enforced.
    end note

    note right of verified
        Only state visible on
        the client dashboard.
    end note
```

The `verified --> needs_review` transition matters and is easy to forget: if a corrected
BG amendment arrives later, the previously verified value must be pulled back for
re-confirmation rather than silently overwritten.

---

## 3. Sequence — email ingestion to verified field

```mermaid
sequenceDiagram
    autonumber
    participant CT as Contractor
    participant EP as Email provider
    participant API
    participant S3 as Object storage
    participant CLS as Classifier
    participant EXT as Extractor
    participant RQ as Review queue
    participant DB as Postgres
    participant RE as Rules engine

    CT->>EP: Marks project email on WO/BG/invoice thread
    EP->>API: Inbound webhook (HMAC signed)
    API->>API: Verify signature
    alt address matches no project
        API->>DB: Insert inbound_quarantine
        API-->>EP: 202 quarantined
    else matched
        API->>S3: Store attachments (immutable)
        API->>DB: Insert document + sha256
        API->>CLS: Classify
        CLS->>DB: document_classification
        API->>EXT: Extract (5 doc types only)
        EXT->>EXT: Schema-constrained parse
        alt financial field OR confidence < 0.90
            EXT->>RQ: state = needs_review
            RQ->>CT: Appears in Inbox Review
            CT->>DB: Confirm or correct → verified
        else non-financial, high confidence
            EXT->>DB: state = verified
        end
        DB->>RE: Verified data changed
        RE->>DB: Write exceptions + action_owner
    end
```

Step ordering matters at the signature check: verify before doing anything else. An
unsigned inbound endpoint is an open door for injecting forged documents into any
contractor's project.

---

## 4. Sequence — idle BG detection

This is a rule worth showing in full because the founder spec defines it precisely and it's
non-obvious: a BG is *idle* when the work is finished but the guarantee is still live and
still costing bank commission.

```mermaid
sequenceDiagram
    autonumber
    participant T as Temporal (daily)
    participant DB as Postgres
    participant R as Rules engine
    participant N as Notifier

    T->>DB: Fetch BGs where status = active
    DB-->>R: BG rows + linked WO + final certification
    R->>R: final_certified_bill_date exists?
    alt yes AND bg.expiry_date > final_certified_bill_date
        R->>DB: status = 'idle'
        R->>DB: exception(rule=bg_idle, owner=contractor,<br/>rupees_at_risk=bg.value)
        R->>N: "BG still live after final bill — claim release"
    else expiry within 30 days
        R->>DB: status = 'expiring'
        R->>N: Renewal alert
    end
    R->>DB: Separately: claim_expiry_date countdown
    note over R,DB: claim_expiry is its own clock.<br/>Expiry passing does NOT end claim exposure.
```

---

## 5. Sequence — payment mismatch via Excel import

```mermaid
sequenceDiagram
    autonumber
    participant CT as Contractor
    participant API
    participant SP as Spreadsheet parser
    participant DB as Postgres
    participant R as Rules engine

    CT->>API: Upload Tally/Zoho export (xlsx/csv)
    API->>SP: Parse (openpyxl, NOT a vision model)
    SP->>SP: Map columns to template
    SP-->>CT: Preview + unmapped column warnings
    CT->>API: Confirm mapping
    API->>DB: Insert payment_receipt + deduction_line
    DB->>R: Reconcile
    R->>R: certified vs tax_invoice vs received<br/>vs deductions vs outstanding
    alt variance beyond tolerance
        R->>DB: exception(rule=payment_mismatch)
        R->>R: interest exposure =<br/>value x overdue_days x rate / 365
    end
```

Spreadsheets go through a structured parser, never a vision model. The real reconciliation
files are genuine xlsx with formulas — sending them to a vision model costs more and loses
precision that's already available for free.

---

## 6. Exception lifecycle

```mermaid
stateDiagram-v2
    [*] --> open : rule fires
    open --> acknowledged : action_owner opens it
    acknowledged --> resolved : underlying data corrected
    open --> escalated : SLA breached, no ack
    escalated --> acknowledged
    escalated --> resolved
    open --> dismissed : owner gives a reason
    dismissed --> [*]
    resolved --> [*]
    resolved --> open : recurs on new data

    note right of dismissed
        Reason is mandatory.
        Dismissals are the tuning
        signal for rule noise.
    end note
```

---

## 7. Module composition on the client dashboard

```mermaid
flowchart TB
    subgraph Client["Client Dashboard — read only, verified only"]
        AP["All Projects"]
        CI["Critical Items"]
        CH["Contractor-wise Health"]
    end

    subgraph Sources["Derived from"]
        BGE["BG Exposure"]
        CAG["Certification Ageing"]
        PMM["Payment Mismatch"]
        WCCW["WCC / Warranty Status"]
        EVR["Evidence Readiness"]
        RSA["Resolution Availability"]
    end

    BGE --> CI
    CAG --> CI
    PMM --> CI
    WCCW --> CH
    EVR --> CH
    RSA --> AP
    CI --> AP
    CH --> AP
```

Status vocabulary, fixed across the whole product so the two sides never argue about what a
label means: `healthy`, `critical`, `needs_verification`, `pending_contractor`,
`pending_client_pmc`, `resolved`.

That `pending_client_pmc` value is doing quiet diplomatic work — it lets the platform state
that a delay sits with the client without editorialising, because the certification clock
is simply a fact derived from the WO's own SLA.
