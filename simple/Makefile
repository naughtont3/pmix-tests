
# Set default to pmix wrapper, can override with CC=xxx on command-line
CC = pcc

# We are not striving for performance, so set debug flags
CFLAGS += -g -D_GNU_SOURCE

all: progress_thread.o simptest simpclient

progress_thread.o: progress_thread.c
	$(CC) $(CFLAGS) -I$(LIBEVENT_HOME)/include -I$(PMIX_HOME)/include -c progress_thread.c

simptest: simptest.c progress_thread.c
	$(CC) $(CFLAGS) -I$(PMIX_HOME)/include -L$(PMIX_HOME)/lib -I$(LIBEVENT_HOME)/include -L$(LIBEVENT_HOME)/lib -lpmix -levent -o simptest simptest.c progress_thread.o

simpclient: simpclient.c
	$(CC) $(CFLAGS) -I$(PMIX_HOME)/include -L$(PMIX_HOME)/lib -I$(LIBEVENT_HOME)/include -L$(LIBEVENT_HOME)/lib -lpmix -levent -o simpclient simpclient.c

clean:
	rm -f *.o simptest simpclient simpdie
