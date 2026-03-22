# TODOS

## Compliance

### Phase 2: Filing Monitor

**What:** Build the Filing Monitor — FilingMonitorSnapshot model, `monitor_public_filings` management command, IAPD/EDGAR data parsing, discrepancy detection, email alerts, "Public Profile" dashboard card.

**Why:** Catches gaps between what you think you filed and what the SEC actually shows. Prevents surprises like "IAPD shows your Form ADV was last amended 14 months ago."

**Context:** Design doc Section 5 has full spec. Downloads SEC IAPD CSV compilation (adviserinfo.sec.gov/compilation) and EDGAR Form D feeds weekly. Looks up fund by CRD number (319106). Compares extracted fields against ComplianceSettings internal records. Creates FilingMonitorSnapshot with discrepancy details. Dashboard shows "Public Profile" card with green/red status. Requires CRD number (already in ComplianceSettings) and CIK per fund (already in Fund model).

**Effort:** M
**Priority:** P1
**Depends on:** Phase 1 (ERA compliance calendar with ComplianceSettings CRD field, Fund model with CIK field)

### Alberta Securities Commission compliance resolution

**What:** After Cole Frieman confirms the correct Alberta obligations, update the PLACEHOLDER seed data with real deadlines, filing URLs, and correct obligation details.

**Why:** Live compliance gap — the fund has a GP in Alberta and investors in Alberta but has done nothing with the ASC. The fund may currently be in violation.

**Context:** Key legal question: does the SEC ERA filing satisfy the "registered as an adviser in home jurisdiction" requirement under NI 31-103 s.8.26 (international adviser exemption)? If yes, the firm needs to file required notices with the ASC. If not, the Alberta-based GP may need to register directly. Software update is trivial once legal answer is known — just replace PLACEHOLDER obligations with real ones. See design doc "URGENT: Alberta Compliance Gap" section.

**Effort:** S (software change is trivial; legal research is the bottleneck)
**Priority:** P0
**Depends on:** Conversation with Cole Frieman (compliance counsel)

## Completed
