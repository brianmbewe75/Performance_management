CUSTOM PERFORMANCE MANAGEMENT
Frappe / ERPNext Custom App — Architecture Blueprint
Cascading Balanced Scorecards  ·  KRA/Goal Agreement  ·  Bottom-Up Appraisals

1. Executive Summary
This document specifies the complete architecture for a custom Frappe application that replaces the standard ERPNext Performance Management module. The solution enforces two distinct, sequential phases within each appraisal cycle.

Phase 1 — Cascading Balanced Scorecard Setup (Top → Bottom)
1. The CEO sets organisational objectives and creates the top-level Balanced Scorecard (BSC).
2. Each supervisor creates BSCs for their direct reports, negotiating and agreeing KRAs & Goals.
3. A subordinate's BSC cannot be finalised until the supervisor formally approves it.
4. Cascade flows level-by-level until every employee in the hierarchy has an Agreed BSC.

Phase 2 — Appraisal (Bottom → Top)
1. When the cycle closes, the system auto-creates one Appraisal Record per employee.
2. Each employee self-scores against their agreed Goals.
3. Their immediate supervisor scores the same Goals; the system computes a weighted average.
4. The supervisor's supervisor reviews & approves — repeated up the chain to the top.


2. Data Model — DocTypes
The app (recommended name: performance_mgmt) introduces the following DocTypes. None extend standard ERPNext Performance DocTypes to ensure upgrade safety.

DocType	Module Layer	Purpose
Appraisal Cycle	Configuration	Named period (e.g. FY2025-H1) with start/end dates and phase status
BSC Template	Configuration	Reusable scorecard template per role/department; defines perspective weights
Employee BSC	Phase 1 Core	Scorecard instance per employee per cycle; holds agreed KRAs & Goals
KRA (child table)	Phase 1 Core	Key Result Area row inside Employee BSC with name, description, weight %
Goal (child table)	Phase 1 Core	Goal row under a KRA; target, weight, measurement method, parent_goal link
BSC Cascade Log	Audit	Records every cascade event: parent BSC, child BSC, actor, date
Appraisal Record	Phase 2 Core	Bottom-up appraisal per employee per cycle; holds self & supervisor scores
Appraisal Item (child)	Phase 2 Core	One row per Goal; self_score, supervisor_score, weighted contribution
Appraisal Workflow Log	Audit	Every status transition: actor, timestamp, comments


3. Phase 1 — Cascading Balanced Scorecard
3.1 Cascade Integrity Rules
Cascade Enforcement (Python controller — before_submit on Employee BSC)
Rule 1: Supervisor's own Employee BSC must be status = 'Agreed' before creating a subordinate BSC.
Rule 2: Child BSC inherits the Appraisal Cycle and BSC Template from the parent.
Rule 3: Subordinate proposes their own KRAs and Goals; supervisor negotiates, then approves.
Rule 4: Goals may optionally link to a parent_goal in the supervisor's BSC for traceability.
Rule 5: BSC Cascade Log entry is created automatically when a child BSC is Agreed.
Rule 6: Once Agreed, KRAs and Goals are locked (read-only). Amendments require a formal BSC Amendment Request approved by supervisor.

3.2 Employee BSC — Key Fields
Field	Field Type	Notes
employee	Link → Employee	Owner of this scorecard
appraisal_cycle	Link → Appraisal Cycle	Which cycle this BSC belongs to
supervisor_bsc	Link → Employee BSC	Parent BSC; NULL for CEO/top of org
status	Select	Draft / Pending Supervisor Approval / Agreed / Cascaded
bsc_template	Link → BSC Template	Optional; pre-fills perspective structure
kra_table	Table → KRA	Child table of Key Result Areas
agreed_on	Date	Auto-set when supervisor approves
total_goal_weight	Float (computed)	Sum of all Goal weights; validated = 100% on submit


4. Phase 2 — Bottom-Up Appraisal
4.1 Auto-Creation of Appraisal Records
When the Appraisal Cycle status is set to 'Appraisal Open', a server-side scheduled job (or on_update hook) queries all employees with an Agreed BSC for that cycle and creates one Appraisal Record each. Each record is pre-populated with Appraisal Item rows cloned from the employee's agreed Goals — no manual re-entry required.

4.2 Scoring Sequence
Step-by-Step Bottom-Up Scoring Flow
Step 1 — Employee Self-Score: Employee opens their Appraisal Record, enters a score (1-5) and an evidence comment for each Goal, then submits. Status moves to 'Pending Supervisor Score'.
Step 2 — Supervisor Score: Supervisor receives an in-app and email alert, enters their score per Goal, and submits. System instantly computes the weighted average final score.
Step 3 — Second-Level Review: The supervisor's supervisor reviews the computed score, optionally adds a calibration note, and approves. Status becomes 'Completed'.
Step 4 — Gate Enforcement: A supervisor's Appraisal Record cannot reach '2nd Level Review' until ALL their direct reports are at minimum 'Pending 2nd Review'. This enforces the bottom-up sequence.

4.3 Score Computation
# Python controller — compute_appraisal_score(doc)
def compute_appraisal_score(doc):
    total = 0
    for item in doc.appraisal_items:
        avg = (item.self_score + item.supervisor_score) / 2
        total += (item.goal_weight / 100) * avg
    doc.final_score = round(total, 2)
    doc.rating = get_rating_label(total)  # see scale below

4.4 Rating Scale
Score	Rating Label	Description
4.5 – 5.0	Exceptional	Far exceeded all agreed targets; exemplary performance
3.5 – 4.4	Above Target	Consistently exceeded goals
2.5 – 3.4	On Target	Met all agreed goals as expected
1.5 – 2.4	Partially Met	Met some goals; improvement areas identified
1.0 – 1.4	Below Expectation	Did not meet agreed goals; PIP may be initiated


5. Workflow State Machines
5.1 BSC Workflow States (Frappe Workflow Doc on Employee BSC)
From State	To State	Actor & Trigger
Draft	Pending Supervisor Approval	Employee submits their proposed BSC
Pending Supervisor Approval	Agreed	Supervisor approves; BSC locked for cascade
Pending Supervisor Approval	Revision Required	Supervisor rejects with comments; employee revises
Revision Required	Pending Supervisor Approval	Employee resubmits after revision
Agreed	Cascaded	Supervisor has created & agreed BSCs for all direct reports

5.2 Appraisal Workflow States (Frappe Workflow Doc on Appraisal Record)
From State	To State	Actor & Trigger
Draft	Pending Self-Score	System auto-creates on cycle Appraisal Open
Pending Self-Score	Pending Supervisor Score	Employee submits self-scores
Pending Supervisor Score	Pending 2nd Level Review	Supervisor submits scores; final score computed
Pending 2nd Level Review	Completed	Supervisor's supervisor approves final score


6. Roles & Permission Matrix
Action	HR Admin	CEO	Director	Manager	Employee	Sys Admin
Create Appraisal Cycle	✓	✓				✓
Create own BSC	✓	✓	✓	✓	✓	✓
Approve subordinate BSC		✓	✓	✓		✓
View dept BSCs	✓	✓	✓	✓	Own only	✓
Self-score Appraisal					✓	
Supervisor-score Appraisal		✓	✓	✓		✓
2nd Level Review & Approve		✓	✓	✓		✓
Analytics Dashboard	✓	✓	✓			✓


7. Key Design Decisions & Guardrails
7.1 No Extension of Standard ERPNext Performance Module
This app introduces fully independent DocTypes. This avoids conflicts with ERPNext upgrades and keeps the solution self-contained. The standard Appraisal and Appraisal Template DocTypes remain untouched.
7.2 Goal Progress Decoupled from Appraisal Scoring
Unlike standard ERPNext where Goal progress directly updates appraisal scores, in this system the agreed BSC Goals serve purely as the yardstick. Scores are entered manually during the appraisal phase by the employee and supervisor independently, then averaged. This supports qualitative targets, milestones, and behavioural goals — not just numeric KPIs.
7.3 BSC Amendment Process
Once a BSC is Agreed it is fully locked. If scope needs to change mid-cycle, the supervisor raises a BSC Amendment Request (a lightweight DocType), agrees the changes, and the system creates a new BSC version while archiving the old one with a full audit trail.
7.4 Bottom-Up Gate Logic
A supervisor's Appraisal Record is programmatically blocked from advancing to '2nd Level Review' until every one of their direct reports has reached at minimum 'Pending 2nd Level Review'. This is enforced in the before_submit controller on Appraisal Record, not just at the UI level.


8. Implementation Roadmap
#	Milestone	Deliverables	Estimate
1	App Scaffold & DocTypes	bench new-app; all DocTypes, child tables, field definitions, basic permissions	1 week
2	BSC Cascade Workflow	Workflow states, approval controllers, cascade validation & locking logic	1.5 weeks
3	Appraisal Engine	Auto-creation hook, self/supervisor scoring UI, weighted score computation, gate logic	1.5 weeks
4	Notifications	Email + in-app alerts for every workflow transition requiring action	0.5 week
5	Reports & Dashboard	Cascade completion %, score distribution chart, rating summary, export to Excel	1 week
6	UAT & Go-Live	Pilot with one department, bug fixes, training materials, production deployment	1 week


9. Recommended Next Steps
•	Confirm the scoring split with the client: 50/50 self vs supervisor is the default; adjust weights if the client wants supervisor score to carry more weight (e.g. 30/70).
•	Confirm BSC perspectives (Financial, Customer, Internal Process, Learning & Growth are standard; clients may add or rename).
•	Decide whether to support 360-degree multi-rater scoring in a future phase or keep it two-party for the initial release.
•	Set up staging bench: bench new-app performance_mgmt and begin DocType creation in the sequence listed in Section 2.
•	Build and fully test the cascade validation controller and bottom-up gate logic in staging before any user involvement.
•	Run a pilot appraisal cycle with one department (e.g. HR or Finance) to validate the workflow before full rollout.

Document Info
Version 1.0  |  Status: Draft for Client Review
Compatible with: Frappe v15 / ERPNext v15
Update this document after each sprint to reflect implementation decisions and any scope changes.

