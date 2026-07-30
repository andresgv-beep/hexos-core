# ============================================================================
# COGNITIVE KERNEL v3.0 (STUB) Makefile
# HELIOS Cognitive Ecosystem
#
# "El LLM genera palabras. El Cognitive Kernel genera SIGNIFICADO."
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE
LDFLAGS = -lpthread -lm

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Source files
CORE_SRC = $(SRCDIR)/cognitive_kernel.c

ALL_SRC = $(CORE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libcognitive_kernel.a

# Test target
TEST_TARGET = $(BINDIR)/ck_test

# ============================================================================
# Rules
# ============================================================================

.PHONY: all clean lib test

all: lib test

lib: $(LIB_TARGET)

$(LIB_TARGET): $(OBJECTS)
	@mkdir -p $(BINDIR)
	ar rcs $@ $(OBJECTS)
	@echo ""
	@echo "Library built: $@"

$(OBJDIR)/%.o: $(SRCDIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -I$(INCDIR) -c $< -o $@

test: $(TEST_TARGET)

$(TEST_TARGET): tools/ck_test.c $(LIB_TARGET)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $< -L$(BINDIR) -lcognitive_kernel $(LDFLAGS) -o $@
	@echo ""
	@echo "Test program built: $@"

clean:
	rm -rf $(OBJDIR) $(BINDIR)
