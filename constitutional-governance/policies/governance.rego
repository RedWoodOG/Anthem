package anthem.governance

# Anthem Constitutional Governance Policy
# This is evaluated by OPA on every request. It is not decorative.

default benefit_score = 0.5
default harm_score = 0.5
default tier = "T2"
default warnings = []

# High-benefit tasks
benefit_score = 0.9 {
    input.task == "query"
    input.capability_id != "urpe.evaluate"
}

benefit_score = 0.8 {
    input.task == "underwriting"
}

benefit_score = 0.7 {
    input.task == "analysis"
}

benefit_score = 0.6 {
    input.task == "evaluation"
}

benefit_score = 0.85 {
    input.task == "scheduling"
}

# Harm scoring
harm_score = 0.1 {
    input.task == "query"
    not input.pii_present
}

harm_score = 0.3 {
    input.pii_present
}

harm_score = 0.5 {
    input.capability_id == "urpe.evaluate"
}

harm_score = 0.6 {
    some domain
    input.domains[domain] == "strategy"
}

# Tier determination
tier = "T1" {
    benefit_score > 0.8
    harm_score < 0.2
}

tier = "T3" {
    harm_score > 0.4
}

tier = "halt" {
    harm_score > 0.7
}

# URPE always requires T3
tier = "T3" {
    input.capability_id == "urpe.evaluate"
}

# Warnings
warnings = w {
    w := array.concat(
        pii_warning,
        urpe_warning
    )
}

pii_warning = ["PII detected — masking required"] {
    input.pii_present
}

pii_warning = [] {
    not input.pii_present
}

urpe_warning = ["URPE evaluation requires critical review"] {
    input.capability_id == "urpe.evaluate"
}

urpe_warning = [] {
    input.capability_id != "urpe.evaluate"
}
