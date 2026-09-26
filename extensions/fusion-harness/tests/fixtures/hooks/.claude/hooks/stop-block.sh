#!/bin/sh
# Fixture Stop gate: prints a block decision (the doctor must classify this can-block).
echo '{"decision":"block","reason":"fixture session cannot end"}'
exit 0
