# ============================================================================
# HNF-EXT v1.0 Makefile
# HELIOS Cognitive Ecosystem
#
# "Aquí vive el alma de Helios"
# ============================================================================

CC = gcc
CFLAGS = -D_GNU_SOURCE -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE
LDFLAGS = -lm

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Source files
CORE_SRC = $(SRCDIR)/hnf_ext.c

ALL_SRC = $(CORE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libhnf_ext.a

# Test target
TEST_TARGET = $(BINDIR)/hnf_ext_test

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

$(TEST_TARGET): tools/hnf_ext_test.c $(LIB_TARGET)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $< -L$(BINDIR) -lhnf_ext $(LDFLAGS) -o $@
	@echo ""
	@echo "Test program built: $@"

clean:
	rm -rf $(OBJDIR) $(BINDIR)
