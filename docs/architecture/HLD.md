# EquiContracts — High Level Design

> **Product principle:** Contractor feeds. Client sees. Platform structures, verifies and surfaces exceptions.
>
> The Client must never become a data-entry user. The Contractor must never feel they are
> filling in another ERP. The platform quietly converts routine project communication into
> structured dashboards.

---

## 1. System context

Note the asymmetry: the contractor writes, the client and PMC only read. This is the whole
product thesis expressed as an access model.

```mermaid
flowchart TB
    subgraph Feeders["WRITES — Contractor side"]
        CA["Contractor Admin"]
        CPU["Contractor Project User"]
    end

    subgraph Viewers["READS ONLY — Client / PMC side"]
        CSM["Client Senior Management"]
        CPM["Client Project Manager"]
        PMC["PMC User"]
    end

    subgraph Ingest["Ingestion"]
        MAIL["Dedicated project email<br/>projects+{alias}@equicontracts…"]
        UP["Manual upload"]
        XL["Accounting export<br/>Excel / CSV"]
    end

    subgraph Platform["EquiContracts Platform"]
        API["API + Access Control"]
        CLASSIFY["AI Classification"]
        EXTRACT["AI Extraction"]
        REVIEW["Contractor Verification<br/>ai_extracted → needs_review → verified"]
        RULES["Rules Engine<br/>deterministic"]
        GEN["Resolution Generation<br/>Phase 5"]
    end

    subgraph Store["Data"]
        PG[("Postgres + RLS")]
        S3[("Object storage<br/>immutable")]
    end

    CA --> API
    CPU --> API
    CPU --> REVIEW

    MAIL --> CLASSIFY
    UP --> CLASSIFY
    XL --> EXTRACT

    CLASSIFY --> EXTRACT
    EXTRACT --> REVIEW
    REVIEW -->|verified only| PG
    CLASSIFY -.raw file.-> S3

    PG --> RULES
    RULES --> PG
    PG --> GEN

    API --> PG
    CSM -->|verified data only| API
    CPM -->|verified data only| API
    PMC -->|verified data only| API
```

**The single most important edge in this diagram** is `REVIEW -->|verified only| PG`.
Unverified AI output never reaches a client-facing dashboard. That constraint is what makes
the platform credible to both sides at once: the client trusts the numbers because the
contractor confirmed them, and the contractor accepts the dashboard because it is built
from their own submissions.

---

## 2. Master data backbone

Every record in the system resolves to this chain. If a record can't be placed on it,
the record is malformed.

```mermaid
flowchart LR
    P["Project<br/>Lodha Supremus"] --> PID["Project ID<br/>EC-MUM-101"]
    PID --> WO["Work Order<br/>HVAC/WO/042"]
    WO --> C["Contractor<br/>Cool Air HVAC"]
    C --> M["Module<br/>BG Verify"]
    M --> DT["Document Type<br/>Retention BG"]
    DT --> D["Date"]
    D --> S["Status<br/>Expiring in 12 days"]
    S --> AO["Action Owner<br/>Contractor"]
```

`action_owner` defaults to the Contractor on every exception — the contractor is the party
who feeds the platform, so they are the party who resolves gaps. Client and PMC values
exist for the cases where the blockage genuinely sits with them (certification ageing being
the obvious one), and those cases are exactly what the client dashboard needs to surface
honestly.

---

## 3. Access model

This is the part my earlier plan got wrong, and it is worth understanding before writing
the RLS policy.

```mermaid
flowchart TB
    subgraph OrgA["Org: Nina Percept — type contractor"]
        PA["Project: Lodha Supremus<br/>owner_org_id = Nina"]
    end

    subgraph OrgB["Org: Lodha — type client"]
        VB["Read access via<br/>project_participant"]
    end

    subgraph OrgC["Org: XYZ PMC — type pmc"]
        VC["Read access via<br/>project_participant"]
    end

    PA -->|"participant row<br/>role=client<br/>scope=verified_only"| VB
    PA -->|"participant row<br/>role=pmc<br/>scope=verified_only"| VC

    PA -.->|"NO access"| OTHER["Org: Rival Contractor"]
```

Three access rules the schema must enforce:

1. A contractor sees **only their own** projects. Never another contractor's, even on the
   same client's site.
2. A client sees **verified data only**, across all contractors on their projects.
3. Internal contractor notes are never visible to the client, regardless of role.

Rule 1 is the existential one. Two subcontractors on the same tower seeing each other's
rates ends the business.

---

## 4. Module dependency order

Modules are built in dependency order, not importance order. Each one needs the one before it.

```mermaid
flowchart TB
    ID["Project ID + Email Engine"] --> EL["Evidence Locker"]
    EL --> CL["AI Classification"]
    CL --> EX["AI Extraction<br/>5 doc types"]
    EX --> VER["Contractor Verification"]
    VER --> MV["Milestone Validator"]
    VER --> BG["BG Verify"]
    MV --> CD["Client Dashboard"]
    BG --> CD
    MV --> PM["Payment Mismatch<br/>Excel import"]
    PM --> RS["Resolution Statement"]
    CD --> RS
    RS --> ACC["Accounting API<br/>integration"]
```

Resolution Statement sits last because it is only as good as the project memory beneath it.
Built early, it produces confident, thinly-sourced narratives — which is worse than nothing
in a dispute.

---

## 5. Layer architecture

```mermaid
flowchart TB
    subgraph L1["Presentation"]
        W1["Contractor screens<br/>Setup · Inbox Review · Modules · Exceptions"]
        W2["Client dashboard<br/>exceptions only, read-only"]
    end

    subgraph L2["API"]
        AUTH["Auth + role resolution"]
        RLSM["RLS session scoping"]
        ROUTES["Endpoints"]
    end

    subgraph L3["Logic"]
        RULEENG["Rules engine<br/>NO model calls"]
        VERIF["Verification state machine"]
        SCORE["Exception ranking"]
    end

    subgraph L4["AI — isolated"]
        ROUTER["Type router"]
        VISION["Vision extractor"]
        STRUCT["Spreadsheet parser"]
        CLS["Classifier"]
    end

    subgraph L5["Durable"]
        TEMPORAL["Temporal<br/>multi-year BG timers"]
    end

    subgraph L6["Data"]
        PGDB[("Postgres + RLS")]
        OBJ[("Object storage")]
    end

    L1 --> L2
    L2 --> L3
    L3 --> L6
    L4 --> L3
    L2 --> L5
    L5 --> L6
    L4 -.reads.-> OBJ
```

`L4` connects to `L3`, never directly to `L1` or `L6`. AI output must pass through the
verification state machine to become data. That is enforced by a CI check asserting no
model imports in the rules layer, and by the DB constraint on verification state.

---

## 6. Accounting integration, phased

Deliberately not an API integration on day one.

```mermaid
flowchart LR
    subgraph Ph1["Phase 1 — MVP"]
        X1["Contractor uploads<br/>Excel / CSV"]
    end
    subgraph Ph2["Phase 2"]
        X2["Import templates<br/>Tally · Zoho · SAP · Busy"]
    end
    subgraph Ph3["Phase 3 — post-pilot"]
        X3["Live API connectors"]
    end

    X1 --> CMP["Compare:<br/>Certified vs Tax Invoice<br/>vs Received vs Deductions<br/>vs Outstanding"]
    X2 --> CMP
    X3 --> CMP
    CMP --> MM["Payment mismatch flags"]
```

Building live Tally/SAP connectors before pilot validation is the classic way to spend three
months on plumbing for a workflow nobody has confirmed they want.
