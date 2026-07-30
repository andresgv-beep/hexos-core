# ============================================================================
# HERA v3.0 Makefile
# HELIOS Cognitive Ecosystem
#
# "HERA ES LA MENTE. HEXOS ES EL CUERPO."
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE
LDFLAGS = -lpthread -lrt -lm

# Optional: Link with Memory Core and HNF-EXT
# Uncomment these if building integrated
# CFLAGS += -DMEMORY_CORE_AVAILABLE -DHNF_EXT_AVAILABLE
# LDFLAGS += -L../memory_core/bin -lmemory_core -L../hnf_ext/bin -lhnf_ext

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Source files
CORE_SRC = $(SRCDIR)/hera.c

ALL_SRC = $(CORE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libhera.a

# Test target
TEST_TARGET = $(BINDIR)/hera_test

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

$(TEST_TARGET): tools/hera_test.c $(LIB_TARGET)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $< -L$(BINDIR) -lhera $(LDFLAGS) -o $@
	@echo ""
	@echo "Test program built: $@"

clean:
	rm -rf $(OBJDIR) $(BINDIR)
