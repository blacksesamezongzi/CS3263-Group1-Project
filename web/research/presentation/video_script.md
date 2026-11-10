# Presentation video: 10-minute maximum

Target 9:20 including transitions. Latest user-provided video requirement supersedes the older 15-minute presentation guidance. Cover accomplishments, project understanding, technical depth, methodology and actual results. Responsible AI stays in the report.

Suggested roles are a recording plan, not new claims about implementation ownership. Speak naturally and rehearse; timing depends on speech rate.

## 0:00-0:35 — A course plan needs more than plausible course names
**Suggested speaker:** Sun Jiaen
**Visual:** Title, team names, one actual semester plan. Keep the title readable and omit a long agenda.

**Narration:**
We built Pathway, a course planner for NUS Computer Science students. Students describe what they want, inspect the resulting constraint cards, and generate a semester plan with weekly timetable checks. Our central question is whether direct language-model planning can satisfy the same explicit rules as a symbolic planner. We compare actual generated outputs rather than judging how convincing the explanations sound.

## 0:35-1:25 — The task combines academic rules and personal goals
**Suggested speaker:** Sun Jiaen
**Visual:** Show one prerequisite relation, paired CS2101/CS2103T, and an eight-semester preference. Label requirements, preferences and assumptions distinctly.

**Narration:**
A valid plan must put prerequisites strictly before the courses that need them. For example, completing CS1231S in the same semester as a dependent course does not satisfy an earlier prerequisite. CS2101 and CS2103T must be taken together under our project mapping. Students may also prefer eight semesters or request a Mathematics or Quantitative Finance minor. We distinguish these hard commitments from preferences that can remain unmet. We assume all future years repeat the AY2026/27 offerings, exam dates and lesson patterns. That makes the task concrete, but it is also a major limitation.

## 1:25-2:30 — Language becomes inspectable rules before search
**Suggested speaker:** Shen Jingtao
**Visual:** Use the report pipeline figure. Highlight the model/card boundary and the independent audit.

**Narration:**
The frontend sends a student instruction to our FastAPI backend. The SoCLaaS model returns a restricted JSON proposal. Pydantic checks the allowed rule types, known course codes, hard or soft strength, and semester bounds. The student sees the proposed cards before generating a plan. One card may represent several rules, so the interface does not need a one-to-one relationship with solver constraints. Deleting a card removes its active rules, and reset restores the defaults. The model does not execute code or search the degree plan. The next stage compiles the active rules into PyCSP3 and solves them with ACE. A separate Python checker reviews the result before export. Schema validation alone cannot prove that a card correctly reflects the student's intent, so visibility and correction remain important.

## 2:30-3:45 — Integer assignments express the degree plan
**Suggested speaker:** Achar Pavithra
**Visual:** Show x_c in {0,...,H}, one prerequisite equation and a simple hard/soft objective. Avoid displaying the full compiler.

**Narration:**
Each course has one integer variable. Zero means the course is omitted, and a positive value is its semester. Semester units are the sum of credits assigned to that semester. Hard requirements constrain these variables, including foundation coverage, total units, availability, prerequisite order, and category allocations. Minor allocation variables track which courses fulfil which groups, while preventing invalid sharing. We support sixteen rule types and have fourteen hard cards plus two soft cards by default. Soft requests add penalties for missing a requested semester, placing courses after a target completion semester, and deviating from the workload target. These penalties form a weighted sum. We do not claim they are a proved lexicographic ordering, and a feasible result found within the search limit may not be globally optimal. The actual implementation uses bundled PyCSP3 2.6.1 and ACE, rather than the OR-Tools package suggested in our proposal.

## 3:45-4:55 — Weekly conflicts feed back into degree search
**Suggested speaker:** Shen Jingtao
**Visual:** Show two alternative tutorial packages and a conflict cut. Include the CS2101 shared-package assumption as a small caption.

**Narration:**
A course-level plan can look valid while its weekly timetable is impossible. We therefore solve a second problem for each active semester: choose one complete class package for every lesson type. A class can contain several meetings, and we keep them together. Meetings conflict only if their days, time intervals and teaching weeks overlap. When the search proves that a set of courses cannot coexist, we shrink that set and add a cut to the degree solver for all matching semester parities. The solver then searches again. A timeout is unknown rather than a proof of infeasibility. Missing timetable data is also not treated as verified. We cap refinement attempts and use an outer process timeout. Finally, an academic audit checks foundation coverage and prerequisite order even if a user deleted those cards, so invalid exploratory previews cannot be exported.

## 4:55-5:50 — The interface connects requirements to a usable plan
**Suggested speaker:** Sun Jiaen
**Visual:** Record a 45-50 second prepared screen capture: defaults, add QF minor/pin, cards appear, saved result, weekly view, native JSON export. Cut waiting time with a labelled transition.

**Narration:**
Here are the default requirements and preferences, with official source links where applicable. A student can request a minor or ask to take CS2102 in semester three. The assistant converts the instruction into visible cards. The generated plan shows real course codes rather than unresolved elective placeholders. We can inspect each semester's weekly selection and export a native NUSMods Planner JSON file. The planner contains 338 real reference courses, including supplementary Mathematics and QF options. For the video, the solve is prepared in advance and any skipped waiting time is labelled. We do not need to expose API keys or rely on a live model service during the recording.

## 5:50-6:55 — The benchmark varies explicit rule disclosure
**Suggested speaker:** Sun Jiaen
**Visual:** Show three condition columns A/AP/APR, 15 model IDs, common reference snapshot and output checker. Label CLI versus API.

**Narration:**
Our main matrix tests fifteen model IDs under three conditions: assumptions only, assumptions plus preferences, and assumptions plus preferences plus hard requirements. All methods receive the same frozen course and timetable facts and must return the same JSON schedule format. We exclude aliases from the model count. The SoCLaaS requests use temperature zero and a 3500-token output cap without automatic repairs or retries. Astra and Sol use the Codex CLI because no separate API key is configured. That harness has different hidden instructions and generation limits, so we report it separately. We count hard-card failures on evaluable plans, while unavailable services, truncated or malformed outputs and unknown courses remain visible. A failed request never counts as a zero-violation plan.

## 6:55-8:30 — The results separate correctness from availability
**Suggested speaker:** Sun Jiaen
**Visual:** Show the actual model table and the three CSP controls. Explicitly mark unverified weekly data and unavailable outputs. Include no human preference chart yet.

**Narration:**
Across the 45 main requests, 14 produced evaluable schedules and 1 passed all implemented hard checks. The table distinguishes service errors, unparseable responses, proven rule failures and unresolved weekly checks. Full rule disclosure helped some models, but this small fixed-task study does not establish a universal ranking. Sol produced a fully verified base plan in the full-requirement condition. Astra had zero proven hard-card failures there, but its weekly check remained unverified. This matters: our evidence does not support saying that language models can never produce correct schedules. The three symbolic controls all passed their active hard checks and audits. The base control completed 160 units in eight semesters and met both default preferences. The QF minor control also finished in eight semesters, with a workload deviation. The Mathematics minor control used nine semesters and missed the duration and balance preferences. These are legitimate tradeoffs under a feasible hard model. We have also prepared fifteen anonymous schedules and an anchored rating rubric for two internal raters. We have not collected their scores, so we cannot claim a human preference advantage.

## 8:30-9:20 — Explicit constraints provide inspectable guarantees within scope
**Suggested speaker:** Achar Pavithra
**Visual:** Three concise limitations, then one concrete conclusion. No Responsible AI section is needed in this video.

**Narration:**
Our main accomplishment is a working connection from student language to editable constraints, semester optimisation, weekly verification and NUSMods export. The guarantees apply to the implemented model and frozen data. Future offerings can change, and full graduation eligibility, registration quotas, arbitrary second majors and all preclusion rules remain outside the current scope. Bounded search can also time out or leave preferences unmet. Next we would expand curriculum coverage, measure parser fidelity on many independent instructions, and collect the blinded ratings from students beyond the development team. The project demonstrates how an LLM can make a constraint planner easier to use while preserving inspectable checks on the resulting plan.

## Rehearsal and cuts

- Read once at a comfortable pace, then measure actual duration. Do not accelerate to make dense slides fit.
- If the video exceeds 9:40, shorten the catalogue counts and minor details before cutting the experimental caveats.
- Keep the method, weekly feedback and results sections. Omit a separate related-work survey, Responsible AI and detailed contribution table from the video; they remain in the report.
- Verify that the exported video is at most 10:00. This file is the script/storyboard, not a recorded video.
