@echo off
REM One unattended self-repair cycle: find, judge, patch, run the held-out gate, keep or revert, record.
REM Registered as a Windows Scheduled Task by owner approval, 2026-08-01.
REM
REM What constrains it, verified behaviourally before this file was written -- six probes, all refused:
REM   its own judge, its own ledger, the sealed E5 scripts, the moral core, a path outside the
REM   repository, and the system hosts file. The guard is packages/self_repair/provisional.py FORBIDDEN.
REM Nothing here pushes. Commits, if any, stay local.
REM
REM To stop it:  schtasks /Delete /TN "ATANOR self-repair loop" /F
REM
REM SELF-TUNING, approved by the owner 2026-08-01 (the Goedelian split). The loop may change its own
REM numeric constants -- and only after the held-out gate agrees that what the change UNLOCKS actually
REM survives. It may never touch the GROUND (packages/self_repair/tuning.py GROUND): the recall
REM harness, the ledgers, the criteria ledger, the accountability organs, the moral core. Verified
REM behaviourally with writes ENABLED: an attempt to zero FRICTION_FIRINGS or lower EPISODES_REQUIRED
REM is refused as ground.
REM
REM To revoke: delete the next line. To undo what it has already changed:
REM   del data\self_repair\tuned_parameters.json
set ATANOR_ALLOW_SELF_TUNING=1
cd /d "%~dp0.."
python -m packages.self_repair.autorun --unattended --quiet >> data\self_repair\unattended.log 2>&1
