README
------

Runs many instances of a `sleeper` exe with random sleep time.
The number of instances is variable and is intended to be more
than can run all at once.

The script start up to a given threshold, and then starts more as tasks
complete.  Since the `sleeper` exe's have different sleep times, the
available slots for running changes and stress tests the mapping and other
parts of the system.

See the `END` and `MAX_PROC` variables in the middle of the script for
setting the above thresholds.  Currently, this is being set based on the
number of resources (nodes and cores):
 - `MAX_PROC` is set to `CI_NUM_NODES` times a hardcoded `NUM_CORES_PER_NODE`
 - `END` is set to `n` x total number of cores (e.g., 3 x `MAX_PROC`)

The intent is to have much more work than available cores to keep things busy.

TODO:
 - NOTE: The validty checks do few grep's of output file
   to check if number of expected matches the config for
   that run.  A bit fragile, and likely needs improvement.

