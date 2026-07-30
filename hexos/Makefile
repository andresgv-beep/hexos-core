# ============================================================================
# HEXOS Makefile
# HELIOS Executive Operating System
#
# NOTE: We compile with gcc, NOT nvcc
# HEXOS runs exclusively on CPU
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE -D_FORTIFY_SOURCE=0 -U_FORTIFY_SOURCE
LDFLAGS = -ldl -lpthread -lrt

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Cognitive module paths
HNF_EXT_DIR = ../hnf_ext
MEMORY_CORE_DIR = ../memory_core
HERA_DIR = ../hera

# Source files
CORE_SRC = $(SRCDIR)/core/main.c $(SRCDIR)/core/log.c
HW_SRC = $(SRCDIR)/hw/detect.c $(SRCDIR)/hw/cpu.c $(SRCDIR)/hw/ram.c \
         $(SRCDIR)/hw/storage.c $(SRCDIR)/hw/gpu_nvml.c
TELEMETRY_SRC = $(SRCDIR)/telemetry/telemetry.c
IPC_SRC = $(SRCDIR)/ipc/ipc.c
UI_SRC = $(SRCDIR)/ui/hexos_ui.c $(SRCDIR)/ui/hexos_views.c

ALL_SRC = $(CORE_SRC) $(HW_SRC) $(TELEMETRY_SRC) $(IPC_SRC) $(UI_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Cognitive module libraries
HNF_EXT_LIB = $(HNF_EXT_DIR)/bin/libhnf_ext.a
MEMORY_CORE_LIB = $(MEMORY_CORE_DIR)/bin/libmemory_core.a
HERA_LIB = $(HERA_DIR)/bin/libhera.a

# Target
TARGET = $(BINDIR)/hexos

# ============================================================================
# Rules
# ============================================================================

.PHONY: all clean run modules

all: modules $(TARGET)

# Build cognitive modules first
modules:
	@echo "Building cognitive modules..."
	@$(MAKE) -C $(HNF_EXT_DIR) lib --no-print-directory 2>/dev/null || true
	@$(MAKE) -C $(MEMORY_CORE_DIR) lib --no-print-directory 2>/dev/null || true
	@$(MAKE) -C $(HERA_DIR) lib --no-print-directory 2>/dev/null || true

$(TARGET): $(OBJECTS)
	@mkdir -p $(BINDIR)
	$(CC) $(OBJECTS) -o $@ \
		$(HNF_EXT_DIR)/bin/libhnf_ext.a \
		$(MEMORY_CORE_DIR)/bin/libmemory_core.a \
		$(HERA_DIR)/bin/libhera.a \
		$(LDFLAGS)
	@echo ""
	@echo "Build complete: $@"
	@echo ""
	@echo "Run with: ./$(TARGET)"

$(OBJDIR)/%.o: $(SRCDIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -I$(INCDIR) -I$(HNF_EXT_DIR)/include -I$(MEMORY_CORE_DIR)/include -I$(HERA_DIR)/include -c $< -o $@

clean:
	rm -rf $(OBJDIR) $(BINDIR)

run: $(TARGET)
	./$(TARGET)

# ============================================================================
# Dependencies
# ============================================================================

$(OBJDIR)/core/main.o: $(SRCDIR)/core/main.c $(INCDIR)/hexos.h $(INCDIR)/hexos_types.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_hw.h
$(OBJDIR)/core/log.o: $(SRCDIR)/core/log.c $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h
$(OBJDIR)/hw/detect.o: $(SRCDIR)/hw/detect.c $(INCDIR)/hexos_hw.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h
$(OBJDIR)/hw/cpu.o: $(SRCDIR)/hw/cpu.c $(INCDIR)/hexos_hw.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h
$(OBJDIR)/hw/ram.o: $(SRCDIR)/hw/ram.c $(INCDIR)/hexos_hw.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h
$(OBJDIR)/hw/storage.o: $(SRCDIR)/hw/storage.c $(INCDIR)/hexos_hw.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h
$(OBJDIR)/hw/gpu_nvml.o: $(SRCDIR)/hw/gpu_nvml.c $(INCDIR)/hexos_hw.h $(INCDIR)/hexos_log.h $(INCDIR)/hexos_types.h

# ============================================================================
# Info
# ============================================================================

info:
	@echo "HEXOS Build System"
	@echo ""
	@echo "  Compiler: $(CC)"
	@echo "  Flags:    $(CFLAGS)"
	@echo "  Sources:  $(ALL_SRC)"
	@echo "  Target:   $(TARGET)"
	@echo ""
	@echo "  NOTE: HEXOS runs on CPU only. No CUDA compilation."
	@echo "        GPU monitoring uses NVML (libnvidia-ml.so)"

# ============================================================================
# Tools
# ============================================================================

tools: $(BINDIR)/hexos_ipc_test

$(BINDIR)/hexos_ipc_test: tools/hexos_ipc_test.c $(SRCDIR)/ipc/ipc.c $(SRCDIR)/core/log.c
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $^ -o $@ $(LDFLAGS) -lm
