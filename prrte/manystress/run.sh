#!/bin/bash

# Final return value
FINAL_RTN=0

# Number of nodes - for accounting/verification purposes
NUM_NODES=${CI_NUM_NODES:-1}

# Number of cores in each node (default to 20)
NUM_CORES_PER_NODE=${CI_NUM_CORES_PER_NODE:-20}

# Scale test based on number of nodes
TTL_NUM_CORES=$(expr $NUM_NODES \* $NUM_CORES_PER_NODE)

# Enable more verbose output (set VERBOSE=1)
VERBOSE=1

#
# Control params for _run_stress_test
#
#   MAX_PROC -- maximum number of "active" processes,
#               which is used to throttle how many are
#               actively being launched/running at a time.
#               (Generally want to make this less than 'END',
#                so there are subset of active, while trying
#                to get the full set of tasks done.)
#
#               MAX_PROC <= min available number slots on 1 node,
#               because we do not use oversubscription flag.
#
#               Example: If have only 1 node with 8 slots (cores),
#               the max value for MAX_PROC is 8.  If have 2 node for
#               total of 16 slots (cores), MAX_PROC can be up to 16.
#
#   END      -- Upper bound on number of processes to startup.
#               This is used to calculate the total 'NTASKS'
#               that will be run through the system.
#
# Static values for easy testing
# TJN: DEBUG - Try to see if this changes CI status/hang
export MAX_PROC=20
export END=100
#
#---
# Setting 'MAX_PROC' to total number of cores that we can use over all nodes
# Setting 'END'      to 3x number of cores we have to ensure we have many more
#                     tasks than available cores to run on
#export MAX_PROC=$TTL_NUM_CORES
#export END=$(expr $TTL_NUM_CORES \* 3)

_shutdown()
{
    # ---------------------------------------
    # Cleanup DVM
    # ---------------------------------------
    pterm

    exit $FINAL_RTN
}

###########################################################
# Original script by Wael Elwasif (elwasifwr@ornl.gov)
#
# Stress testing of launching tasks.
#
# All output sent stdout and "output.txt" file using 'tee'
###########################################################
_run_stress_test()
{
    export HN=$(hostname)

    # TJN: Moved 'MAX_PROC' to top-of-file

    # Array of currently running prun processes
    declare -A pidarr
    declare -A finished
    declare -A all_finished
    declare -A launch_time
    i=0;
    export num_active=0
    export num_finished=0

    export START=1
    # TJN: Moved 'END' to top-of-file
    export NTASKS=$(expr $END - $START)

    echo "#  INFO: NUM_NODES=$NUM_NODES NUM_CORES_PER_NODE=$NUM_CORES_PER_NODE TTL_NUM_CORES=$TTL_NUM_CORES MAX_PROC=$MAX_PROC END=$END" | tee -a output.txt
    echo "# SETUP: MAX_PROC=$MAX_PROC START=$START END=$END NTASKS=$NTASKS" | tee  -a output.txt

    export mycount=0

    export array=($(seq $START $END))
    for val in "${array[@]}"; do

        mycount=$(expr $mycount + 1)

        # XXX: EDIT HERE
        # Task duration 1-10 seconds
        nseconds=$(( ( RANDOM % 10 )  + 1 ))
        #nseconds=45

        if [ $VERBOSE -gt 0 ] ; then
            echo "$(date) : $(date +%s) : [$mycount] Launch 'sleep $nseconds'" | tee -a output.txt
        fi

        #
        # We launch prun (_CMD) in background, but also append
        # the output to logfile (output.txt).  This could get
        # mixed up but we do not care about order of output.
        #
        # NOTE: Final validity checks assume each sleeper outputs
        #       single line containing 'DONE' string.
        #

        _CMD="prun -n 1 ./sleeper $nseconds"

        # Launch prun without waiting (**background**)
        $_CMD 2>&1 | tee -a output.txt &
        pid=$!
        st=${PIPESTATUS[0]}
        if [ $st -ne 0 ] ; then
            echo "ERROR: prun failed with $st" | tee -a output.txt
            FINAL_RTN=9
            _shutdown
        fi

        num_active=$(expr $num_active + 1)
        if [ $VERBOSE -gt 0 ] ; then
            echo "$(date) : $(date +%s) : Launched command ${val} : num_active = $num_active  num_finished = $num_finished (cmd[$mycount]: sleep $nseconds)" | tee -a output.txt
        fi

        # Add child PID and launch-counter-ID to 'pidarr' tracking array
        pidarr[$pid]="${val}";

        # Record child PID and launch-time to 'launch_time' tracking array
        launch_time[$pid]=$(date +%s);

        #echo "$pid STARTED $(date +%s)" | tee -a output.txt

        #echo "${!pidarr[@]}";
        i=$(expr $i+1);

        #wait when we've launched MAX_PROC processes for any one to finish
        while [ $(expr $MAX_PROC - $num_active) -eq 0 ]; do
            do_sleep=1
            for p in ${!pidarr[@]}; do
                # Check if process $p is alive
                kill -0 $p 2>/dev/null;
                if [ $? -ne 0 ] ; then
                    wait $p;
                    #echo "$p FINISHED $(date +%s)" | tee -a output.txt
                    #echo "$p FINISHED" | tee -a output.txt

                    # Decrement number of active processes
                    num_active=$(expr $num_active - 1);

                    # Increment number of finished processes
                    num_finished=$(expr $num_finished + 1);

                    #delete=($p);
                    #pidarr=( "${pidarr[@]/$delete}" );

                    # Record child PID and launcher-counter-ID to 'finished' tracking array
                    finished[$p]=${pidarr[$p]}

                    # Calculate execution time
                    runtime=$(expr $(date +%s) - ${launch_time[$p]} )

                    if [ $VERBOSE -gt 0 ] ; then
                        echo "$(date) : $(date +%s) : Finished ${pidarr[$p]} : num_active = $num_active  num_finished = $num_finished runtime = $runtime" | tee -a output.txt
                    fi

                    # Remove child PID from 'pidarr' tracking array
                    unset pidarr[$p]

                    do_sleep=0
                    #echo "${!pidarr[@]}";
              fi
            done # for p

            if [ $do_sleep -eq 1 ] ; then
                if [ ${#finished[@]} -gt 0 ]; then
                    keys=( "${!finished[@]}" ) ;
                    k0=${keys[0]};
                    unset finished[$k0];
                fi
                sleep 0.5
            fi
        done # while

    done # for val

    echo "DONE SUBMITTING - now only waiting" | tee -a output.txt
    while [ ${#pidarr[@]} -gt 0 ]; do
        do_sleep=1
        for p in ${!pidarr[@]}; do
            # Check if process $p is alive
            kill -0 $p 2>/dev/null;
            if [ $? -ne 0 ] ; then
                wait $p;
                #echo "$p FINISHED $(date +%s)" | tee -a output.txt
                num_active=$(expr $num_active - 1);
                num_finished=$(expr $num_finished + 1);
                #delete=($p);
                #pidarr=( "${pidarr[@]/$delete}" );
                finished[$p]=${pidarr[$p]}
                if [ $VERBOSE -gt 0 ] ; then
                    echo "$(date) : $(date +%s) : Finished ${pidarr[$p]} : num_active = $num_active  num_finished = $num_finished" | tee -a output.txt
                fi
                unset pidarr[$p];
                do_sleep=0;
                #echo "${!pidarr[@]}";
            fi;
        done;
        if [ $do_sleep -eq 1 ] ; then
            sleep 0.5
        fi

        for k0 in "${!finished[@]}" ; do
            unset finished[$k0]
        done
    done

    #echo "${!pidarr[@]}"
    #wait ${!pidarr[@]};
    echo "TASKS FINISHED on $HN" | tee -a output.txt
}


# ---------------------------------------
# Start the DVM
# ---------------------------------------
if [ "x" = "x$CI_HOSTFILE" ] ; then
    prte --daemonize
else
    prte --daemonize --hostfile $CI_HOSTFILE
fi

# Wait for DVM to start
sleep 5

########

# ---------------------------------------
# (Sanity test) Run the test - hostname
# ---------------------------------------
_CMD="prun -n 1 hostname"
echo "======================="
echo "Running hostname: $_CMD"
echo "======================="

rm output.txt ; touch output.txt
for n in $(seq 1 $NUM_ITERS) ; do
    echo -e "--------------------- Execution (hostname): $n"
    $_CMD 2>&1 | tee -a output.txt
    st=${PIPESTATUS[0]}
    if [ $st -ne 0 ] ; then
        echo "ERROR: prun failed with $st"
        FINAL_RTN=1
        _shutdown
    fi
done

echo "---- Done"
# ---------------------------------------
# (Sanity test) Verify the results
# ---------------------------------------
ERRORS=`grep ERROR output.txt | wc -l`
if [[ $ERRORS -ne 0 ]] ; then
    echo "ERROR: Error string detected in the output"
    FINAL_RTN=2
    _shutdown
fi

LINES=`wc -l output.txt | awk '{print $1}'`
if [[ $LINES -ne 1 ]] ; then
    echo "ERROR: Incorrect number of lines of output. Expected 1. Actual $LINES"
    FINAL_RTN=3
    _shutdown
fi

echo "Sanity check passed"

echo "---- Done"

# ---------------------------------------
# Run the test
# ---------------------------------------
rm output.txt ; touch output.txt
_run_stress_test


echo "---- Done"
# ---------------------------------------
# Verify the results
# ---------------------------------------
ERRORS=`grep ERROR output.txt | wc -l`
if [[ $ERRORS -ne 0 ]] ; then
    echo "ERROR: Error string detected in the output"
    FINAL_RTN=4
    _shutdown
fi

LINES=`wc -l output.txt | awk '{print $1}'`
if [[ $LINES -eq 0 ]] ; then
    echo "ERROR: No results in output file. Expected >0. Actual $LINES"
    FINAL_RTN=5
    _shutdown
fi

# The 'sleeper' exe prints 'DONE' in its output,
# we check to see that number of instances actually ran.
n_expected=$END
n_lines=$(grep DONE output.txt | grep -v TERMINATING | grep -v SUBMITTING |wc -l)

#echo "DEBUG: n_expected=$n_expected"
#echo "DEBUG: n_lines=$n_lines"

if [ "$n_expected" -ne "$n_lines" ] ; then
    echo "FAILURE: $n_expected != $n_lines"
    FINAL_RTN=6
    _shutdown
fi


echo "---- Done"
if [ $FINAL_RTN == 0 ] ; then
    #echo "SUCCESS: $n_expected == $n_lines"
    echo "Success"
fi

_shutdown
