"""Flash banner text for the patient-detail page, keyed by the redirect's `error`/`success` code."""

ERROR_MESSAGES = {
    "illegal_transition": "That journey transition isn't allowed from the current state.",
    "no_active_medication": "This patient has no active medication to update.",
}

SUCCESS_MESSAGES = {
    "journey_updated": "Journey state updated.",
    "medication_updated": "Medication updated.",
    "instruction_added": "Clinician instruction added.",
    "schedule_updated": "Metric tracking cadence updated.",
    "health_event_recorded": "Health event recorded.",
    "checkins_seeded": "Missed check-ins seeded.",
}
