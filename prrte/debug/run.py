#!/bin/python3.6

from os import environ
from os import error
from os import remove
from subprocess import CalledProcessError
from subprocess import check_call
from subprocess import DEVNULL
from subprocess import PIPE
from subprocess import STDOUT
from subprocess import Popen
from sys import argv
from sys import stdout
from threading import Timer
from time import sleep
from time import strftime

SYS_DAEMON_NEEDED = 0x01
ATTACH_TARGET_NEEDED = 0x02
MULTINODE_TEST = 0x04
ATTACH_WAITTIME = 10.0

# Set of tests to run. There is one row per test. The columns in the row are:
# col[0]: Test case name, labels the testcase and is included in output
#         filenames
# col[1]: Flags for special setup processing for testcase execution
#         SYS_DAEMON_NEEDED: Start prte system deamon before starting testcase
#         ATTACH_TARGET_NEEDED: Launch prterun session to attach to
#         MULTINODE_TEST: Specify hostfile when starting daemon
# col[2]: Path to main executable for testcase
# col[3-n]: Command line arguments for testcase
#
# A multinode testcase includes MULTINODE_TEST in it's testcase flags settings
tests = [ ["direct", SYS_DAEMON_NEEDED, "./direct"],
          ["direct-cospawn", SYS_DAEMON_NEEDED, "./direct", "-c"]
# These testcases are not working at this point, so comment them out for now
#          ["attach", ATTACH_TARGET_NEEDED, "./attach", "$attach-namespace"],
#          ["indirect", SYS_DAEMON_NEEDED, "indirect", "./prun", "-q", "-n", "2",
#                  "hello", "10"],
#          ["direct-1host", SYS_DAEMON_NEEDED | MULTINODE_TEST,
#                  "direct", "-H", "./direct-1host-hostfile", "--map-by",
#                  "ppr:4:node"],
#          ["direct-2host", SYS_DAEMON_NEEDED | MULTINODE_TEST,
#                  "direct", "-H", "./direct-2host-hostfile", "--map-by",
#                  "ppr:4:node"]
        ]

# Commands to start prte system daemons for multi-node tests. The testcase
# name (array element 0) must match the name of the testcase in the tests array
# and the name of the hostfile should be the same as the hostfile in the 
# testcase run command in the tests array.
hostfileDaemons = [ ["direct-2host", "prte", "--system-server", "--hostfile",
                          "./direct-2host-hostfile", "--report-uri", "+"],
                    ["direct-1host", "prte", "--system-server", "--hostfile",
                          "./direct-1host-hostfile", "--report-uri", "+"] ]

def log(*text):
    """Write a timestamped log message to stdout"""

    messageText = ""
        # The log message may be a combination of strings, numbers and
        # sublists. Append each message fragment to log message based on type
    for fragment in text:
        if (isinstance(fragment, str)):
            messageText = messageText + fragment
        elif (isinstance(fragment, int) or isinstance(fragment, float)):
            messageText = messageText + str(fragment)
        else:
            for frag in fragment:
                if (isinstance(frag, int) or isinstance(frag, float)):
                    messageText = messageText + str(frag) + " "
                else:
                    messageText = messageText + frag + " "
    print(strftime("%X ") + messageText)
    stdout.flush()

def testcaseTimer(proc, waitTimeout):
    """Timer thread used to detect if a testcase has reached it's time limit."""

        # Testcase timeout limit has been reached.
        # If the testcase process did not complete, kill it now
    childStatus = proc.poll()
    if (childStatus == None):
        log("ERROR: Testcase execution timed out, kill pid ", proc.pid)
        proc.kill()

        # Get testcase completion status. 0=success, anything else=failure
    proc.wait(waitTimeout)
    return proc.returncode

def shutdownPrte(prteProcess, waitTimeout):
    """Shut down a prte system daemon"""
    ptermProcess = Popen(["pterm", "--system-server-only"],
                          stdout=DEVNULL, stderr=DEVNULL)
    rc = prteProcess.wait(waitTimeout)
    ptermProcess.wait(waitTimeout)
    return rc

def writeStdio(stdoutFile, stdoutText, stderrFile, stderrText):
    """Write stdout and stderr test to output files"""
    for text in stdoutText:
        stdoutFile.write(text)
    for text in stderrText:
        stderrFile.write(text)

def run(selected, testCases):
    """Driver to run individual test cases specified in testCases"""

      # Run the individual testcases. If a test case fails, that results
      # in an exception which logs that test case failure and then the
      # next test case is run.
    failedTests = []
    prteProcess = None
    rc = 0
    failures = 0
    testcases = 0
    testcaseTimeout = 60.0
    daemonDelay = 5.0
    waitTimeout = 5.0
    try:
        testcaseTimeout = float(environ["TC_TIMEOUT"])
    except KeyError:
        pass
    try:
        waitTimeout = float(environ["TC_WAIT_TIMEOUT"])
    except KeyError:
        pass
    try:
        daemonDelay = float(environ["TC_DAEMON_DELAY"])
    except KeyError:
        pass

    log("Testcase timeout limit is ", testcaseTimeout, " seconds.")
    log("Process wait timeout limit is ", waitTimeout, " seconds.")
    log("Daemon startup delay is ", daemonDelay, " seconds.")
    for testCase in testCases:
        if ((selected != "**all**") and (selected != testCase[0])):
            continue
        log("Initialize testcase ", testCase[0])
        testcases = testcases + 1
        prteProcess = None
        attachProcess = None
        attachTimerThread = None
        prteNamespace = ""
        attachNamespace = ""
  
          # If the test requires a persistent prte daemon, start it here
        if ((testCase[1] & SYS_DAEMON_NEEDED) != 0):
            if ((testCase[1] & MULTINODE_TEST) == 0):
                prteProcess = Popen(["prte", "--report-uri", "+",
                                    "--system-server"], stdout=PIPE,
                                    stderr=STDOUT)
            else:
                  # This is a multinode testcase (with hostfile). Find the
                  # matching prte daemon startup command and start the daemon.
                prteCommand = None
                for daemonCmd in hostfileDaemons:
                    if (daemonCmd[0] == testCase[0]):
                        prteCommand = daemonCmd[1:]
                        break
                if (prteCommand == None):
                    log("Multi-node prte daemon command not found for ",
                        testCase[0])
                    failures = failures + 1
                    failedTests.append(testCase[0])
                    rc = 1
                    continue
                log("Starting multi-node prte ", prteCommand)
                prteProcess = Popen(prteCommand, stdout=PIPE, stderr=STDOUT)

               # The namespace is the first ';' delimited token in the first
               # line # of prte daemon output. This read also serves as a
               # barrier to ensure prte is started before running the test
            pipe = prteProcess.stdout
            prteOutput = pipe.readline()
            line = str(object=prteOutput, encoding="ascii")
            semiIndex = line.find(";")
            if (semiIndex != -1):
                prteNamespace = line[0:semiIndex]
            log("prte namespace: ", prteNamespace)

              # Delay to allow daemon to fully initialize
            sleep(daemonDelay)

          # If the test requires an application to attach to, start the app here
        if ((testCase[1] & ATTACH_TARGET_NEEDED) != 0):
            attachProcess = Popen(["prterun", "--report-uri", "+",
                                  "-n", "2", "hello",
                                  str(int(ATTACH_WAITTIME))], 
                                  stdout=PIPE, stderr=STDOUT)
              # The namespace is the first ';' delimited token in the first line
              # of prterun output. This read also serves as a barrier to
              # ensure prterun is started before running the test
            pipe = attachProcess.stdout
            attachOutput = pipe.readline()
            line = str(object=attachOutput, encoding="ascii")
            semiIndex = line.find(";")
            if (semiIndex != -1):
                attachNamespace = line[0:semiIndex]
                  # --report-uri namespace string contains trailing task index
                  # that must be removed
                dotIndex = attachNamespace.rfind(".")
                if (dotIndex != -1):
                    attachNamespace = attachNamespace[0:dotIndex]
            log("attach target namespace: ", attachNamespace)

              # Delay to allow application to fully initialize
            sleep(daemonDelay)

              # Create a thread to monitor the attach target and kill it if it
              # exceeds its allotted execution time
            attachTimerThread = Timer(testcaseTimeout, testcaseTimer,
                                args=(attachProcess, waitTimeout))
            attachTimerThread.daemon = True
            attachTimerThread.start()

          # If the testcase command arguments contain symbolic names then
          # replace them with actual values here
        for idx, testArg in enumerate(testCase):
            if (testArg == "$namespace"):
                testCase[idx] = prteNamespace
            if (testArg == "$attach-namespace"):
                testCase[idx] = attachNamespace

        stdoutPath = str.format("{}.stdout", testCase[0])
        stderrPath = str.format("{}.stderr", testCase[0])
          # Delete old testcase output files. Missing files is not an error
        for path in [stdoutPath, stderrPath]:
            try:
                remove(path)
            except FileNotFoundError as e:
                continue
        stdoutFile = open(stdoutPath, "w+")
        stderrFile = open(stderrPath, "w+")
        try:
              # Create the test case process
            testProcess = Popen(testCase[2:], stdout=PIPE, stderr=PIPE,
                                universal_newlines=True)
            log("Starting testcase pid ", testProcess.pid, ": '", testCase[2:],
                "'")

              # Create a thread to monitor the testcase and kill it if it
              # exceeds its alloted execution time
            timerThread = Timer(testcaseTimeout, testcaseTimer,
                                args=(testProcess, waitTimeout))
            timerThread.daemon = True
            timerThread.start()

              # Note that testProcess.communicate blocks until the process exits
            stdoutText, stderrText = testProcess.communicate()

              # Get test case exit code first to avoid leaving a zombie process
            runRC = testProcess.wait(waitTimeout)

              # Test case complete, cancel the testcase timer
            timerThread.cancel()

              # Test case has terminated, clean up related processes here
            if ((testCase[1] & ATTACH_TARGET_NEEDED) != 0):
                attachTimerThread.cancel()
                  # The attach target runs for approximately ATTACH_WAITTIME
                  # seconds, so if it hasn't terminated yet then wait that
                  # number of seconds to give it a chance to exit normally
                targetStatus = attachProcess.poll()
                if (targetStatus == None):
                    sleep(ATTACH_WAITTIME)

                  # If a target application was needed and it did not terminate
                  # then kill it here.
                targetStatus = attachProcess.poll()
                if (targetStatus == None):
                    log("Attach target pid ", attachProcess.pid, 
                        " did not terminate, killing target")
                    attachProcess.kill()
                    writeStdio(stdoutFile, stdoutText, stderrFile, stderrText)
                    failures = failures + 1
                    failedTests.append(testCase[0])
                    rc = 1
                    continue

              # If this testcase started a prte daemon, shut it down here
            if ((testCase[1] & SYS_DAEMON_NEEDED) != 0):
                prteRC = shutdownPrte(prteProcess, waitTimeout)
                if (prteRC != 0):
                    log("ERROR: prte daemon failed with rc=", prteRC)
                    failures = failures + 1
                    failedTests.append(testCase[0])
                    continue

              # Make sure testcase exited successfully
            if (runRC != 0):
                log("ERROR: Test failed with return code ", runRC)
                if (len(stderrText) > 0):
                    log("Testcase stderr is:\n", stderrText)
                writeStdio(stdoutFile, stdoutText, stderrFile, stderrText)
                failures = failures + 1
                failedTests.append(testCase[0])
                rc = 1
                continue

            log("Verify stdout/stderr for testcase ", testCase[0])
              # Get the testcase stdout and stderr output, split that output
              # into '\n'-delimited newlines, and sort the resulting text
              # arrays by the line prefix tag
              #
              # Sorting by line prefix tag eliminates false failures due to
              # difference in ordering of testcase output with differing
              # timing of execution by individual tasks.
              #
              # This eliminates the possibility of detecting problems caused
              # by differing timing of interactions between processes, but
              # that kind of testing is probably outside the scope of 
              # simple CI testing.
            stdoutText = sorted(stdoutText.splitlines(keepends=True))
            stderrText = sorted(stderrText.splitlines(keepends=True))

              # Filter stdout and stderr, translating variable text like
              # namespaces to constant strings so that comparison to baseline
              # files can be successfully done
            stdoutFilter = Popen("./tcfilter", stdin=PIPE, stdout=stdoutFile)

              # Send stdout text to filter
            pipe = stdoutFilter.stdin
            for text in stdoutText:
                pipe.write(text.encode(encoding="UTF-8"))
            pipe.close()
            stdoutFilter.wait(waitTimeout)

            stderrFilter = Popen("./tcfilter", stdin=PIPE, stdout=stderrFile)

              # Send stderr text to filter
            pipe = stderrFilter.stdin
            for text in stderrText:
                pipe.write(text.encode(encoding="UTF-8"))
            pipe.close()
            stderrFilter.wait(waitTimeout)

              # Compare stdout and stderr output to corresponding baselines
            diffProcess = Popen(["/bin/diff", stdoutPath + ".baseline",
                                 stdoutPath])
            diffProcess.wait(waitTimeout)
            if (diffProcess.returncode != 0):
                log("ERROR: testcase ", testCase[0],
                    " stdout does not match baseline")
                failures = failures + 1
                failedTests.append(testCase[0])
                rc = 1
                continue

            diffProcess = Popen(["/bin/diff", stderrPath + ".baseline",
                                 stderrPath])
            diffProcess.wait(waitTimeout)
            if (diffProcess.returncode != 0):
                log("ERROR: testcase ", testCase[0],
                    " stderr does not match baseline")
                failures = failures + 1
                failedTests.append(testCase[0])
                rc = 1
                continue
        except CalledProcessError as e:
            log("ERROR: Command ", "'", e.cmd, "' failed with return code ",
                e.returncode)
            failures = failures + 1
            failedTests.append(testCase[0])
            rc = 1
            if (prteProcess != None):
                shutdownPrte(prteProcess, waitTimeout)

        except error as e:
            log("ERROR: Command", "'", testCase, "' failed: ", e.strerror)
            failures = failures + 1
            failedTests.append(testCase[0])
            rc = 1
            if (prteProcess != None):
                shutdownPrte(prteProcess, waitTimeout)

        log("Completed testcase ", testCase[0])

    log("Ran " + str(testcases) + " tests, " + str(failures) + " failed")
    if (failures > 0):
        log("Failed tests:")
        for failedTest in failedTests:
            log("    ", failedTest)
    return rc

rc = -1
if (len(argv) > 1):
    rc = run(argv[1], tests)
else:
    rc = run("**all**", tests)
exit(rc)
