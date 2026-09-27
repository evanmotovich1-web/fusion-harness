# Directory launch correction

Written before implementation for this follow-up.

Reproduced the user's exact `Cannot find module .../extensions/self-compact` error
with actual Pi startup (`--mode rpc`, exit 1). `--help` alone exits 0 even when the
extension fails to load, so it is insufficient proof of a successful launch.

1. Add `extensions/self-compact/index.ts` forwarding the existing default export,
   allowing Pi's loader to resolve the extension directory.
2. Let the existing offline runtime probe choose the directory entry point.
3. Verify real CLI RPC startup and self-compact command discovery through both the
   directory and file paths. Exercise compact-and-resume using the actual Pi runtime
   and offline provider through the directory path. Preserve all unrelated files.
4. Document the shorter launch command and report actual results. No paid provider
   calls, commits, or deployment.

Completed: directory entry point added; both real CLI RPC launches pass with
self-compact command discovery, no stderr and exit 0. The directory entry point also
passes actual-Pi offline compact-and-resume with one summary and no extension errors.
See `extensions/self-compact/VERIFICATION.md` for evidence and scope.

## Correction: normal discovery conflict

The preceding checks disabled normal discovery and did not establish that the
user's command works. Reproduced exit 1 and duplicate tool/flag errors with normal
settings: Fusion Harness is installed globally as a Pi package, which discovers
the new index.ts separately from the explicit directory path.

Revised build steps, written before the correction:
1. Replace our index.ts with a package.json main entry pointing at self-compact.ts.
   This supports explicit directory imports without opting into Pi's index-based
   automatic discovery. Preserve global settings and other extensions.
2. Run both explicit directory/file launches with normal discovery and verify one
   self-compact command, exit 0, and no extension conflicts.
3. Rerun scoped tests and actual-Pi compact-and-resume through the directory.
4. Correct documentation and record normal-configuration verification evidence.

Revised steps completed: main entry replaces index, both normal-discovery RPC
launches pass, exact interactive command opens the widget and exits cleanly,
63 focused tests pass, and directory compact-and-resume passes. Evidence is in
VERIFICATION.md and verification/normal-discovery-{before,after}.json.
