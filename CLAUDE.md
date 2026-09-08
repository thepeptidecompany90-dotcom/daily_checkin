# GLP-1 Voice Agent

## Product

We are building a voice agent for patients 55+ on a GLP-1 medication journey.

The V1 product performs short daily check-ins and converts conversations
into structured longitudinal health data.

## Framework

Pipecat is the ONLY voice-agent framework.

Use:
- Python
- uv
- Pipecat
- Pipecat Flows
- OpenAI
- PostgreSQL
- Daily/WebRTC

## Important architecture rule

The database/domain model is the source of truth.

The LLM must NOT independently determine:
- patient journey state
- medication schedule
- clinical instructions
- missed check-ins
- escalation severity
- medication changes

The backend determines these.

The LLM:
1. Converses naturally
2. Uses tools to retrieve context
3. Extracts patient-reported information
4. Calls tools to persist information
5. Follows clinical protocols returned by the backend

## Safety

The agent must not:
- diagnose
- prescribe
- change medication
- invent clinical instructions
- tell a patient to stop medication unless an authorized
  clinical protocol explicitly instructs it to do so

Emergency situations must follow the configured emergency protocol.

## Domain model

Read:
docs/domain-model.md

## Voice Agent KB

Read:
docs/voice-agent-kb.md

## Development rules

Before implementing:
1. Inspect the existing architecture.
2. Explain the proposed change.
3. Keep business logic outside prompts.
4. Keep database logic outside the LLM.
5. Use typed schemas.
6. Write tests for state transitions and extraction.
7. Do not introduce unnecessary abstractions.