# GLP-1 Voice Check-in — State & Database Design

## 1. Product Principle

The database should **not be designed around the conversation**.

The conversation is an interface for collecting information. The database should represent the patient's **longitudinal health journey**.

> **Conversation → Health Events / Observations → Longitudinal Patient Timeline**

A patient's journey state, a check-in's state, and a health event are separate concepts and should not be mixed.

---

## 2. Core Domain Model

```text
Patient
  │
  ├── Journey
  │     ├── Current state
  │     └── State history
  │
  ├── Medications
  │     └── Medication history / dose changes
  │
  ├── Check-ins
  │     └── Call sessions
  │
  ├── Health Events
  │     ├── Symptoms
  │     └── Medication events
  │
  ├── Check-in Observations
  │     ├── Appetite
  │     ├── Hydration
  │     ├── Energy
  │     ├── Sleep
  │     └── Overall feeling
  │
  └── Flags
```

---

# 3. Patient Journey State Machine

For V1, keep the state machine intentionally small.

```text
                    ┌──────────────┐
                    │  CONSULTED   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ PRESCRIBED   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │   STARTING   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │    EARLY     │
                    │  TREATMENT   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ ESTABLISHED  │
                    └──────┬───────┘
                           ↓
                    ┌──────┴───────┐
                    ↓              ↓
               DOSE_CHANGE   DISCONTINUED
                    │
                    ↓
             EARLY AFTER CHANGE
                    │
                    ↓
             ESTABLISHED TREATMENT
```

Initial states:

- `CONSULTED`
- `PRESCRIBED`
- `STARTING`
- `EARLY_TREATMENT`
- `ESTABLISHED`
- `DOSE_CHANGE`
- `DISCONTINUED`

The exact transition rules should be defined before implementing the conversational flow.

---

# 4. Database Principles

## 4.1 Separate facts from derived information

Store facts:

```text
checkin.status = missed
symptom.onset_at = Sep 3
symptom.type = feverish
```

Derive metrics:

```text
missed_checkins = 2
days_since_last_checkin = 3
symptom_persistence = 3 days
```

Do not unnecessarily duplicate derived values.

---

## 4.2 Preserve history

Do not simply store:

```text
patient.journey_state = "EARLY_TREATMENT"
```

because this loses historical information.

Instead store the current journey and its state history.

This lets us answer:

- When did the patient enter early treatment?
- How long were they in each state?
- What happened after a dose change?
- What symptoms occurred during a particular journey state?

---

## 4.3 Separate occurrence time from observation time

This is critical for conversational health data.

If a patient says on September 5:

> "I've been feeling feverish for the last two days."

Then:

```text
occurred_at = September 3
observed_at = September 5
```

`occurred_at` tells us **when the health event happened**.

`observed_at` tells us **when the system learned about it**.

Never collapse these into one timestamp.

---

## 4.4 Separate raw conversation from structured health data

The transcript should not be the source of truth for the dashboard.

Instead:

```text
Call Session
    ↓
Extraction
    ↓
Structured Health Data
    ↓
Database
    ↓
Dashboard
```

Keep the raw conversation for evidence/auditability, while the structured tables power the application.

---

# 5. Core Tables

## 5.1 `patients`

Represents the person.

```text
patients
--------
id                  PK
first_name
last_name
date_of_birth
phone
timezone
preferred_language
created_at
updated_at
```

Do not put medication or journey history directly into this table.

---

## 5.2 `patient_journeys`

Represents a treatment journey.

```text
patient_journeys
----------------
id                  PK
patient_id          FK → patients.id
status
started_at
ended_at
created_at
```

A patient may have more than one journey over time.

---

## 5.3 `journey_state_history`

Represents state transitions.

```text
journey_state_history
---------------------
id                  PK
journey_id          FK → patient_journeys.id
state
started_at
ended_at
transition_reason
created_at
```

Example:

```text
CONSULTED
    ↓
PRESCRIBED
    ↓
STARTING
    ↓
EARLY_TREATMENT
    ↓
ESTABLISHED
```

History should be append-oriented rather than overwriting previous states.

---

# 6. Medication Model

## 6.1 `medications`

Represents the medication itself.

```text
medications
-----------
id                  PK
name
generic_name
route
created_at
```

---

## 6.2 `patient_medications`

Represents a medication assigned to a patient.

```text
patient_medications
-------------------
id                  PK
patient_id          FK → patients.id
medication_id       FK → medications.id
dose
dose_unit
frequency
started_at
ended_at
status
created_at
updated_at
```

This allows medication history and dose changes without overwriting the past.

---

# 7. Check-in Model

## 7.1 `checkins`

A check-in represents a scheduled interaction.

```text
checkins
--------
id                  PK
patient_id          FK → patients.id
scheduled_at
started_at
completed_at
status
duration_seconds
created_at
```

Possible statuses:

```text
scheduled
completed
missed
cancelled
failed
```

A missed call is a **check-in event**, but it is not a health event.

---

## 7.2 `call_sessions`

A check-in may contain multiple call attempts.

```text
call_sessions
-------------
id                  PK
checkin_id          FK → checkins.id
started_at
ended_at
status
transcript
created_at
```

Example:

```text
Check-in Sep 5
    │
    ├── Call attempt 1 → failed
    │
    └── Call attempt 2 → completed
```

This is more flexible than assuming one check-in always equals one call.

---

# 8. Health Events

## 8.1 `health_events`

Represents something clinically relevant that happened or was reported.

```text
health_events
-------------
id                  PK
patient_id          FK → patients.id
checkin_id          FK → checkins.id NULL
event_type
occurred_at
observed_at
status
source
created_at
```

Examples:

```text
event_type:
- symptom
- medication
- other
```

The event should link back to the check-in when applicable.

---

## 8.2 `symptom_events`

Symptom-specific information.

```text
symptom_events
--------------
id                  PK
health_event_id     FK → health_events.id
symptom_type
severity
onset_at
resolved_at
trend
notes
```

Example:

```text
symptom_type = nausea
severity = mild
onset_at = 2026-09-03
status = active
trend = improving
```

---

# 9. Medication Events

## `medication_events`

Represents a medication-related event.

```text
medication_events
-----------------
id                  PK
health_event_id             FK → health_events.id
patient_medication_id       FK → patient_medications.id
event_type
scheduled_at
occurred_at
dose_taken
reason
notes
```

Possible event types:

```text
TAKEN
MISSED
DELAYED
REFUSED
SIDE_EFFECT
REFILL_ISSUE
```

Example:

> "I missed my injection yesterday because I was traveling."

```text
event_type = MISSED
scheduled_at = Sep 4
occurred_at = Sep 4
observed_at = Sep 5
reason = TRAVEL
```

---

# 10. Check-in Observations

Not everything needs to be a health event.

Daily measurements such as appetite, hydration, energy, and sleep can be modeled as observations.

## `checkin_observations`

```text
checkin_observations
--------------------
id                  PK
checkin_id          FK → checkins.id
observation_type
value
unit
confidence
created_at
```

Examples:

```text
APPETITE        → LOW
ENERGY          → LOW
HYDRATION       → NORMAL
SLEEP           → GOOD
OVERALL_FEELING → NOT_GOOD
```

This keeps the schema flexible as V1 evolves.

---

# 11. Flags

Flags should be **derived from underlying data**, rather than embedded inside the symptom itself.

## `flags`

```text
flags
-----
id                  PK
patient_id          FK → patients.id
health_event_id     FK → health_events.id NULL
checkin_id          FK → checkins.id NULL
flag_type
severity
reason
status
created_at
resolved_at
```

Conceptually:

```text
Health Data
    ↓
Rules / Flag Engine
    ↓
Flag
    ↓
Care Team
```

The underlying patient data should remain unchanged even if flagging rules change later.

---

## 11.1 Clinician Instructions

Represents an explicit tracking instruction from the care team (referenced by the voice-agent KB
as `active_clinician_instructions`, but originally missing from this schema — added here as the
authoritative definition).

## `clinician_instructions`

```text
clinician_instructions
-----------------------
id                  PK
patient_id          FK → patients.id
metric
frequency
instruction
start_date
end_date
status
created_at
```

Example:

```text
metric = hydration
frequency = daily
instruction = "Track daily fluid intake"
start_date = 2026-09-05
end_date = 2026-09-12
status = active
```

A patient may have zero or more active instructions at a time. `status` distinguishes
active/expired/completed without deleting history.

---

## 11.2 Escalation Protocols

`get_clinical_escalation_protocol` (voice-agent KB §4.13) has no backing table in this document
either — added here. Content is **clinical, not engineering**: rows must be authored/approved by
clinical staff, not invented by the agent or by application code. The migration seeds only a
generic, non-clinical fallback per `event_type` ("contact your care team") so the system fails
safe (never silent, never inventing guidance) until real protocols are loaded.

## `escalation_protocols`

```text
escalation_protocols
---------------------
id                  PK
event_type
severity            NULL = applies to any severity
action
instructions
urgency
contact
created_at
```

---

# 12. Event Evidence

For important extracted information, preserve the conversational evidence.

## `event_evidence`

```text
event_evidence
--------------
id                  PK
health_event_id     FK → health_events.id
call_session_id     FK → call_sessions.id
transcript_start
transcript_end
quoted_text
created_at
```

Example:

```text
Health event:
    Feverish

Onset:
    Sep 3

Reported:
    Sep 5

Evidence:
    "I've been feeling feverish for the last two days."
```

This gives clinicians traceability from structured data back to the original conversation.

---

# 13. Example: User Misses Two Calls

Timeline:

```text
Sep 2
└── Check-in → COMPLETED

Sep 3
└── Check-in → MISSED

Sep 4
└── Check-in → MISSED

Sep 5
└── Check-in → COMPLETED
       │
       └── User:
           "I've been feeling feverish for the last two days."
```

Extraction:

```text
health_event
-------------------------
patient_id
checkin_id = Sep 5 check-in
event_type = symptom
occurred_at = Sep 3
observed_at = Sep 5
source = patient_report

symptom_event
-------------------------
symptom_type = feverish
onset_at = Sep 3
status = active
```

The database therefore preserves both:

```text
Observation gap:
Sep 3 + Sep 4 = 2 missed check-ins

Health event:
Feverish
Started ≈ Sep 3
Reported Sep 5
```

This is much better than:

```text
Sep 5 → fever = true
```

because the latter loses the temporal information.

---

# 14. Overall Architecture

```text
                         PIPECAT
                            │
                            ↓
                     Conversation
                            │
                            ↓
                    Extraction Layer
                            │
                 ┌──────────┴──────────┐
                 ↓                     ↓
          Observations          Health Events
                 │                     │
                 └──────────┬──────────┘
                            ↓
                       PostgreSQL
                            │
                 ┌──────────┴──────────┐
                 ↓                     ↓
        Longitudinal Patient       Flag Engine
             Timeline                  │
                                       ↓
                              Clinician Dashboard
```

The Pipecat agent should **collect and extract information**.

The backend/database should be the source of truth for:

- Patient state
- Journey state
- Historical transitions
- Check-in history
- Temporal relationships
- Health events
- Medication history
- Derived flags

---

# 15. Recommended V1 Tables

Start with:

```text
patients
patient_journeys
journey_state_history

medications
patient_medications

checkins
call_sessions

health_events
symptom_events
medication_events
checkin_observations

flags
event_evidence
clinician_instructions
escalation_protocols
```

Do not build a full EHR or clinical data platform yet.

The V1 goal is:

> **A short daily voice conversation that reliably turns patient-reported information into structured, longitudinal data.**

---

# 16. Key Design Rules

1. **Store facts; derive metrics.**
2. **Never destroy history by overwriting state.**
3. **Separate journey state from check-in state.**
4. **Separate health events from daily observations.**
5. **Separate occurrence time from observation time.**
6. **Keep raw conversation separate from structured data.**
7. **Keep evidence for important extracted events.**
8. **Treat missed check-ins as operational events, not health events.**
9. **Keep flags separate from the underlying clinical data.**
10. **Keep the V1 schema narrow and extensible.**

---

# 17. Next Design Step

Before implementing the Pipecat flow, define the state machine in detail.

For every state, specify:

```text
STATE
  ↓
Entry conditions
  ↓
Information we need
  ↓
Daily questions
  ↓
Possible events
  ↓
Transition conditions
  ↓
Next state
```

For example:

```text
STARTING
│
├── What medication?
├── Has first dose been taken?
├── When?
├── Any symptoms?
├── Appetite?
├── Hydration?
├── Energy?
│
└── First dose confirmed
        ↓
   EARLY_TREATMENT
```

Once these transitions are defined, the **Pipecat conversation flow + extraction schema + PostgreSQL schema** can all be derived from the same state machine.
