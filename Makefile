PKGCONF := pkgconf
CFLAGS := -fpic -g -O2 -Wall -Wno-missing-braces
CFLAGS += -fvisibility=hidden -ffunction-sections -fdata-sections
CFLAGS += $(shell $(PKGCONF) --cflags python3)
LDLIBS := -lpython3
LDFLAGS := -Wl,--gc-sections

MAKEFLAGS += -r
.SUFFIXES:

OBJS := atomic.o lock.o _mpmetrics.o
DEPS := $(OBJS:.o=.d)

_mpmetrics.so: $(OBJS)
	$(CC) -shared $(LDFLAGS) $^ $(LDLIBS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -MMD -c $< -o $@

-include $(DEPS)

.PHONY: clean
clean:
	rm -f *.so *.o *.d
