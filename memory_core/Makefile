# ============================================================================
# MEMORY CORE v3.0 Makefile
# HELIOS Cognitive Ecosystem
#
# "Los recuerdos viven aquí. Pero la memoria vive en HERA."
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE
LDFLAGS = -lpthread -lrt -lm

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Source files
CORE_SRC = $(SRCDIR)/core/memory_core.c

ALL_SRC = $(CORE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libmemory_core.a

# Test target
TEST_TARGET = $(BINDIR)/mc_test

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

$(TEST_TARGET): tools/mc_test.c $(LIB_TARGET)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $< -L$(BINDIR) -lmemory_core $(LDFLAGS) -o $@
	@echo ""
	@echo "Test program built: $@"
	@echo "Run with: ./$(TEST_TARGET)"

clean:
	rm -rf $(OBJDIR) $(BINDIR)

# ============================================================================
# Info
# ============================================================================

info:
	@echo "MEMORY CORE v3.0 Build System"
	@echo ""
	@echo "  Compiler: $(CC)"
	@echo "  Flags:    $(CFLAGS)"
	@echo "  Sources:  $(ALL_SRC)"
	@echo "  Library:  $(LIB_TARGET)"
	@echo "  Test:     $(TEST_TARGET)"
