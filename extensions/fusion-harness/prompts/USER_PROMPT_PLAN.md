Plan this task. Do not write the code.

Task:
{{TASK}}

Project: {{REPO_ROOT}}
Plan folder: {{PLAN_DIR}}
Write the plan to this exact path and nowhere else: {{PLAN_PATH}}

Inspect the project first. Then write that one file with these headings, in this order, each as a level-2 heading:

## Decoded ask
## Evidence
## Do not touch
## Deliverables
## Steps
## Checklist
## Verify
## Handoff

Decoded ask restates the task in one sentence. Evidence cites paths you actually opened. Do not touch lists files and actions that are out of scope, including commit and push. Deliverables names the plan path and says done means the file exists. Steps name the file, the change, the verify command, and the expected exit status. Checklist lines cite a path or a number. Verify is the command a fresh agent runs. Handoff is the single next action, which is to wait until the user says to implement.

Do not implement the task. Do not create, edit, or delete any other file.
