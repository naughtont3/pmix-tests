#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    char host[128];
    int rc;
    int nsec = 1;
    pid_t pid = getpid();

    if (argc > 1) {
        nsec = atoi(argv[1]);
    }

    if (0 > (rc = gethostname(host, sizeof(host)))) {
        fprintf(stderr, "(%6d) Error: failed to obtain hostname (rc=%d)\n", pid);
        return (1);
    }

    sleep(nsec);

    printf("(%6d) [%s] DONE (slept %d seconds)\n", pid, host, nsec);
    return 0;
}
