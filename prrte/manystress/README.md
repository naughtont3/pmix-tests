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
setting the above thresholds.  Currently this is fixed and ignores
any change in number of available nodes, i.e., more nodes just means
your may avoid hitting threshold (backup) and just complete faster.

TODO:
 - NOTE: The validty checks do few grep's of output file
   to check if number of expected matches the config for
   that run.  A bit fragile, and likely needs improvement.

 - Make `END` and `MAX_PROC` variables smarter to use num nodes

