# Bireme Research

A multi-tenant Django platform for investment research, portfolio management, and compliance oversight.

## Compliance Certifications & Surveys

The platform includes a robust certification system designed for SEC-registered investment advisers. It automates recurring employee surveys and attestations, ensuring regulatory requirements are met with full auditability.

### Key Features
- **Survey Versioning:** Immutable version history for all legal attestations and question sets.
- **Automated Assignments:** Engine to launch quarterly and annual surveys to specific audiences (Access Persons, All Supervised Persons, etc.).
- **Dynamic Forms:** Support for Yes/No, Text, Date, Decimal, and File Upload questions.
- **Exception Escalation:** Flagged answers automatically trigger `SurveyException` records for CCO review.
- **Digital Signatures:** Digital signature capture with timestamps and legal text snapshots.
- **CCO Dashboard:** Central command center for assignments, reviews, and exception management.

### Initialization & Setup
1. **Seed Templates:** Run the following command to load standard regulatory templates (Personal Trading, Code of Ethics, etc.):
   ```bash
   python manage.py seed_compliance_surveys
   ```
2. **Assign Surveys:** Navigate to **Compliance > Certifications** in the sidebar. Use the "Assign Surveys" button to launch certifications for a specific year and quarter.
3. **Employee Participation:** Employees will see their pending tasks under **My Certifications**.
4. **CCO Review:** Submissions appear in the review queue on the Certifications Dashboard. Approved items are locked; rejected items are sent back to the employee for correction.

### Auditability
All survey data is exportable via CSV. Each submission preserves the exact questions and attestation language presented to the user at the time of signing.
